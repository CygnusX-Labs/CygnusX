"""Agent 聊天 Runtime 的统一入口与观测网关。"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from omichub.application.services.chat.chat_router_service import ChatRouterService
from omichub.application.services.chat.runtimes.base import ChatRuntimeRequest
from omichub.core.config import get_settings
from omichub.core.telemetry import get_meter, get_tracer
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk

_agent_duration = get_meter("omichub.chat").create_histogram(
    "agent.run.duration", unit="ms", description="Agent 单次运行耗时"
)
_legacy_runtime_entry_count = get_meter("omichub.chat").create_counter(
    "agent.runtime.legacy_entry.count",
    description="仍通过旧 Agent 编排入口的调用次数",
)


class AgentRuntimeGateway:
    """统一构造 Agent Runtime 请求并提供执行观测。"""

    async def stream_agent_chat(
        self,
        user_id: str,
        agent_id: str,
        messages: list[dict[str, str]],
        session_id: str | None = None,
        model_id: uuid.UUID | None = None,
        attachments: list[dict[str, Any]] | None = None,
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        deep_thinking: bool = False,
        mode: str | None = None,
        mcp_mode: str | None = None,
        extra_mcp_servers: list[str] | None = None,
        multi_agent: bool | None = None,
        overdrive: bool | None = None,
        extend_max_rounds: bool = False,
        project_id: str | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Agent 编排入口（带 Trace/Log/Metrics 埋点）：作为 AI/MCP/技能 span 的父 span。"""
        tracer = get_tracer("omichub.chat")
        span_attrs: dict[str, Any] = {"agent.id": agent_id}
        if model_id is not None:
            span_attrs["agent.model_id"] = str(model_id)
        with tracer.start_as_current_span("agent.run", attributes=span_attrs) as span:
            start = time.perf_counter()
            status = "success"
            try:
                request = ChatRuntimeRequest(
                    user_id=user_id,
                    agent_id=agent_id,
                    messages=messages,
                    session_id=session_id,
                    model_id=model_id,
                    attachments=attachments,
                    enable_web_search=enable_web_search,
                    enable_code_execution=enable_code_execution,
                    deep_thinking=deep_thinking,
                    mode=mode,
                    mcp_mode=mcp_mode,
                    extra_mcp_servers=extra_mcp_servers,
                    multi_agent=multi_agent,
                    overdrive=overdrive,
                    extend_max_rounds=extend_max_rounds,
                    project_id=project_id,
                    runtime_context=runtime_context or {},
                )
                settings = get_settings()
                if settings.chat_runtime_refactor_enabled:
                    stream = ChatRouterService(self).stream(request)
                else:
                    legacy_attributes = {
                        "agent.id": agent_id,
                        "chat.mode": mode or "chat",
                    }
                    _legacy_runtime_entry_count.add(1, legacy_attributes)
                    logger.bind(
                        event="agent.runtime.legacy_entry",
                        **legacy_attributes,
                    ).info("agent runtime used legacy entry")
                    stream = self._stream_agent_chat_inner(
                        user_id,
                        agent_id,
                        messages,
                        session_id=session_id,
                        model_id=model_id,
                        attachments=attachments,
                        enable_web_search=enable_web_search,
                        enable_code_execution=enable_code_execution,
                        deep_thinking=deep_thinking,
                        mode=mode,
                        mcp_mode=mcp_mode,
                        extra_mcp_servers=extra_mcp_servers,
                        multi_agent=multi_agent,
                        overdrive=overdrive,
                        extend_max_rounds=extend_max_rounds,
                        project_id=project_id,
                        runtime_context=runtime_context,
                    )
                async for chunk in stream:
                    if chunk.type == "error":
                        status = "error"
                    yield chunk
            except Exception as exc:  # noqa: BLE001
                status = "error"
                span.record_exception(exc)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                attrs = {"agent.id": agent_id, "agent.status": status}
                span.set_attribute("agent.status", status)
                span.set_attribute("agent.duration_ms", round(duration_ms, 2))
                with contextlib.suppress(Exception):
                    _agent_duration.record(duration_ms, attrs)
                logger.bind(
                    event="agent.run",
                    agent_id=agent_id,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                ).info("agent.run completed")
