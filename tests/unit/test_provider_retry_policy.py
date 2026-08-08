from collections.abc import AsyncIterator

import pytest

from omichub.core.config import get_settings
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


@pytest.mark.asyncio
async def test_transient_error_retries_multiple_times_before_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可重试错误在尚未输出时应能连续重试多次（默认 3 次），最终成功则正常产出。"""
    provider = OpenAICompatibleProvider(
        AIProviderConfigModel(name="test", model="qwen-test", base_url="https://example.test")
    )
    monkeypatch.setattr(get_settings(), "llm_stream_transient_retries", 3)
    calls = {"count": 0}

    async def stream_once(*args: object) -> AsyncIterator[ChatChunk]:
        calls["count"] += 1
        if calls["count"] <= 3:  # 前 3 次均瞬时失败
            yield ChatChunk(type="error", metadata={"retryable": True})
            return
        yield ChatChunk(type="text", content="成功")
        yield ChatChunk(type="done")

    monkeypatch.setattr(provider, "_stream_once", stream_once)

    chunks = [chunk async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}])]

    assert calls["count"] == 4  # 1 次初始 + 3 次重试
    assert [chunk.type for chunk in chunks] == ["text", "done"]
    assert chunks[0].content == "成功"


@pytest.mark.asyncio
async def test_transient_error_exhausts_retries_then_yields_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重试用尽后应把错误上抛（而不是无限循环），且错误带 retryable 标记。"""
    provider = OpenAICompatibleProvider(
        AIProviderConfigModel(name="test", model="qwen-test", base_url="https://example.test")
    )
    monkeypatch.setattr(get_settings(), "llm_stream_transient_retries", 2)
    calls = {"count": 0}

    async def stream_once(*args: object) -> AsyncIterator[ChatChunk]:
        calls["count"] += 1
        yield ChatChunk(type="error", content="连接中断", metadata={"retryable": True})

    monkeypatch.setattr(provider, "_stream_once", stream_once)

    chunks = [chunk async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}])]

    assert calls["count"] == 3  # 1 次初始 + 2 次重试
    assert [chunk.type for chunk in chunks] == ["error"]
    assert chunks[0].content == "连接中断"


@pytest.mark.asyncio
async def test_no_retry_after_text_already_yielded(monkeypatch: pytest.MonkeyPatch) -> None:
    """已经输出正文后发生的错误不得重试（避免重复内容），应直接上抛错误。"""
    provider = OpenAICompatibleProvider(
        AIProviderConfigModel(name="test", model="qwen-test", base_url="https://example.test")
    )
    monkeypatch.setattr(get_settings(), "llm_stream_transient_retries", 3)
    calls = {"count": 0}

    async def stream_once(*args: object) -> AsyncIterator[ChatChunk]:
        calls["count"] += 1
        yield ChatChunk(type="text", content="部分内容")
        yield ChatChunk(type="error", content="中途断开", metadata={"retryable": True})

    monkeypatch.setattr(provider, "_stream_once", stream_once)

    chunks = [chunk async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}])]

    assert calls["count"] == 1  # 不重试
    assert [chunk.type for chunk in chunks] == ["text", "error"]


@pytest.mark.asyncio
async def test_retry_disabled_when_limit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """把重试上限配置为 0 时，首次可重试错误即直接上抛。"""
    provider = OpenAICompatibleProvider(
        AIProviderConfigModel(name="test", model="qwen-test", base_url="https://example.test")
    )
    monkeypatch.setattr(get_settings(), "llm_stream_transient_retries", 0)
    calls = {"count": 0}

    async def stream_once(*args: object) -> AsyncIterator[ChatChunk]:
        calls["count"] += 1
        yield ChatChunk(type="error", metadata={"retryable": True})

    monkeypatch.setattr(provider, "_stream_once", stream_once)

    chunks = [chunk async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}])]

    assert calls["count"] == 1
    assert [chunk.type for chunk in chunks] == ["error"]
