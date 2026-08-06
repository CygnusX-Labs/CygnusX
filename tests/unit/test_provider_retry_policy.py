from collections.abc import AsyncIterator

import pytest

from omichub.domain.ai_provider.entities import AIProviderConfig
from omichub.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
from omichub.infrastructure.ai_provider.openai_compatible import (
    ChatChunk,
    OpenAICompatibleProvider,
)
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel


def test_litellm_stream_kwargs_request_usage_and_retry() -> None:
    provider = LiteLLMProvider()
    config = AIProviderConfig.create(
        name="test",
        model="qwen-test",
        base_url="https://example.test/v1",
    )

    kwargs = provider._build_kwargs(
        config,
        [{"role": "user", "content": "hello"}],
        stream=True,
    )

    assert kwargs["stream_options"] == {"include_usage": True}
    assert kwargs["num_retries"] == 2


@pytest.mark.asyncio
async def test_retryable_stream_error_keeps_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(
        AIProviderConfigModel(name="test", model="qwen-test", base_url="https://example.test")
    )
    tools = [{"type": "function", "function": {"name": "ask_user"}}]
    calls: list[list[dict[str, object]] | None] = []

    async def stream_once(*args: object) -> AsyncIterator[ChatChunk]:
        calls.append(args[4])
        if len(calls) == 1:
            yield ChatChunk(type="error", metadata={"retryable": True})
            return
        yield ChatChunk(type="text", content="完成")
        yield ChatChunk(type="done")

    monkeypatch.setattr(provider, "_stream_once", stream_once)

    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "请分析"}], tools=tools
        )
    ]

    assert calls == [tools, tools]
    assert [chunk.type for chunk in chunks] == ["text", "done"]


@pytest.mark.asyncio
async def test_empty_tool_stream_retries_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(
        AIProviderConfigModel(name="test", model="qwen-test", base_url="https://example.test")
    )
    tools = [{"type": "function", "function": {"name": "ask_user"}}]
    calls: list[list[dict[str, object]] | None] = []

    async def stream_once(*args: object) -> AsyncIterator[ChatChunk]:
        calls.append(args[4])
        if len(calls) == 1:
            yield ChatChunk(type="done")
            return
        yield ChatChunk(type="text", content="请补充输入文件")
        yield ChatChunk(type="done")

    monkeypatch.setattr(provider, "_stream_once", stream_once)

    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "请分析"}], tools=tools
        )
    ]

    assert calls == [tools, None]
    assert [chunk.type for chunk in chunks] == ["text", "done"]
