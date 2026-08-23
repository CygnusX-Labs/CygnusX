"""Agent Runtime 网关测试。"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from omichub.application.services.chat.agent_runtime_gateway import AgentRuntimeGateway
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk


class _Gateway(AgentRuntimeGateway):
    async def _stream_agent_chat_inner(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatChunk]:
        del args, kwargs
        yield ChatChunk(type="error", content="legacy path should not run")


class _Span:
    def __enter__(self) -> "_Span":
        return self

    def __exit__(self, *args: Any) -> None:
        del args

    def record_exception(self, error: Exception) -> None:
        del error

    def set_attribute(self, key: str, value: Any) -> None:
        del key, value


class _Tracer:
    def start_as_current_span(self, *args: Any, **kwargs: Any) -> _Span:
        del args, kwargs
        return _Span()


class _Counter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, str]]] = []

    def add(self, value: int, attributes: dict[str, str]) -> None:
        self.calls.append((value, attributes))


@pytest.mark.asyncio
async def test_gateway_routes_to_runtime_when_refactor_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Router:
        def __init__(self, service: Any) -> None:
            captured["service"] = service

        async def stream(self, request: Any) -> AsyncIterator[ChatChunk]:
            captured["request"] = request
            yield ChatChunk(type="done")

    monkeypatch.setattr(
        "omichub.application.services.chat.agent_runtime_gateway.ChatRouterService", _Router
    )
    monkeypatch.setattr(
        "omichub.application.services.chat.agent_runtime_gateway.get_settings",
        lambda: SimpleNamespace(chat_runtime_refactor_enabled=True),
    )
    monkeypatch.setattr(
        "omichub.application.services.chat.agent_runtime_gateway.get_tracer",
        lambda name: _Tracer(),
    )
    gateway = _Gateway()

    chunks = [
        chunk
        async for chunk in gateway.stream_agent_chat(
            user_id="user-1",
            agent_id="agent-1",
            messages=[{"role": "user", "content": "hello"}],
        )
    ]

    assert [chunk.type for chunk in chunks] == ["done"]
    assert captured["service"] is gateway
    assert captured["request"].agent_id == "agent-1"


@pytest.mark.asyncio
async def test_gateway_records_legacy_entry_when_refactor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = _Counter()
    monkeypatch.setattr(
        "omichub.application.services.chat.agent_runtime_gateway.get_settings",
        lambda: SimpleNamespace(chat_runtime_refactor_enabled=False),
    )
    monkeypatch.setattr(
        "omichub.application.services.chat.agent_runtime_gateway.get_tracer",
        lambda name: _Tracer(),
    )
    monkeypatch.setattr(
        "omichub.application.services.chat.agent_runtime_gateway._legacy_runtime_entry_count",
        counter,
    )

    chunks = [
        chunk
        async for chunk in _Gateway().stream_agent_chat(
            user_id="user-1",
            agent_id="agent-1",
            messages=[{"role": "user", "content": "hello"}],
            mode="studio",
        )
    ]

    assert [chunk.type for chunk in chunks] == ["error"]
    assert counter.calls == [(1, {"agent.id": "agent-1", "chat.mode": "studio"})]
