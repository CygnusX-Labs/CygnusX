"""联网搜索适配器的离线契约测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from omichub.application.schemas import tool_invocation
from omichub.application.services import chat_service, search_provider_service
from omichub.application.services.agent_service import AgentContext, AgentService
from omichub.application.services.chat_service import ChatService
from omichub.application.services.search_provider_service import SearchProviderService
from omichub.core.exceptions import BusinessError
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk
from omichub.infrastructure.web_search.service import WebSearchService


@pytest.mark.parametrize(
    ("adapter", "payload", "expected"),
    [
        (
            "_tavily",
            {"results": [{"title": "Tavily", "url": "https://tavily.com", "content": "result"}]},
            ("Tavily", "https://tavily.com", "result"),
        ),
        (
            "_exa",
            {"results": [{"title": "Exa", "url": "https://exa.ai", "highlights": ["first", "second"]}]},
            ("Exa", "https://exa.ai", "first second"),
        ),
        (
            "_bocha",
            {"data": {"webPages": {"value": [{"name": "Bocha", "url": "https://bochaai.com", "snippet": "result"}]}}},
            ("Bocha", "https://bochaai.com", "result"),
        ),
        (
            "_zhipu",
            {
                "search_result": [
                    {
                        "title": "Zhipu",
                        "link": "https://zhipuai.cn",
                        "content": "result",
                        "publish_date": "2026-07-26",
                    }
                ]
            },
            ("Zhipu", "https://zhipuai.cn", "result"),
        ),
    ],
)
def test_provider_adapters_normalize_results(adapter, payload, expected):
    results = getattr(WebSearchService, adapter)(payload)

    assert len(results) == 1
    assert (results[0].title, results[0].url, results[0].snippet) == expected


def test_searxng_adapter_filters_invalid_results_and_limits_response():
    payload = {
        "results": [
            {"title": "valid", "url": "https://example.com", "content": "snippet", "published_date": "2026-07-26"},
            {"title": "missing URL"},
            {"title": "other", "url": "https://example.org"},
        ]
    }

    results = WebSearchService._searxng(payload, limit=2)

    assert [result.url for result in results] == ["https://example.com"]
    assert results[0].as_dict()["publishedAt"] == "2026-07-26"


def test_zhipu_request_matches_official_web_search_contract():
    payload = WebSearchService._zhipu_request_payload("基因组研究", 10, "advanced")

    assert payload == {
        "search_query": "基因组研究",
        "search_engine": "search_pro",
        "search_intent": False,
        "count": 10,
        "search_recency_filter": "noLimit",
        "content_size": "medium",
    }


def test_zhipu_publish_date_is_normalized():
    result = WebSearchService._zhipu(
        {
            "search_result": [
                {
                    "title": "Zhipu",
                    "link": "https://zhipuai.cn",
                    "content": "result",
                    "publish_date": "2026-07-26",
                }
            ]
        }
    )[0]

    assert result.published_at == "2026-07-26"


def test_freshness_queries_require_web_search_without_manual_toggle():
    assert ChatService._requires_fresh_web_search("武汉今天天气")
    assert ChatService._requires_fresh_web_search("最新单细胞研究文献")
    assert not ChatService._requires_fresh_web_search("如何做 RNA-seq 差异表达")


@pytest.mark.asyncio
async def test_empty_query_avoids_network_request():
    service = WebSearchService(provider_id="tavily", api_key="key", base_url="https://api.tavily.com")

    assert await service.search("   ") == []


@pytest.mark.asyncio
async def test_local_provider_is_rejected_before_network_request():
    service = WebSearchService(provider_id="google", api_key="", base_url="https://www.google.com")

    with pytest.raises(BusinessError, match="暂未启用"):
        await service.search("OmicHub")


@pytest.mark.asyncio
async def test_local_provider_cannot_be_selected_as_default():
    service = SearchProviderService(None)

    with pytest.raises(BusinessError, match="暂不能设为默认"):
        await service.set_default("google")


def test_api_key_mask_keeps_only_safe_prefix_and_suffix():
    assert SearchProviderService._masked_api_key("sk-live-secret-1234") == "sk-****1234"
    assert SearchProviderService._masked_api_key("short") == "********"


@pytest.mark.asyncio
async def test_provider_search_passes_configured_depth(monkeypatch):
    captured: dict[str, object] = {}

    class FakeWebSearchService:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def search(self, query, max_results, search_depth):
            captured.update(query=query, max_results=max_results, search_depth=search_depth)
            return []

    monkeypatch.setattr(search_provider_service, "WebSearchService", FakeWebSearchService)
    model = SimpleNamespace(
        id="tavily",
        api_key="key",
        base_url="https://api.tavily.com",
        timeout_seconds=10,
        params={"maxResults": 8, "searchDepth": "advanced"},
    )

    await SearchProviderService(None)._search_with(model, "latest paper")

    assert captured["query"] == "latest paper"
    assert captured["max_results"] == 8
    assert captured["search_depth"] == "advanced"


def _configure_agent_stream(monkeypatch, *, supports_tools, provider_stream):
    class FakeDb:
        async def flush(self):
            return None

    model = SimpleNamespace(
        id="model-1",
        api_key="model-key",
        name="Test model",
        model="test-model",
        extra_params={"supports_tools": supports_tools},
    )
    context = AgentContext(
        agent=SimpleNamespace(name="Test agent", project_id=None),
        model_config=model,
        system_prompt="base system prompt",
        tools=[],
        mcp_servers=[],
        features={},
        temperature=0.2,
        max_tokens=256,
    )
    session = SimpleNamespace(
        agent_id="agent-1",
        mode="chat",
        sandbox_meta={},
        model_id=model.id,
        project_id=None,
    )
    service = ChatService(FakeDb())
    message_ids = iter(["user-1", "assistant-1"])

    async def no_cookie_balance(_user_id):
        return None

    async def assemble_context(_self, _agent_id):
        return context

    async def get_session(_session_id, _user_id):
        return session

    async def add_message(*_args, **_kwargs):
        return SimpleNamespace(message_id=next(message_ids))

    async def ignore_update(*_args, **_kwargs):
        return None

    async def no_session_file_context(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(service, "_ensure_cookie_balance", no_cookie_balance)
    monkeypatch.setattr(AgentService, "assemble_context", assemble_context)
    monkeypatch.setattr(service, "get_session", get_session)
    monkeypatch.setattr(service, "add_message", add_message)
    monkeypatch.setattr(service, "update_message_content", ignore_update)
    monkeypatch.setattr(service, "_apply_usage_to_session", ignore_update)
    monkeypatch.setattr(service, "_collect_session_file_context", no_session_file_context)
    monkeypatch.setattr(chat_service.provider_manager, "chat_stream", provider_stream)
    monkeypatch.setattr(tool_invocation, "ToolInvocationContext", lambda **kwargs: kwargs)
    return service


@pytest.mark.asyncio
async def test_agent_without_tools_uses_presearch_context(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_search_default(_self, query, _max_results=5):
        captured["query"] = query
        return [{"title": "Fresh result", "url": "https://example.com", "snippet": "current data"}]

    async def fake_provider_stream(**kwargs):
        captured["system_prompt"] = kwargs["system_prompt"]
        captured["tools"] = kwargs["tools"]
        yield ChatChunk(type="text", content="回答 [1]")
        yield ChatChunk(type="done", metadata={"usage": {"total": 1}})

    monkeypatch.setattr(SearchProviderService, "search_default", fake_search_default)
    service = _configure_agent_stream(monkeypatch, supports_tools=False, provider_stream=fake_provider_stream)

    events = [
        event async for event in service.stream_agent_chat(
            user_id="user-1",
            agent_id="agent-1",
            session_id="session-1",
            messages=[{"role": "user", "content": "今天的新闻"}],
            enable_web_search=True,
        )
    ]

    assert "error" not in [event.type for event in events], [
        (event.type, event.content) for event in events
    ]
    assert captured["query"] == "今天的新闻"
    assert captured["tools"] is None
    assert "[1] Fresh result" in captured["system_prompt"]
    assert [event.type for event in events] == ["web_search", "web_search_results", "text", "done"]


@pytest.mark.asyncio
async def test_agent_injects_user_memory_into_system_prompt(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_provider_stream(**kwargs):
        captured["system_prompt"] = kwargs["system_prompt"]
        yield ChatChunk(type="text", content="已结合项目背景")
        yield ChatChunk(type="done", metadata={"usage": {"total": 1}})

    async def fake_memory_context(self, user_id, agent_id, query):
        assert (user_id, agent_id, query) == ("user-1", "agent-1", "继续分析小鼠脑数据")
        return "## 用户记忆（跨会话，可能过时；与当前对话冲突时以当前对话为准）\n- 用户常用小鼠脑 10x V3 数据。"

    monkeypatch.setattr(
        "omichub.application.services.agent_memory_service.AgentMemoryService.build_prompt_context",
        fake_memory_context,
    )
    service = _configure_agent_stream(monkeypatch, supports_tools=False, provider_stream=fake_provider_stream)
    service._db = MagicMock(flush=AsyncMock())

    events = [
        event async for event in service.stream_agent_chat(
            user_id="user-1",
            agent_id="agent-1",
            session_id="session-1",
            messages=[{"role": "user", "content": "继续分析小鼠脑数据"}],
        )
    ]

    assert "error" not in [event.type for event in events]
    assert "用户常用小鼠脑 10x V3 数据" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_agent_with_tools_executes_and_reinjects_web_search(monkeypatch):
    calls: list[dict[str, object]] = []

    async def fake_search_default(_self, query, _max_results=5):
        assert query == "查找该主题的资料"
        return [{"title": "Live source", "url": "https://example.com/live", "snippet": "new finding"}]

    async def fake_provider_stream(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            assert any(tool["function"]["name"] == "web_search" for tool in kwargs["tools"])
            yield ChatChunk(
                type="tool_calls",
                metadata={
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "web_search", "arguments": '{"query":"查找该主题的资料"}'},
                        }
                    ]
                },
            )
            yield ChatChunk(type="done", metadata={})
            return
        assert kwargs["messages"][-1]["role"] == "tool"
        assert "Live source" in kwargs["messages"][-1]["content"]
        yield ChatChunk(type="text", content="这是依据 [1] 的回答")
        yield ChatChunk(type="done", metadata={})

    monkeypatch.setattr(SearchProviderService, "search_default", fake_search_default)
    service = _configure_agent_stream(monkeypatch, supports_tools=True, provider_stream=fake_provider_stream)

    events = [
        event async for event in service.stream_agent_chat(
            user_id="user-1",
            agent_id="agent-1",
            session_id="session-1",
            messages=[{"role": "user", "content": "查找该主题的资料"}],
            enable_web_search=True,
        )
    ]

    assert "error" not in [event.type for event in events], [
        (event.type, event.content) for event in events
    ]
    assert [event.type for event in events] == [
        "tool_call", "web_search", "web_search_results", "tool_result", "text", "done",
    ]


@pytest.mark.asyncio
async def test_presearch_failure_does_not_interrupt_agent_response(monkeypatch):
    async def failing_search_default(_self, _query, _max_results=5):
        raise BusinessError("搜索超时")

    async def fake_provider_stream(**_kwargs):
        yield ChatChunk(type="text", content="继续使用模型知识回答")
        yield ChatChunk(type="done", metadata={})

    monkeypatch.setattr(SearchProviderService, "search_default", failing_search_default)
    service = _configure_agent_stream(monkeypatch, supports_tools=False, provider_stream=fake_provider_stream)

    events = [
        event async for event in service.stream_agent_chat(
            user_id="user-1",
            agent_id="agent-1",
            session_id="session-1",
            messages=[{"role": "user", "content": "会失败的搜索"}],
            enable_web_search=True,
        )
    ]

    assert [event.type for event in events] == ["web_search", "web_search", "text", "done"]
    assert events[1].metadata["status"] == "failed"


@pytest.mark.asyncio
async def test_setting_default_clears_existing_default_provider():
    provider = SimpleNamespace(
        id="tavily",
        name="Tavily",
        provider_type="api",
        api_key="tavily-secret-1234",
        base_url="https://api.tavily.com",
        is_enabled=True,
        is_default=False,
        params={},
        timeout_seconds=10,
        updated_at=None,
    )

    class FakeDatabase:
        def __init__(self):
            self.statement = None

        async def get(self, _model, _provider_id):
            return provider

        async def execute(self, statement):
            self.statement = statement

        async def flush(self):
            return None

        async def refresh(self, _model):
            return None

    database = FakeDatabase()
    result = await SearchProviderService(database).set_default("tavily")

    assert provider.is_default is True
    assert "is_default" in str(database.statement)
    assert result.is_default is True
