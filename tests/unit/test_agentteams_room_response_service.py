"""房间 Manager 响应回路测试：锁去重、终态跳过、LLM 失败容错、manager agent 选法。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from omichub.application.services.agent_consultation_service import (
    AgentConsultationService,
    ConsultationEnvelope,
)
from omichub.application.services.agentteams_capability_registry import (
    AgentTeamsCapabilityRegistry,
)
from omichub.application.services.agentteams_room_response_service import (
    ROOM_RESPONSE_LOCK_KEY_PREFIX,
    AgentTeamsRoomResponseService,
)

_STATUS_LINES = {
    key: [key]
    for key in (
        "recruited",
        "queued",
        "running",
        "reviewing",
        "succeeded",
        "failed",
        "awaiting_input",
    )
}


def _agent_config(agent_id: str, *, planner_eligible: bool = False) -> dict:
    return {
        "agent_id": agent_id,
        "name": agent_id,
        "features": {
            "internal_case_role": agent_id,
            "agentteams": {
                "category": "expert",
                "recruitable": True,
                "planner_eligible": planner_eligible,
                "execution_modes": ["readonly_consultation"],
            },
            "persona": {"status_lines": _STATUS_LINES},
        },
    }


class FakeAbilityCatalog:
    def __init__(self, agent_ids: set[str]) -> None:
        self._agent_ids = agent_ids

    def all(self) -> dict[str, dict]:
        return {agent_id: {} for agent_id in self._agent_ids}


def _registry(*agent_ids: str, planner_ids: set[str] | None = None) -> AgentTeamsCapabilityRegistry:
    planners = planner_ids or set()
    return AgentTeamsCapabilityRegistry(
        ability_catalog=FakeAbilityCatalog(set(agent_ids)),
        agent_configs=[
            _agent_config(agent_id, planner_eligible=agent_id in planners)
            for agent_id in agent_ids
        ],
    )


class FakeRedis:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.set_calls: list[tuple[object, ...]] = []
        self.release_calls: list[tuple[object, ...]] = []

    async def set(self, *args, **kwargs):
        self.set_calls.append((*args, kwargs))
        return self.acquired

    async def eval(self, *args):
        self.release_calls.append(args)
        return 1


def _service(
    *,
    agentteams: SimpleNamespace,
    registry: AgentTeamsCapabilityRegistry,
    redis: FakeRedis,
) -> AgentTeamsRoomResponseService:
    return AgentTeamsRoomResponseService(
        SimpleNamespace(),
        agentteams=agentteams,
        registry=registry,
        redis_getter=lambda: redis,
    )


def _agentteams(
    *,
    status: str = "executing",
    events: list[dict] | None = None,
    case_overrides: dict | None = None,
) -> SimpleNamespace:
    case = {"case_id": "bioops_1", "intent": "RNA-seq 差异分析", "status": status}
    case.update(case_overrides or {})
    return SimpleNamespace(
        get_case=AsyncMock(return_value=case),
        get_case_events=AsyncMock(return_value={"events": events or [], "next_cursor": None}),
        post_case_evidence=AsyncMock(return_value={"event_id": "evt-reply"}),
        start_chat_planning=AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_respond_records_manager_reply_evidence(monkeypatch) -> None:
    events = [
        {
            "event_type": "room.user_message",
            "payload": {"summary": "旧问题", "payload": {"actor": "user-a", "content": "旧问题"}},
        },
        {
            "event_type": "room.user_message",
            "payload": {
                "summary": "质控过了吗？",
                "payload": {"actor": "user-a", "content": "质控过了吗？"},
            },
        },
    ]
    agentteams = _agentteams(events=events)
    redis = FakeRedis()
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="质控已通过，可以交付。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams,
        registry=_registry("agent-general"),
        redis=redis,
    ).respond("bioops_1", "user-a", "质控过了吗？")

    assert result == {"status": "responded"}
    assert run.await_args.kwargs["agent_id"] == "agent-general"
    assert run.await_args.kwargs["capability"] == "interpretation"
    assert "质控过了吗？" in run.await_args.kwargs["question"]
    assert "RNA-seq 差异分析" in run.await_args.kwargs["question"]
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert event_types == ["room.typing", "room.agent_message", "room.typing"]
    typing_payloads = [
        call.kwargs["payload"]
        for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.typing"
    ]
    assert typing_payloads == [{"typing": True}, {"typing": False}]
    reply_call = agentteams.post_case_evidence.await_args_list[1]
    assert reply_call.kwargs["work_item_id"] == "case"
    assert reply_call.kwargs["payload"]["content"] == "质控已通过，可以交付。"
    assert reply_call.kwargs["payload"]["agent_id"] == "agent-general"
    assert reply_call.kwargs["payload"]["role"] == "bioops-manager"
    assert len(redis.release_calls) == 1


@pytest.mark.asyncio
async def test_flow_manager_reply_exposes_persisted_handoff_failure(monkeypatch) -> None:
    agentteams = _agentteams(
        events=[
            _user_message_event("请开始单细胞分析"),
            {
                "event_type": "case.handoff_failed",
                "payload": {"reason": "agent-scrna-upstream 凭证未配置"},
            },
        ],
        case_overrides={"flow_id": "scrna"},
    )
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="我会先整理分析步骤。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams,
        registry=_registry("agent-general"),
        redis=FakeRedis(),
    ).respond("bioops_1", "user-a", "请开始单细胞分析")

    assert result == {"status": "responded"}
    reply_call = next(
        call
        for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.agent_message"
    )
    assert "agent-scrna-upstream 凭证未配置" in reply_call.kwargs["payload"]["content"]
    assert "方案咨询" in reply_call.kwargs["payload"]["content"]


@pytest.mark.asyncio
async def test_flow_manager_reply_cannot_claim_handoff_before_started(monkeypatch) -> None:
    agentteams = _agentteams(
        events=[_user_message_event("请开始单细胞分析")],
        case_overrides={"flow_id": "scrna"},
    )
    run = AsyncMock(
        return_value=ConsultationEnvelope(
            conclusion="已交接给专项 Agent，任务已派发并已开始分析。"
        )
    )
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    await _service(
        agentteams=agentteams,
        registry=_registry("agent-general"),
        redis=FakeRedis(),
    ).respond("bioops_1", "user-a", "请开始单细胞分析")

    reply_call = next(
        call
        for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.agent_message"
    )
    content = reply_call.kwargs["payload"]["content"]
    assert "已交接" not in content
    assert "已派发" not in content
    assert "已开始分析" not in content
    assert "待确认交接" in content


@pytest.mark.asyncio
async def test_respond_projects_reasoning_and_text_deltas_before_final_reply(monkeypatch) -> None:
    agentteams = _agentteams(events=[_user_message_event("请说明这个结果")])

    async def run_consultation(_service, **kwargs):
        projector = kwargs["on_event"]
        await projector({"type": "worker_reasoning_delta", "content": "先核对输入。"})
        await projector({"type": "worker_text_delta", "content": "结果已核对。"})
        return ConsultationEnvelope(
            conclusion="结果已核对。",
            recommendations=["可继续进行下游分析。"],
            risks=["样本量较小时需谨慎解释。"],
        )

    monkeypatch.setattr(AgentConsultationService, "run_consultation", run_consultation)

    result = await _service(
        agentteams=agentteams,
        registry=_registry("agent-general"),
        redis=FakeRedis(),
    ).respond("bioops_1", "user-a", "请说明这个结果")

    assert result == {"status": "responded"}
    calls = agentteams.post_case_evidence.await_args_list
    event_types = [call.kwargs["event_type"] for call in calls]
    assert event_types == ["room.typing", "room.agent_stream", "room.agent_stream", "room.agent_message", "room.typing"]
    stream_calls = [call for call in calls if call.kwargs["event_type"] == "room.agent_stream"]
    assert [call.kwargs["payload"]["channel"] for call in stream_calls] == ["reasoning", "content"]
    assert stream_calls[0].kwargs["payload"]["delta"] == "先核对输入。"
    assert stream_calls[1].kwargs["payload"]["delta"] == "结果已核对。"
    final_payload = next(call.kwargs["payload"] for call in calls if call.kwargs["event_type"] == "room.agent_message")
    assert final_payload["stream_id"] == stream_calls[0].kwargs["payload"]["stream_id"]
    assert final_payload["manager_report"] == {
        "conclusion": "结果已核对。",
        "recommendations": ["可继续进行下游分析。"],
        "evidence_refs": [],
        "risks": ["样本量较小时需谨慎解释。"],
        "hard_gate": None,
        "proposed_submission": None,
    }


@pytest.mark.asyncio
async def test_readonly_file_request_routes_to_tool_execution_without_planning(monkeypatch) -> None:
    events = [
        _user_message_event("读取 result.csv 并判断是否为空"),
    ]
    agentteams = _agentteams(
        status="received",
        events=events,
        case_overrides={
            "work_items": [],
        },
    )
    run = AsyncMock(
        return_value=ConsultationEnvelope(
            conclusion="已读取 result.csv，文件包含 3 行数据，未发现空内容。",
            evidence_refs=["file:result.csv"],
        )
    )
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams,
        registry=_registry("agent-general"),
        redis=FakeRedis(),
    ).respond("bioops_1", "user-a", "读取 result.csv 并判断是否为空")

    assert result == {"status": "responded"}
    agentteams.start_chat_planning.assert_not_awaited()
    run.assert_awaited_once()
    assert run.await_args.kwargs["requested_tools"] == ["workspace_read", "readonly_review"]
    assert run.await_args.kwargs["execution_mode"] == "readonly_consultation"
    assert run.await_args.kwargs["on_event"] is not None
    route = next(
        call for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.route_decision"
    )
    assert route.kwargs["payload"]["execution_path"] == "agentteams_tool_execution"
    reply = next(
        call for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.agent_message"
    )
    assert reply.kwargs["payload"]["tool_result_refs"] == ["file:result.csv"]
    assert reply.kwargs["payload"]["stream_id"]
    assert reply.kwargs["payload"]["manager_report"]["conclusion"] == "已读取 result.csv，文件包含 3 行数据，未发现空内容。"


@pytest.mark.asyncio
async def test_respond_skipped_when_lock_held() -> None:
    agentteams = _agentteams()
    redis = FakeRedis(acquired=False)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=redis
    ).respond("bioops_1", "user-a", "hello")

    assert result == {"status": "skipped_locked"}
    agentteams.get_case.assert_not_awaited()
    agentteams.post_case_evidence.assert_not_awaited()
    assert redis.release_calls == []


def test_build_question_keeps_task_message_when_newer_room_message_exists() -> None:
    events = [
        {
            "event_type": "room.user_message",
            "payload": {
                "summary": "帮我做系统发育树",
                "payload": {
                    "content": "帮我做系统发育树",
                    "context_refs": [
                        {
                            "kind": "file",
                            "id": "tree-1",
                            "location": "workspace/chat-uploads/example.treefile",
                        }
                    ],
                },
            },
        },
        {
            "event_type": "room.user_message",
            "payload": {"summary": "这是更新的问题", "payload": {"content": "这是更新的问题"}},
        },
    ]

    question = AgentTeamsRoomResponseService._build_question(
        {"intent": "介绍 Manager", "status": "planning_running"},
        events,
        "帮我做系统发育树",
    )

    assert "请求人最新发言：帮我做系统发育树" in question
    assert "workspace/chat-uploads/example.treefile" in question
    assert "必须以‘请求人最新发言’为唯一当前问题" in question


def test_build_question_applies_global_manager_preferences_without_skipping_gates() -> None:
    question = AgentTeamsRoomResponseService._build_question(
        {"intent": "数据质控", "status": "planning_running"},
        [],
        "继续处理",
        {
            "managerName": "小 O",
            "communicationStyle": "concise",
            "autonomy": "autonomous",
            "language": "en-US",
        },
    )

    assert "称呼自己为「小 O」" in question
    assert "沟通语言为English" in question
    assert "极简高效" in question
    assert "自主模式" in question
    assert "真实计算、写入、费用、提交和审批仍必须遵守系统安全闸门" in question


@pytest.mark.asyncio
async def test_respond_also_answers_for_terminal_case(monkeypatch) -> None:
    """终态 Case（已取消/已关闭）发言仍应得到 Manager 只读回复。"""
    agentteams = _agentteams(status="closed")
    run = AsyncMock(
        return_value=SimpleNamespace(conclusion="这个 Case 已关闭，但可以继续解答问题")
    )
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", "还在吗")

    assert result == {"status": "responded"}
    run.assert_awaited_once()


@pytest.mark.asyncio
async def test_respond_llm_failure_only_logs_and_releases_lock(monkeypatch) -> None:
    agentteams = _agentteams()
    redis = FakeRedis()
    monkeypatch.setattr(
        AgentConsultationService,
        "run_consultation",
        AsyncMock(side_effect=RuntimeError("LLM 不可用")),
    )

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=redis
    ).respond("bioops_1", "user-a", "hello")

    assert result == {"status": "failed"}
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert event_types == ["room.typing", "room.typing"]
    typing_payloads = [
        call.kwargs["payload"] for call in agentteams.post_case_evidence.await_args_list
    ]
    assert typing_payloads == [{"typing": True}, {"typing": False}]
    assert len(redis.release_calls) == 1


@pytest.mark.asyncio
async def test_respond_skipped_without_manager_agent(monkeypatch) -> None:
    agentteams = _agentteams()
    run = AsyncMock()
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-rnaseq"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", "hello")

    assert result == {"status": "skipped_no_manager"}
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_manager_agent_falls_back_to_planner_eligible(monkeypatch) -> None:
    agentteams = _agentteams()
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="好的。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams,
        registry=_registry("agent-rnaseq", "agent-code", planner_ids={"agent-code"}),
        redis=FakeRedis(),
    ).respond("bioops_1", "user-a", "hello")

    assert result == {"status": "responded"}
    assert run.await_args.kwargs["agent_id"] == "agent-code"


def test_lock_key_namespaced_per_case() -> None:
    assert ROOM_RESPONSE_LOCK_KEY_PREFIX == "agentteams:room-response:lock:"


@pytest.mark.asyncio
async def test_respond_posts_ask_user_card_when_manager_requests_clarification(monkeypatch) -> None:
    """Manager 信封携带 ask_user 问题时落 room.ask_user 事件，而非纯文本回复。"""
    agentteams = _agentteams(status="received")
    run = AsyncMock(
        return_value=ConsultationEnvelope(
            conclusion="启动规划前需要你确认几个关键信息。",
            ask_user=[
                {
                    "question": "输入数据是计数矩阵还是 FASTQ？",
                    "options": ["已有计数矩阵", "从 FASTQ 开始"],
                },
                {"question": "物种与参考基因组版本？", "options": []},
            ],
        )
    )
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    # 注意：消息文本不得含执行动词，否则会先命中 clarify 中间态而不走 LLM 会诊。
    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", "想确认一下这个 Case 的分组设置")

    assert result == {"status": "asked"}
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert event_types == ["room.typing", "room.ask_user", "room.typing"]
    ask_call = agentteams.post_case_evidence.await_args_list[1]
    assert ask_call.kwargs["work_item_id"] == "case"
    assert ask_call.kwargs["payload"]["content"] == "启动规划前需要你确认几个关键信息。"
    assert ask_call.kwargs["payload"]["role"] == "bioops-manager"
    assert ask_call.kwargs["payload"]["questions"] == [
        {"question": "输入数据是计数矩阵还是 FASTQ？", "options": ["已有计数矩阵", "从 FASTQ 开始"]},
        {"question": "物种与参考基因组版本？", "options": []},
    ]
    assert ask_call.kwargs["payload"]["manager_report"]["conclusion"] == "启动规划前需要你确认几个关键信息。"


def test_build_question_instructs_structured_ask_user() -> None:
    question = AgentTeamsRoomResponseService._build_question(
        {"intent": "RNA-seq 数据分析", "status": "received"},
        [],
        "rna-seq 数据分析",
    )

    assert "ask_user" in question
    assert "禁止只在 conclusion 正文里罗列编号问题" in question


_EXECUTION_EVENTS = [
    {
        "event_type": "room.user_message",
        "payload": {
            "summary": "对这个 treefile 进行可视化并解释",
            "payload": {
                "actor": "user-a",
                "content": "对这个 treefile 进行可视化并解释",
                "context_refs": [
                    {
                        "kind": "file",
                        "id": "tree-1",
                        "location": "workspace/chat-uploads/example.treefile",
                    }
                ],
            },
        },
    }
]


@pytest.mark.asyncio
async def test_execution_intent_starts_chat_planning_without_duplicate_manager_reply(monkeypatch) -> None:
    """执行意图进入领域规划后，不再让 Manager 追加重复澄清。"""
    agentteams = _agentteams(status="received", events=_EXECUTION_EVENTS)
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="已为你启动可视化流水线。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", "对这个 treefile 进行可视化并解释")

    assert result == {"status": "planning_started"}
    agentteams.start_chat_planning.assert_awaited_once()
    trigger = agentteams.start_chat_planning.await_args.kwargs
    assert trigger["case_id"] == "bioops_1"
    assert trigger["requester_ref"] == "user-a"
    assert "对这个 treefile 进行可视化并解释" in trigger["objective"]
    assert "work_items" in trigger["objective"]
    assert trigger["context_refs"] == [
        {"kind": "file", "id": "tree-1", "location": "workspace/chat-uploads/example.treefile"}
    ]
    run.assert_not_awaited()
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert event_types == ["room.route_decision"]
    route_call = agentteams.post_case_evidence.await_args_list[0]
    assert route_call.kwargs["work_item_id"] == "case"
    decision = route_call.kwargs["payload"]
    # “treefile 可视化”走通用 Overdrive 路径，由 Manager 自动选择，不要求用户选 Agent。
    assert decision["path"] == "overdrive"
    assert decision["flow_id"] is None
    assert decision["confidence"] == "high"
    assert "options" not in decision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "status", "case_overrides"),
    [
        # 非执行意图
        ("你好", "received", {}),
        # 有 flow_id 的 Case 走人工审批链路，绝不自动触发
        ("对这个 treefile 进行可视化并解释", "received", {"flow_id": "rna_seq"}),
        # 状态非 received
        ("对这个 treefile 进行可视化并解释", "planning_running", {}),
        # 已有 plan-01 工作项
        (
            "对这个 treefile 进行可视化并解释",
            "received",
            {"work_items": [{"work_item_id": "plan-01"}]},
        ),
    ],
)
async def test_execution_intent_not_triggered_when_gates_fail(
    monkeypatch, content: str, status: str, case_overrides: dict
) -> None:
    agentteams = _agentteams(status=status, events=_EXECUTION_EVENTS, case_overrides=case_overrides)
    monkeypatch.setattr(
        AgentConsultationService,
        "run_consultation",
        AsyncMock(return_value=ConsultationEnvelope(conclusion="好的。")),
    )

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", content)

    assert result == {"status": "responded"}
    agentteams.start_chat_planning.assert_not_awaited()
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert "room.route_decision" not in event_types


@pytest.mark.asyncio
async def test_execution_trigger_failure_does_not_break_manager_reply(monkeypatch) -> None:
    agentteams = _agentteams(status="received", events=_EXECUTION_EVENTS)
    agentteams.start_chat_planning = AsyncMock(side_effect=RuntimeError("bridge down"))
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="稍后为你处理。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", "对这个 treefile 进行可视化并解释")

    assert result == {"status": "responded"}
    assert "计划冻结后会在房间内请求你确认" not in run.await_args.kwargs["question"]


# ---- O6 阶段 2：clarify 中间态（执行动词成立但无作用对象）----


def _user_message_event(content: str, context_refs: list[dict] | None = None) -> dict:
    inner: dict = {"actor": "user-a", "content": content}
    if context_refs:
        inner["context_refs"] = context_refs
    return {
        "event_type": "room.user_message",
        "payload": {"summary": content[:80], "payload": inner},
    }


def _clarify_card_event(origin_content: str, round_no: int) -> dict:
    return {
        "event_type": "room.ask_user",
        "payload": {
            "summary": "请确认数据来源",
            "payload": {
                "content": "需要你先确认数据来源，再启动执行。",
                "role": "bioops-manager",
                "questions": [{"question": "请确认数据来源：", "options": ["上传文件"]}],
                "clarify_kind": "execution_object",
                "round": round_no,
                "origin_content": origin_content,
            },
        },
    }


def test_unstarted_flow_handoff_language_is_gated() -> None:
    reply = "我已交接给专项 Agent，任务已派发并已开始分析。"

    guarded = AgentTeamsRoomResponseService._gate_unstarted_handoff_language(reply)

    assert "已交接" not in guarded
    assert "已派发" not in guarded
    assert "已开始分析" not in guarded
    assert "待确认交接" in guarded


def test_handoff_failure_reason_is_read_from_persisted_event() -> None:
    reason = AgentTeamsRoomResponseService._handoff_failure_reason(
        [
            {"event_type": "room.user_message", "payload": {}},
            {
                "event_type": "case.handoff_failed",
                "payload": {"reason": "agent-scrna-upstream 凭证未配置"},
            },
        ]
    )

    assert reason == "agent-scrna-upstream 凭证未配置"


@pytest.mark.asyncio
async def test_clarify_intent_emits_option_card_without_route_decision(monkeypatch) -> None:
    """“帮我做差异分析”（无附件）→ 选项式澄清卡；不触发规划、不推 route_decision、不跑 LLM。"""
    events = [_user_message_event("帮我做差异分析")]
    agentteams = _agentteams(status="received", events=events)
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="好的。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", "帮我做差异分析")

    assert result == {"status": "asked"}
    run.assert_not_awaited()
    agentteams.start_chat_planning.assert_not_awaited()
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert event_types == ["room.ask_user"]
    payload = agentteams.post_case_evidence.await_args_list[0].kwargs["payload"]
    assert payload["clarify_kind"] == "execution_object"
    assert payload["round"] == 1
    assert payload["origin_content"] == "帮我做差异分析"
    assert "差异分析" in payload["questions"][0]["question"]
    assert len(payload["questions"][0]["options"]) >= 3


@pytest.mark.asyncio
async def test_clarify_reply_with_object_auto_starts_execution(monkeypatch) -> None:
    """澄清回复补全作用对象（文件名）→ 自动转 execute，沿用原始请求拼接执行目标。"""
    reply = "【澄清回复】\n1. 请确认数据来源：使用工作区已有数据 genes.xlsx"
    events = [
        _user_message_event("帮我做差异分析"),
        _clarify_card_event("帮我做差异分析", 1),
        _user_message_event(reply),
    ]
    agentteams = _agentteams(status="received", events=events)
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="已为你启动差异分析流水线。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", reply)

    assert result == {"status": "planning_started"}
    agentteams.start_chat_planning.assert_awaited_once()
    run.assert_not_awaited()
    trigger = agentteams.start_chat_planning.await_args.kwargs
    assert "帮我做差异分析" in trigger["objective"]
    assert "genes.xlsx" in trigger["objective"]
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    # 自动转 execute 后按既有链路外显路由决策卡
    assert "room.route_decision" in event_types
    assert "room.ask_user" not in event_types
    answer_call = next(
        call
        for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.ask_user_answered"
    )
    assert answer_call.kwargs["payload"]["answer"] == reply
    assert answer_call.kwargs["payload"]["round"] == 1


@pytest.mark.asyncio
async def test_clarify_answer_is_recorded_before_second_round(monkeypatch) -> None:
    """没有作用对象的澄清回复也要进入 Case 的已收集答案清单。"""
    reply = "【澄清回复】\n1. 请确认数据来源：我去上传文件"
    events = [
        _user_message_event("帮我做差异分析"),
        _clarify_card_event("帮我做差异分析", 1),
        _user_message_event(reply),
    ]
    agentteams = _agentteams(status="received", events=events)
    monkeypatch.setattr(
        AgentConsultationService,
        "run_consultation",
        AsyncMock(return_value=ConsultationEnvelope(conclusion="好的。")),
    )

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", reply)

    assert result == {"status": "asked"}
    answer_call = next(
        call
        for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.ask_user_answered"
    )
    assert answer_call.kwargs["payload"]["question"] == "请确认数据来源："
    assert answer_call.kwargs["payload"]["answer"] == reply


@pytest.mark.asyncio
async def test_clarify_reply_without_object_advances_to_round_two(monkeypatch) -> None:
    """结构化答复仍未给出对象 → 发出第 2 轮澄清卡。"""
    reply = "【澄清回复】\n1. 请确认数据来源：使用工作区已有数据（请回复文件名或路径）"
    events = [
        _user_message_event("帮我做差异分析"),
        _clarify_card_event("帮我做差异分析", 1),
        _user_message_event(reply),
    ]
    agentteams = _agentteams(status="received", events=events)
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="好的。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", reply)

    assert result == {"status": "asked"}
    run.assert_not_awaited()
    agentteams.start_chat_planning.assert_not_awaited()
    ask_call = next(
        call
        for call in agentteams.post_case_evidence.await_args_list
        if call.kwargs["event_type"] == "room.ask_user"
    )
    payload = ask_call.kwargs["payload"]
    assert payload["round"] == 2


@pytest.mark.asyncio
async def test_clarify_exhausted_after_two_rounds_degrades_to_chat(monkeypatch) -> None:
    """2 轮追问后仍无对象 → 降级纯对话，Manager 说明原因，不触发规划。"""
    content = "再帮我汇总一下吧"
    events = [
        _user_message_event("帮我做差异分析"),
        _clarify_card_event("帮我做差异分析", 1),
        _user_message_event("【澄清回复】\n1. 请确认数据来源：使用工作区已有数据"),
        _clarify_card_event("帮我做差异分析", 2),
        _user_message_event(content),
    ]
    agentteams = _agentteams(status="received", events=events)
    run = AsyncMock(
        return_value=ConsultationEnvelope(conclusion="缺少输入数据，暂时无法直接执行。")
    )
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", content)

    assert result == {"status": "responded"}
    agentteams.start_chat_planning.assert_not_awaited()
    question = run.await_args.kwargs["question"]
    assert "暂时无法直接执行" in question
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert "room.route_decision" not in event_types
    assert "room.ask_user" not in event_types


@pytest.mark.asyncio
async def test_clarify_opt_out_reply_falls_back_to_chat(monkeypatch) -> None:
    """用户在澄清中选择“先不执行”→ 纯对话，不再追问。"""
    reply = "【澄清回复】\n1. 请确认数据来源：先不执行，继续讨论方案"
    events = [
        _user_message_event("帮我做差异分析"),
        _clarify_card_event("帮我做差异分析", 1),
        _user_message_event(reply),
    ]
    agentteams = _agentteams(status="received", events=events)
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="好的，先讨论方案。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", reply)

    assert result == {"status": "responded"}
    run.assert_awaited_once()
    agentteams.start_chat_planning.assert_not_awaited()
    event_types = [call.kwargs["event_type"] for call in agentteams.post_case_evidence.await_args_list]
    assert "room.ask_user" not in event_types
    assert "room.route_decision" not in event_types


@pytest.mark.asyncio
async def test_non_execution_ask_user_card_does_not_arm_pending_clarify(monkeypatch) -> None:
    """Manager LLM 产出的普通澄清卡（无 clarify_kind 标记）不计入执行对象追问：
    其后的纯文件名回复不应被误判为补全对象而触发执行。"""
    reply = "result.csv"
    events = [
        _user_message_event("想确认一下分组"),
        {
            "event_type": "room.ask_user",
            "payload": {
                "summary": "输入数据是计数矩阵还是 FASTQ？",
                "payload": {
                    "content": "需要确认。",
                    "role": "bioops-manager",
                    "questions": [{"question": "输入数据是计数矩阵还是 FASTQ？", "options": []}],
                },
            },
        },
        _user_message_event(reply),
    ]
    agentteams = _agentteams(status="received", events=events)
    run = AsyncMock(return_value=ConsultationEnvelope(conclusion="收到。"))
    monkeypatch.setattr(AgentConsultationService, "run_consultation", run)

    result = await _service(
        agentteams=agentteams, registry=_registry("agent-general"), redis=FakeRedis()
    ).respond("bioops_1", "user-a", reply)

    assert result == {"status": "responded"}
    agentteams.start_chat_planning.assert_not_awaited()


def test_celery_task_delegates_to_async_impl(monkeypatch) -> None:
    import omichub.infrastructure.celery_app.tasks.agentteams as task_module

    calls: list[tuple[str, str, str]] = []

    async def fake_impl(case_id: str, requester_ref: str, content: str) -> dict[str, str]:
        calls.append((case_id, requester_ref, content))
        return {"status": "responded"}

    monkeypatch.setattr(task_module, "_respond_to_room_message", fake_impl)

    result = task_module.respond_to_room_message("bioops_1", "user-a", "hello")

    assert result == {"status": "responded"}
    assert calls == [("bioops_1", "user-a", "hello")]
