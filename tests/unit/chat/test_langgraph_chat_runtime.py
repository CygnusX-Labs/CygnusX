"""LangGraph Agent Runtime 的终态事件测试。"""

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from cygnusx.application.services.chat.runtimes.langgraph_runtime import LangGraphChatRuntime
from cygnusx.application.services.chat.dual_run import (
    assert_equivalent,
    compare_golden_record,
)
from cygnusx.application.services.execution_events import validate_event_sequence
from cygnusx.infrastructure.ai_provider.openai_compatible import ChatChunk


_GOLDEN_ROOT = Path(__file__).parents[2] / "e2e" / "chat_golden"


class _Service:
    def __init__(self) -> None:
        self.update_message_content = AsyncMock()
        self._apply_usage_to_session = AsyncMock()


async def _stream_chunks(
    runtime: LangGraphChatRuntime,
    **overrides: Any,
) -> list[ChatChunk]:
    defaults: dict[str, Any] = {
        "user_id": "user-1",
        "session_id": "session-1",
        "ai_message_id": "message-1",
        "model_config": SimpleNamespace(model="test-model"),
        "llm_messages": [],
        "system_prompt": None,
        "tools": [],
        "temperature": 0.2,
        "max_tokens": 128,
        "deep_thinking": False,
        "active_mcp_servers": [],
        "mcp_client": SimpleNamespace(),
        "tool_context": SimpleNamespace(agent_id="agent-1"),
    }
    defaults.update(overrides)
    return [
        chunk
        async for chunk in runtime._stream_agent_chat_langgraph(**defaults)
    ]


@pytest.mark.asyncio
async def test_langgraph_runtime_error_stream_emits_failed_terminal_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingRuntime:
        def __init__(self, *_: Any, **__: Any) -> None:
            self.last_usage = None
            self.last_handoff = None
            self.last_ask_request = None
            self.rounds_exhausted = False

        async def stream(self, _: list[dict[str, Any]]) -> AsyncIterator[ChatChunk]:
            yield ChatChunk(type="error", content="provider unavailable")

    import cygnusx.infrastructure.execution.langgraph_runtime as runtime_module

    monkeypatch.setattr(runtime_module, "LangGraphRuntimeService", _FailingRuntime)
    service = _Service()
    runtime = LangGraphChatRuntime(service)  # type: ignore[arg-type]
    chunks = await _stream_chunks(runtime)

    assert [chunk.type for chunk in chunks] == [
        "agent_turn_started",
        "error",
        "agent_turn_failed",
        "done",
    ]
    validate_event_sequence(chunks)
    service.update_message_content.assert_awaited_once()

    result = await compare_golden_record(
        "langgraph-runtime-error",
        _GOLDEN_ROOT / "langgraph-runtime-error.json",
        lambda: runtime._stream_agent_chat_langgraph(
            user_id="user-1",
            session_id="session-1",
            ai_message_id="message-1",
            model_config=SimpleNamespace(model="test-model"),
            llm_messages=[],
            system_prompt=None,
            tools=[],
            temperature=0.2,
            max_tokens=128,
            deep_thinking=False,
            active_mcp_servers=[],
            mcp_client=SimpleNamespace(),
            tool_context=SimpleNamespace(agent_id="agent-1"),
        ),
    )

    assert_equivalent([result])


@pytest.mark.asyncio
async def test_unhandled_langgraph_handoff_emits_failed_terminal_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _HandoffRuntime:
        def __init__(self, *_: Any, **__: Any) -> None:
            self.last_usage = None
            self.last_handoff = {"target_agent_id": "agent-2"}
            self.last_ask_request = None
            self.rounds_exhausted = False

        async def stream(self, _: list[dict[str, Any]]) -> AsyncIterator[ChatChunk]:
            if False:
                yield ChatChunk(type="text")

    import cygnusx.infrastructure.execution.langgraph_runtime as runtime_module

    monkeypatch.setattr(runtime_module, "LangGraphRuntimeService", _HandoffRuntime)
    service = _Service()
    chunks = await _stream_chunks(LangGraphChatRuntime(service))  # type: ignore[arg-type]

    assert [chunk.type for chunk in chunks] == [
        "agent_turn_started",
        "error",
        "agent_turn_failed",
        "done",
    ]
    validate_event_sequence(chunks)
    service.update_message_content.assert_awaited_once()
