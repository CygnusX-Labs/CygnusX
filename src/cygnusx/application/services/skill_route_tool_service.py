"""`skill_route` builtin 工具适配器。"""

from __future__ import annotations

import json
from typing import Any

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.parallel_subagent_service import ParallelSubAgentService
from cygnusx.application.services.skill_route_service import SkillRouteService
from cygnusx.core.exceptions import BusinessError
from cygnusx.infrastructure.ai_provider.openai_compatible import ChatChunk
from cygnusx.infrastructure.config.prompt_loader import get_prompt


def _parse_scout_answer(answer: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """解析 scout 的 JSON，保留原始答复便于排查模型偶发格式错误。"""
    raw = answer.strip()
    start = raw.find("{")
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(raw[start:])
            if isinstance(payload, dict):
                payload.setdefault(
                    "candidates",
                    [
                        {key: value for key, value in item.items() if key != "skill_body"}
                        for item in candidates
                    ],
                )
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "matched": False,
        "skill_id": None,
        "confidence": 0.0,
        "reason": "Skill scout 未返回可解析的结构化审查结果",
        "candidates": [
            {key: value for key, value in item.items() if key != "skill_body"}
            for item in candidates
        ],
        "scout_answer": answer[:4000],
    }


def _compact_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """候选瘦身：只保留主 Agent 决策所需的元数据，防止 3KB llm_payload 截断。"""
    compact: list[dict[str, Any]] = []
    for item in candidates:
        compact.append(
            {
                "skill_id": item.get("skill_id"),
                "name": item.get("name"),
                "metadata_score": item.get("metadata_score"),
                "description": str(item.get("description") or "")[:80],
                "version": item.get("version"),
                "source": item.get("source"),
                "body_loaded": item.get("body_loaded"),
                "body_truncated": item.get("body_truncated"),
            }
        )
    return compact


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    """统一收尾：候选瘦身、长字段截断、生成 summary 兜底。"""
    result["candidates"] = _compact_candidates(
        [item for item in (result.get("candidates") or []) if isinstance(item, dict)]
    )
    reason = str(result.get("reason") or "")
    if len(reason) > 200:
        result["reason"] = reason[:200] + "……"
    if result.get("matched") and result.get("skill_id"):
        result["summary"] = (
            f"命中 Skill：{result['skill_id']}（置信度 {result.get('confidence') or 0:.2f}）"
        )
    else:
        result["summary"] = f"未命中合适 Skill：{result.get('reason') or '无覆盖候选'}"
    return result


SKILL_ROUTE_CARD_LABEL = "Skill 路由审查"
SKILL_ROUTE_SCOUT_AGENT_ID = "skill-route-scout"


def skill_route_started_chunk(tool_call_id: str, query: str) -> ChatChunk:
    """子 Agent 审查启动事件：任务已交给子 Agent，主 Agent 等待结果。"""
    return ChatChunk(
        type="subagents",
        metadata={
            "phase": "started",
            "tool_call_id": tool_call_id,
            "label": SKILL_ROUTE_CARD_LABEL,
            "tasks": [
                {
                    "index": 1,
                    "agent_id": SKILL_ROUTE_SCOUT_AGENT_ID,
                    "task": f"只读检索并审查 Skill：{query}"[:120],
                }
            ],
        },
    )


def skill_route_aggregated_chunk(tool_call_id: str, bridge_result: dict[str, Any]) -> ChatChunk:
    """子 Agent 审查完成事件：透出命中/未命中结论，驱动卡片进入完成态。"""
    route_llm = bridge_result.get("llm_payload") or {}
    route_ok = bool(bridge_result.get("success")) and not bridge_result.get("is_error")
    if route_llm.get("matched") and route_llm.get("skill_id"):
        route_summary = str(route_llm.get("summary") or "")[:120]
    else:
        route_summary = f"未命中合适 Skill：{str(route_llm.get('reason') or '')[:80]}"
    return ChatChunk(
        type="subagents",
        metadata={
            "phase": "aggregated",
            "tool_call_id": tool_call_id,
            "label": SKILL_ROUTE_CARD_LABEL,
            "success": route_ok,
            "summary": route_summary,
            "progress": [
                {
                    "index": 1,
                    "agent_id": SKILL_ROUTE_SCOUT_AGENT_ID,
                    "status": "ok" if route_ok else "failed",
                }
            ],
        },
    )


class SkillRouteToolService:
    """提供只读 Skill 路由，复用 Router 风格的单子 Agent 审查。"""

    async def route(
        self,
        *,
        query: str = "",
        limit: int = 5,
        context: ToolInvocationContext | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if context is None or not context.user_id or not context.session_id:
            raise BusinessError("Skill 路由需要受控的会话调用上下文")
        candidates = await SkillRouteService().prepare_candidates(
            query=query, db=context.db, limit=limit
        )
        if not candidates:
            return _finalize(
                {
                    "matched": False,
                    "skill_id": None,
                    "confidence": 0.0,
                    "reason": "没有通过元数据预筛的候选 Skill",
                    "candidates": [],
                }
            )

        prompt = get_prompt("agents.skill_route", "")
        candidate_payload = json.dumps(candidates, ensure_ascii=False)
        task = (
            f"{prompt}\n\n"
            "## 用户任务\n"
            f"{query}\n\n"
            "## L1 预筛候选及其完整 SKILL.md 正文\n"
            f"{candidate_payload}\n\n"
            "请只输出一个 JSON 对象，不要 Markdown 围栏。字段必须包括："
            "matched、skill_id、confidence、reason、fit_checks、"
            "missing_requirements、recommended_action。"
        )
        envelope = await ParallelSubAgentService().run(
            user_id=context.user_id,
            parent_agent_id=context.agent_id or "",
            parent_session_id=context.session_id,
            context_summary="执行 Skill 路由全文适配审查。",
            tasks=[{"agent_id": "agent-general", "task": task}],
            db=context.db,
            safe_only=True,
            runtime_authorized=True,
        )
        results = (envelope.get("llm_payload") or {}).get("results") or []
        answer = str(results[0].get("answer") or "") if results else ""
        if not answer:
            return _finalize(
                {
                    "matched": False,
                    "skill_id": None,
                    "confidence": 0.0,
                    "reason": (envelope.get("llm_payload") or {}).get("error")
                    or "Skill scout 未返回审查结果",
                    "candidates": [
                        {key: value for key, value in item.items() if key != "skill_body"}
                        for item in candidates
                    ],
                }
            )
        return _finalize(_parse_scout_answer(answer, candidates))
