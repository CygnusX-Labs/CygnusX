"""房间内用户发言的 Manager 响应回路。

用户在团队协作室发出 ``room.user_message`` 后，由 Celery 任务驱动本服务：
以 readonly_consultation 模式调用 Manager agent（默认 agent-general，
无则回退到任意 planner_eligible 的可会诊 agent），把结论落为
``room.agent_message`` Case 级证据事件——SSE 投影与 Matrix 镜像随之自动生效。

同一 Case 同时只允许一个 pending 响应（Redis 互斥锁）；锁被占用时由任务层
短暂重试，避免连续发言被静默丢弃。LLM 或 Bridge 失败只记 warning，绝不影响
用户发言主流程。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services.agent_consultation_service import AgentConsultationService
from omichub.application.services.agentteams_capability_registry import (
    AgentTeamsCapabilityRegistry,
    get_agentteams_capability_registry,
)
from omichub.application.services.agentteams_execution_intent import (
    GENERAL_PLAN_CONTRACT,
    ExecutionIntent,
    classify_execution_intent,
    has_explicit_object,
)
from omichub.application.services.agentteams_route_decision import (
    ROUTE_DECISION_EVENT_TYPE,
    build_route_decision,
    summarize_route_decision,
)
from omichub.application.services.agentteams_service import (
    AUTO_CONFIRM_CASES_KEY,
    CASE_LEVEL_WORK_ITEM_ID,
    AgentTeamsService,
)
from omichub.application.services.flow_registry import FlowRegistry
from omichub.infrastructure.cache.redis_client import get_redis
from omichub.infrastructure.database.models.user import UserModel

ROOM_RESPONSE_LOCK_KEY_PREFIX = "agentteams:room-response:lock:"
ROOM_RESPONSE_LOCK_TTL_SECONDS = 180
_CONTEXT_EVENT_LIMIT = 30
_CONTEXT_EVENT_SUMMARY_LINES = 8
_PREFERRED_MANAGER_AGENT_ID = "agent-general"

# 执行对象澄清（O6 阶段 2）：clarify 态下 Manager 直发选项式追问卡片，
# 复用 room.ask_user / AskUserCard 的渲染与【澄清回复】回填链路。
CLARIFY_KIND_EXECUTION_OBJECT = "execution_object"
MAX_EXECUTION_CLARIFY_ROUNDS = 2
ROOM_ASK_REPLY_MARKER = "【澄清回复】"
_CLARIFY_OPT_OUT_MARKERS = ("先不执行", "暂不执行", "先讨论", "继续讨论", "不用了", "取消")
_CLARIFY_EXHAUSTED_NOTE = (
    "系统提示：就该执行请求已进行 "
    f"{MAX_EXECUTION_CLARIFY_ROUNDS} 轮选项式追问，仍未获得可执行的作用对象（输入文件/数据）。"
    "本轮按纯对话处理：请向用户说明暂时无法直接执行的原因，"
    "并建议其上传文件、引用工作区已有数据或给出公共数据库 accession 后重试。"
)

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class AgentTeamsRoomResponseService:
    """Generate one Manager reply per room user message, at most one per case at a time."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        agentteams: AgentTeamsService,
        registry: AgentTeamsCapabilityRegistry | None = None,
        redis_getter: Callable[[], Any] = get_redis,
        lock_ttl_seconds: int = ROOM_RESPONSE_LOCK_TTL_SECONDS,
        flow_registry: FlowRegistry | None = None,
    ) -> None:
        self._db = db
        self._agentteams = agentteams
        self._registry = registry or get_agentteams_capability_registry()
        self._redis_getter = redis_getter
        self._lock_ttl = lock_ttl_seconds
        self._flow_registry = flow_registry

    async def respond(self, case_id: str, requester_ref: str, content: str) -> dict[str, str]:
        lock_key = f"{ROOM_RESPONSE_LOCK_KEY_PREFIX}{case_id}"
        lock_token = uuid4().hex
        redis = self._redis_getter()
        acquired = False
        try:
            acquired = bool(await redis.set(lock_key, lock_token, nx=True, ex=self._lock_ttl))
            if not acquired:
                logger.bind(case_id=case_id).info(
                    "AgentTeams room response skipped: another response is pending"
                )
                return {"status": "skipped_locked"}
            return await self._respond_locked(case_id, requester_ref, content)
        finally:
            if acquired:
                try:
                    await redis.eval(_RELEASE_LOCK_LUA, 1, lock_key, lock_token)
                except Exception as exc:  # noqa: BLE001
                    logger.bind(case_id=case_id).warning(
                        "AgentTeams room response lock release failed: {}", exc
                    )

    async def _respond_locked(self, case_id: str, requester_ref: str, content: str) -> dict[str, str]:
        try:
            case = await self._agentteams.get_case(case_id, requester_ref)
            # 终态 Case 也允许继续对话（只读会诊回复，不改 Case 状态）。
            events = await self._agentteams.get_case_events(
                case_id, requester_ref, limit=_CONTEXT_EVENT_LIMIT
            )
            event_items = [
                item for item in events.get("events", []) if isinstance(item, dict)
            ]
            preferences = await self._manager_preferences(requester_ref)
            execution_outcome = await self._maybe_start_chat_execution(
                case_id=case_id,
                requester_ref=requester_ref,
                case=case,
                events=event_items,
                content=content,
                preferences=preferences,
            )
            if execution_outcome == "clarified":
                # clarify 态：选项式追问卡片已落 room.ask_user，本轮不再跑
                # LLM 会诊，避免与澄清卡片重复回复；答案将作为下一条
                # room.user_message 回到本回路。
                return {"status": "asked"}
            # 触发成功后 Bridge 侧已推进到 planning_running；用拷贝覆盖快照状态，
            # 避免 Manager 按触发前的 received 快照作答。
            question_case = (
                {**case, "status": "planning_running"}
                if execution_outcome == "started"
                else case
            )
            question = self._build_question(
                question_case,
                event_items,
                content,
                preferences,
                system_note=(
                    _CLARIFY_EXHAUSTED_NOTE if execution_outcome == "degraded" else None
                ),
            )
            agent_id = self._manager_agent_id()
            if agent_id is None:
                logger.bind(case_id=case_id).warning(
                    "AgentTeams room response skipped: no manager agent available"
                )
                return {"status": "skipped_no_manager"}
            await self._set_typing(case_id, typing=True)
            try:
                envelope = await AgentConsultationService(
                    self._db, agentteams_service=self._agentteams
                ).run_consultation(
                    case_id=case_id,
                    agent_id=agent_id,
                    question=question,
                    capability="interpretation",
                    evidence_refs=[],
                    requested_tools=[],
                    requester_ref=requester_ref,
                )
                reply = envelope.conclusion.strip()
                questions = [
                    {"question": item.question.strip(), "options": item.options}
                    for item in (getattr(envelope, "ask_user", None) or [])
                    if item.question.strip()
                ]
                if not reply and not questions:
                    return {"status": "failed"}
                if questions:
                    # 澄清问题走可交互卡片：前端渲染 ask_user 弹窗，答案作为下一条
                    # room.user_message 回到本响应回路。
                    await self._agentteams.post_case_evidence(
                        case_id,
                        work_item_id=CASE_LEVEL_WORK_ITEM_ID,
                        event_type="room.ask_user",
                        summary=(reply or questions[0]["question"])[:200],
                        payload={
                            "content": reply[:4_000],
                            "agent_id": agent_id,
                            "role": "bioops-manager",
                            "questions": questions,
                        },
                    )
                    return {"status": "asked"}
                await self._agentteams.post_case_evidence(
                    case_id,
                    work_item_id=CASE_LEVEL_WORK_ITEM_ID,
                    event_type="room.agent_message",
                    summary=reply[:200],
                    payload={
                        "content": reply[:4_000],
                        "agent_id": agent_id,
                        "role": "bioops-manager",
                    },
                )
                return {"status": "responded"}
            finally:
                await self._set_typing(case_id, typing=False)
        except Exception as exc:  # noqa: BLE001 - 响应失败不得影响用户发言主流程
            logger.bind(case_id=case_id).warning("AgentTeams room response failed: {}", exc)
            return {"status": "failed"}

    async def _maybe_start_chat_execution(
        self,
        *,
        case_id: str,
        requester_ref: str,
        case: dict[str, Any],
        events: list[dict[str, Any]],
        content: str,
        preferences: dict[str, Any] | None = None,
    ) -> str:
        """聊天式 Case 的执行意图三态处理；返回处理结果。

        返回值：``started``（execute 态，已触发 planning）/ ``clarified``
        （clarify 态，已落选项式追问卡片）/ ``degraded``（追问轮次耗尽，
        降级为纯对话）/ ``none``（chat 态或触发失败，走正常 Manager 回复）。

        仅对无 flow_id、仍处于 received、且尚无 plan-01 的 Case 生效——flow 型
        Case 的人工审批链路绝不旁路。触发失败只记日志，不影响 Manager 回复。
        若用户偏好为 autonomous，将该 Case 加入自动确认集合，以便进入
        approval_pending 后无需人工审批。clarify 态不推送 route_decision
        执行卡片（O1 兼容约束）。
        """
        if case.get("flow_id") or case.get("status") != "received":
            return "none"
        work_items = case.get("work_items")
        if isinstance(work_items, list) and any(
            isinstance(item, dict) and item.get("work_item_id") == "plan-01"
            for item in work_items
        ):
            return "none"
        refs = self._latest_message_context_refs(events, content)
        pending_clarify = self._pending_execution_clarify(events, content)
        if pending_clarify and any(marker in content for marker in _CLARIFY_OPT_OUT_MARKERS):
            # 用户在澄清中明确放弃执行：按纯对话处理，不再追问。
            return "none"
        intent = classify_execution_intent(content, refs)
        origin_content: str | None = None
        if pending_clarify and intent is not ExecutionIntent.EXECUTE:
            if has_explicit_object(content, refs):
                # 澄清回复补全了作用对象：沿用原始执行请求，自动转入 execute。
                intent = ExecutionIntent.EXECUTE
                origin_content = self._pending_clarify_origin(events, content)
            elif intent is ExecutionIntent.CHAT and content.strip().startswith(
                ROOM_ASK_REPLY_MARKER
            ):
                # 结构化澄清答复仍未给出对象：推进追问轮次（受轮次上限约束）。
                intent = ExecutionIntent.CLARIFY
        if intent is ExecutionIntent.CHAT:
            return "none"
        if intent is ExecutionIntent.CLARIFY:
            rounds = self._execution_clarify_rounds(events)
            if rounds >= MAX_EXECUTION_CLARIFY_ROUNDS:
                logger.bind(case_id=case_id).info(
                    "AgentTeams execution clarify exhausted after {} rounds, degraded to chat",
                    rounds,
                )
                return "degraded"
            emitted = await self._emit_execution_clarify(
                case_id, content, round_no=rounds + 1
            )
            return "clarified" if emitted else "none"
        # execute 态：路由决策卡（O1）：执行意图成立即外显路由决策，不改变路由逻辑本身。
        await self._emit_route_decision(case_id, content)
        # Bridge objective 上限 1000 字符：用户原话截断后附通用计划契约尾段；
        # 经澄清补全的执行沿用原始请求，并附用户补充的作用对象说明。
        if origin_content is not None:
            objective = (
                f"{origin_content[:600]}\n\n"
                f"用户补充的作用对象：{content.strip()[:200]}\n\n"
                f"{GENERAL_PLAN_CONTRACT}"
            )
        else:
            objective = f"{content.strip()[:600]}\n\n{GENERAL_PLAN_CONTRACT}"
        try:
            await self._agentteams.start_chat_planning(
                case_id=case_id,
                requester_ref=requester_ref,
                objective=objective,
                context_refs=refs,
            )
        except Exception as exc:  # noqa: BLE001 - 触发失败不得影响回复主流程
            logger.bind(case_id=case_id).warning(
                "AgentTeams chat execution trigger failed: {}", exc
            )
            return "none"
        if preferences.get("autonomy") == "autonomous":
            try:
                redis = self._redis_getter()
                await redis.sadd(AUTO_CONFIRM_CASES_KEY, case_id)
            except Exception as exc:  # noqa: BLE001
                logger.bind(case_id=case_id).warning(
                    "AgentTeams auto-confirm marking failed: {}", exc
                )
        logger.bind(case_id=case_id).info(
            "AgentTeams chat execution intent detected, planning started"
        )
        return "started"

    async def _emit_execution_clarify(
        self, case_id: str, content: str, *, round_no: int
    ) -> bool:
        """clarify 态：落 ``room.ask_user`` 选项式追问卡片（AskUserCard 渲染）。

        复用 phylo 域 intake questions 的同一条渲染与回答回收链路：前端把答案
        格式化为带【澄清回复】前缀的下一条 room.user_message 回到响应回路。
        卡片发送失败时返回 False，调用方回退到正常 Manager 回复。
        """
        brief = content.strip().replace("\n", " ")[:80]
        if round_no <= 1:
            question = (
                f"收到你的执行请求「{brief}」，但还缺少明确的作用对象（输入文件/数据）。"
                "请确认数据来源："
            )
            options = [
                "上传文件后执行（推荐）",
                "使用工作区已有数据（请回复文件名或路径）",
                "从公共数据库检索（请回复 accession 或关键词）",
                "先不执行，继续讨论方案",
            ]
        else:
            question = (
                "仍未拿到可执行的作用对象：请直接上传文件，或回复工作区文件名/路径"
                "（如 genes.xlsx），或公共数据库 accession/检索关键词。"
            )
            options = ["我去上传文件", "回复文件名或路径", "先不执行了"]
        try:
            await self._agentteams.post_case_evidence(
                case_id,
                work_item_id=CASE_LEVEL_WORK_ITEM_ID,
                event_type="room.ask_user",
                summary=question[:200],
                payload={
                    "content": "需要你先确认数据来源，再启动执行。",
                    "agent_id": self._manager_agent_id() or "bioops-manager",
                    "role": "bioops-manager",
                    "questions": [{"question": question, "options": options}],
                    "clarify_kind": CLARIFY_KIND_EXECUTION_OBJECT,
                    "round": round_no,
                    "origin_content": content.strip()[:600],
                },
            )
        except Exception as exc:  # noqa: BLE001 - 澄清卡片失败回退到正常回复
            logger.bind(case_id=case_id).warning(
                "AgentTeams execution clarify event failed: {}", exc
            )
            return False
        logger.bind(case_id=case_id).info(
            "AgentTeams execution intent unclear (no object), clarify round {} asked",
            round_no,
        )
        return True

    @classmethod
    def _is_execution_clarify_event(cls, event: dict[str, Any]) -> bool:
        if event.get("event_type") != "room.ask_user":
            return False
        payload = cls._payload_dict(event)
        inner_raw = payload.get("payload")
        inner = dict(inner_raw) if isinstance(inner_raw, dict) else {}
        return inner.get("clarify_kind") == CLARIFY_KIND_EXECUTION_OBJECT

    @classmethod
    def _execution_clarify_rounds(cls, events: list[dict[str, Any]]) -> int:
        """已发出的执行对象澄清轮次（按澄清卡片计数）。"""
        return sum(1 for event in events if cls._is_execution_clarify_event(event))

    @classmethod
    def _current_message_index(
        cls, events: list[dict[str, Any]], content: str
    ) -> int | None:
        target = content.strip()
        for index in range(len(events) - 1, -1, -1):
            event = events[index]
            if event.get("event_type") != "room.user_message":
                continue
            payload = cls._payload_dict(event)
            inner_raw = payload.get("payload")
            inner = dict(inner_raw) if isinstance(inner_raw, dict) else {}
            event_content = str(inner.get("content") or payload.get("summary") or "").strip()
            if event_content == target:
                return index
        return None

    @classmethod
    def _pending_execution_clarify(
        cls, events: list[dict[str, Any]], content: str
    ) -> bool:
        """当前发言是否处于“执行对象澄清待补全”状态。

        即：当前发言之前最近的一张执行对象澄清卡之后没有其他用户发言——
        当前发言就是对那张卡片的回答。
        """
        current_index = cls._current_message_index(events, content)
        scan = events[:current_index] if current_index is not None else events
        pending = False
        for event in scan:
            if event.get("event_type") == "room.user_message":
                pending = False
            elif cls._is_execution_clarify_event(event):
                pending = True
        return pending

    @classmethod
    def _pending_clarify_origin(
        cls, events: list[dict[str, Any]], content: str
    ) -> str | None:
        """取待补全澄清卡记录的原始执行请求（供补全后拼接执行目标）。"""
        current_index = cls._current_message_index(events, content)
        scan = events[:current_index] if current_index is not None else events
        for event in reversed(scan):
            if not cls._is_execution_clarify_event(event):
                continue
            payload = cls._payload_dict(event)
            inner_raw = payload.get("payload")
            inner = dict(inner_raw) if isinstance(inner_raw, dict) else {}
            origin = str(inner.get("origin_content") or "").strip()
            return origin or None
        return None

    async def _emit_route_decision(self, case_id: str, content: str) -> None:
        """落 ``room.route_decision`` 事件并写结构化日志；任何失败仅记 warning。

        只外显决策结果（路径 / 命中关键词 / Planner 评分 / 预计阶段 / 置信度），
        不改变意图路由与规划逻辑；卡片发送失败绝不影响执行触发主流程。
        """
        try:
            decision = build_route_decision(
                content,
                flow_registry=self._flow_registry,
                capability_registry=self._registry,
            )
        except Exception as exc:  # noqa: BLE001 - 决策构建失败不得影响执行触发
            logger.bind(case_id=case_id).warning("AgentTeams route decision build failed: {}", exc)
            return
        if decision is None:
            return
        try:
            await self._agentteams.post_case_evidence(
                case_id,
                work_item_id=CASE_LEVEL_WORK_ITEM_ID,
                event_type=ROUTE_DECISION_EVENT_TYPE,
                summary=summarize_route_decision(decision)[:200],
                payload=decision,
            )
        except Exception as exc:  # noqa: BLE001 - 卡片发送失败不得影响执行触发
            logger.bind(case_id=case_id).warning("AgentTeams route decision event failed: {}", exc)
            return
        logger.bind(case_id=case_id, route_decision=decision).info(
            "AgentTeams route decision: path={} flow={} lead_planner={} confidence={}",
            decision["path"],
            decision["flow_id"],
            decision["lead_planner"],
            decision["confidence"],
        )

    async def _set_typing(self, case_id: str, *, typing: bool) -> None:
        """落 ``room.typing`` 瞬时事件驱动房间页"正在输入"指示；失败仅记日志。

        typing 事件只由真正拿到锁并进入响应的流程发出——被锁丢弃的消息不会
        产生 typing 事件，因此不会残留永久"正在输入"态（前端另有新鲜度兜底）。
        """
        try:
            await self._agentteams.post_case_evidence(
                case_id,
                work_item_id=CASE_LEVEL_WORK_ITEM_ID,
                event_type="room.typing",
                summary="Manager 正在输入" if typing else "Manager 输入结束",
                payload={"typing": typing},
            )
        except Exception as exc:  # noqa: BLE001 - typing 指示失败不得影响响应主流程
            logger.bind(case_id=case_id).warning("AgentTeams room typing event failed: {}", exc)

    def _manager_agent_id(self) -> str | None:
        """Manager agent 选法：优先 agent-general（平台指定的通用 planner），
        否则回退到任意 planner_eligible 且可会诊的 agent。"""
        consultation_agents = self._registry.consultation_agents()
        if _PREFERRED_MANAGER_AGENT_ID in consultation_agents:
            return _PREFERRED_MANAGER_AGENT_ID
        capabilities = self._registry.agent_capabilities()
        for role in sorted(capabilities):
            capability = capabilities[role]
            if capability["planner_eligible"] and capability["agent_id"] in consultation_agents:
                return str(capability["agent_id"])
        return None

    async def _manager_preferences(self, requester_ref: str) -> dict[str, Any]:
        try:
            user_id = UUID(str(requester_ref))
        except (ValueError, TypeError, AttributeError):
            return {}
        try:
            result = await self._db.execute(
                select(UserModel.preferences).where(UserModel.id == user_id)
            )
            preferences = result.scalar_one_or_none()
        except Exception as exc:  # noqa: BLE001 - 偏好读取失败不阻断房间回复
            logger.bind(requester_ref=requester_ref).warning(
                "AgentTeams manager preferences lookup failed: {}", exc
            )
            return {}
        if not isinstance(preferences, dict):
            return {}
        agentteams = preferences.get("agentteams")
        return dict(agentteams) if isinstance(agentteams, dict) else {}

    @staticmethod
    def _payload_dict(event: dict[str, Any]) -> dict[str, Any]:
        payload = event.get("payload")
        return dict(payload) if isinstance(payload, dict) else {}

    @classmethod
    def _latest_message_context_refs(
        cls, events: list[dict[str, Any]], latest_content: str
    ) -> list[dict[str, Any]]:
        """取本条 room.user_message 事件携带的 context_refs（供意图判定与 prompt 复用）。"""
        for event in reversed(events):
            if event.get("event_type") != "room.user_message":
                continue
            payload = cls._payload_dict(event)
            inner_raw = payload.get("payload")
            inner = dict(inner_raw) if isinstance(inner_raw, dict) else {}
            event_content = str(inner.get("content") or payload.get("summary") or "").strip()
            if event_content != latest_content:
                continue
            refs = inner.get("context_refs")
            if not isinstance(refs, list):
                return []
            return [dict(ref) for ref in refs if isinstance(ref, dict)]
        return []

    @classmethod
    def _build_question(
        cls,
        case: dict[str, Any],
        events: list[dict[str, Any]],
        fallback_content: str,
        preferences: dict[str, Any] | None = None,
        system_note: str | None = None,
    ) -> str:
        preferences = preferences or {}
        latest_user_message = fallback_content.strip()
        matching_context_refs: list[str] = []
        for ref in cls._latest_message_context_refs(events, latest_user_message):
            location = str(ref.get("location") or ref.get("id") or "").strip()
            if location:
                matching_context_refs.append(location[:300])
        recent_lines: list[str] = []
        for event in events[-_CONTEXT_EVENT_SUMMARY_LINES:]:
            payload = cls._payload_dict(event)
            summary = str(payload.get("summary") or "").strip()
            event_type = str(event.get("event_type") or "")
            line = f"- {event_type}: {summary}" if summary else f"- {event_type}"
            recent_lines.append(line[:200])
        context_block = "\n".join(recent_lines) or "- （暂无历史动态）"
        refs_block = "、".join(matching_context_refs) or "（无显式文件引用）"
        manager_name = str(preferences.get("managerName") or "Manager")[:24]
        style = {
            "friendly": "亲切友好：语气自然、有温度，但不使用夸张措辞",
            "concise": "极简高效：先给结论和下一步，减少背景铺陈",
            "professional": "正式专业：表述严谨、结构清晰、术语准确",
        }.get(str(preferences.get("communicationStyle")), "正式专业：表述严谨、结构清晰、术语准确")
        language = "English" if preferences.get("language") == "en-US" else "中文"
        autonomy = (
            "自主模式：对低风险只读分析可主动给出下一步并推进；"
            "真实计算、写入、费用、提交和审批仍必须遵守系统安全闸门"
            if preferences.get("autonomy") == "autonomous"
            else "谨慎模式：涉及执行选择或信息不足时优先说明影响并请求用户确认"
        )
        return (
            "你在 AgentTeams 协作房间中扮演 Manager，直接回答请求人的最新发言。"
            "必须以‘请求人最新发言’为唯一当前问题，不得重复回答更早的问题。"
            "用中文简洁回答；若问题涉及执行中的任务，结合 Case 状态说明进展。"
            "若用户要求基于文件绘图、运行分析或生成产物，必须明确这是计算执行请求，"
            "不得假装已经产出结果；应说明当前 Case 是否与该目标一致，以及下一步会进入"
            "规划、确认、执行和产物交付中的哪个阶段。\n"
            "澄清协议（强制）：若最新发言缺少继续推进所需的关键信息（如输入数据形式、"
            "物种与参考基因组、样本分组与生物学重复、分析目标、交付物），禁止只在 "
            "conclusion 正文里罗列编号问题；必须在 JSON 信封的 ask_user 字段输出结构化"
            "问题数组（最多 5 个），每项形如 "
            '{"question":"...","options":["候选 A","候选 B"]}，options 给 2-4 个可点选'
            "候选（有推荐项时放第一位并以（推荐）标注），无法预设选项的问题 options 留空数组。"
            "使用 ask_user 时 conclusion 只写一句简短引导语，不得重复问题正文；"
            "信息充分、无需澄清时 ask_user 必须留空数组。\n"
            + (f"{system_note}\n" if system_note else "")
            + f"全局回复偏好：称呼自己为「{manager_name}」；沟通语言为{language}；"
            f"沟通风格为{style}；执行偏好为{autonomy}。\n"
            f"Case 目标：{str(case.get('intent') or '')[:200]}\n"
            f"Case 当前状态：{str(case.get('status') or '')}\n"
            f"最近房间动态：\n{context_block}\n"
            f"本条发言引用文件：{refs_block}\n"
            f"请求人最新发言：{latest_user_message}"
        )
