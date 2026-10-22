"""Embedding-only Provider selection must never reroute chat or hide bad UUIDs."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from cygnusx.domain.ai_provider.entities import AIProviderConfig
from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider

pytestmark = pytest.mark.unit


@pytest.fixture
def selection(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    config = AIProviderConfig.create(
        name="embedding", model="Qwen/Qwen3-Embedding-8B",
        base_url="https://embedding.example/v1", api_key="synthetic-key",
    )
    settings = SimpleNamespace(
        agent_memory_embedding_provider_id=str(config.id),
        agent_memory_embedding_dimensions=1024,
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.ai_provider.litellm_provider.get_settings", lambda: settings,
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=config)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=MagicMock())
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory",
        lambda: lambda: context,
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.repositories.ai_provider_repository."
        "SqlAlchemyAIProviderConfigRepository", lambda _: repo,
    )
    request = AsyncMock(return_value={"data": [{"embedding": [0.5]}]})
    monkeypatch.setattr(
        "cygnusx.infrastructure.ai_provider.litellm_provider.litellm.aembedding", request,
    )
    return SimpleNamespace(config=config, settings=settings, repo=repo, request=request)


@pytest.mark.asyncio
async def test_embedding_selects_uuid_and_sends_dimensions(selection: SimpleNamespace) -> None:
    provider = LiteLLMProvider()
    provider._get_config = AsyncMock(side_effect=AssertionError("No chat fallback"))
    assert await provider.embeddings("synthetic", model="Qwen/Qwen3-Embedding-8B") == [0.5]
    selection.repo.get_by_id.assert_awaited_once_with(selection.config.id)
    sent = selection.request.await_args.kwargs
    assert sent["model"] == "openai/Qwen/Qwen3-Embedding-8B"
    assert sent["api_base"] == selection.config.base_url
    assert sent["api_key"] == selection.config.api_key
    assert sent["dimensions"] == 1024
    # Exercise the installed SDK's validation rather than stopping at aembedding's mock.
    from litellm.utils import get_optional_params_embeddings

    optional = get_optional_params_embeddings(
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=sent["dimensions"],
        custom_llm_provider="openai",
        allowed_openai_params=sent["allowed_openai_params"],
    )
    assert optional["dimensions"] == 1024
    provider._get_config.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["bad_uuid", "missing", "inactive"])
async def test_invalid_selection_never_falls_back(selection: SimpleNamespace, kind: str) -> None:
    if kind == "bad_uuid":
        selection.settings.agent_memory_embedding_provider_id = "not-a-uuid"
    elif kind == "missing":
        selection.repo.get_by_id.return_value = None
    else:
        selection.config.is_active = False
    provider = LiteLLMProvider()
    provider._get_config = AsyncMock(side_effect=AssertionError("No chat fallback"))
    with pytest.raises(ValueError, match="Embedding Provider"):
        await provider.embeddings("synthetic")
    selection.request.assert_not_awaited()
    provider._get_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_blank_selection_preserves_old_request(selection: SimpleNamespace) -> None:
    selection.settings.agent_memory_embedding_provider_id = ""
    selection.config.model = "old-model"
    provider = LiteLLMProvider(selection.config)
    await provider.embeddings("synthetic")
    sent = selection.request.await_args.kwargs
    assert sent["model"] == "openai/old-model"
    assert "dimensions" not in sent
    assert "allowed_openai_params" not in sent
    selection.repo.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_config_does_not_use_embedding_selection(selection: SimpleNamespace) -> None:
    chat = AIProviderConfig.create(name="chat", model="chat-model")
    assert await LiteLLMProvider(chat)._get_config() is chat
    selection.repo.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_maintenance_provider_stays_in_target_database(
    selection: SimpleNamespace,
) -> None:
    await LiteLLMProvider(selection.config).embeddings("synthetic")
    selection.repo.get_by_id.assert_not_awaited()
    other = selection.config.model_copy(update={"id": uuid4()})
    with pytest.raises(ValueError, match="conflicts"):
        await LiteLLMProvider(other).embeddings("synthetic")
    selection.repo.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [True, False])
async def test_startup_reports_invalid_or_default_provider(
    selection: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, invalid: bool,
) -> None:
    from cygnusx import main

    selection.settings.agent_memory_embedding_model = "Qwen/Qwen3-Embedding-8B"
    monkeypatch.setattr(main, "get_settings", lambda: selection.settings)
    messages = MagicMock()
    monkeypatch.setattr("loguru.logger.error", messages.error)
    monkeypatch.setattr("loguru.logger.warning", messages.warning)
    selection.config.is_default = True
    if invalid:
        selection.repo.get_by_id.return_value = None
    await main._validate_memory_embedding_provider()
    if invalid:
        messages.error.assert_called_once()
        assert "embedding_provider_invalid" in messages.error.call_args.args[0]
    else:
        messages.warning.assert_called_once()
        assert "embedding_provider_is_chat_default" in messages.warning.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", ["memory", "kb_index", "kb_query"])
async def test_memory_and_kb_share_embedding_selection(
    selection: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, consumer: str,
) -> None:
    selection.settings.agent_memory_embedding_model = selection.config.model
    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: selection.settings)
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: selection.settings,
    )
    vector = [0.5] * 1024
    selection.request.return_value = {"data": [{"embedding": vector}]}
    if consumer == "memory":
        from cygnusx.application.services.agent_memory_service import AgentMemoryService

        result = await AgentMemoryService(MagicMock())._embed("synthetic")
    elif consumer == "kb_index":
        from cygnusx.application.services.knowledge_index_service import KnowledgeIndexService

        result = await KnowledgeIndexService(MagicMock())._embed("synthetic", selection.config.model)
    else:
        from cygnusx.application.services.vector_retrieval_service import VectorRetrievalService

        result = await VectorRetrievalService(MagicMock())._embed("synthetic")
    assert result == vector
    sent = selection.request.await_args.kwargs
    assert sent["api_base"] == selection.config.base_url
    assert sent["model"] == "openai/Qwen/Qwen3-Embedding-8B"
    assert sent["dimensions"] == 1024


def test_embedding_settings_defaults_and_dimension_validation() -> None:
    from pydantic import ValidationError

    from cygnusx.core.config import Settings

    settings = Settings(_env_file=None, agent_memory_embedding_provider_id="")
    assert settings.agent_memory_embedding_provider_id == ""
    assert settings.agent_memory_embedding_dimensions == 1024
    with pytest.raises(ValidationError):
        Settings(_env_file=None, agent_memory_embedding_dimensions=0)
