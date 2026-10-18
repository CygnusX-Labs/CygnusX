from types import SimpleNamespace
from uuid import uuid4

import pytest

from cygnusx.core.config import Settings
from cygnusx.infrastructure.ai_provider import openai_compatible
from cygnusx.infrastructure.ai_provider.openai_compatible import provider_manager
from cygnusx.infrastructure.ai_provider.testing import DeterministicTestProvider

pytestmark = pytest.mark.unit


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name="isolated deterministic provider",
        model="scripted",
        provider_type="deterministic_test",
        extra_params={
            "deterministic_test_script": {
                "call_id": "test-call",
                "name": "catalog.read",
                "arguments": {},
            }
        },
    )


def test_deterministic_provider_requires_explicit_acceptance_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    provider_manager.clear_cache(str(config.id))
    monkeypatch.setattr(
        openai_compatible,
        "get_settings",
        lambda: Settings(app_env="acceptance", deterministic_test_provider_enabled=False),
    )

    with pytest.raises(RuntimeError, match="DETERMINISTIC_TEST_PROVIDER_DISABLED"):
        provider_manager.get_or_create(config)


def test_deterministic_provider_is_never_available_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    provider_manager.clear_cache(str(config.id))
    monkeypatch.setattr(
        openai_compatible,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="production", deterministic_test_provider_enabled=True
        ),
    )

    with pytest.raises(RuntimeError, match="DETERMINISTIC_TEST_PROVIDER_DISABLED"):
        provider_manager.get_or_create(config)


def test_provider_manager_assembles_deterministic_provider_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    provider_manager.clear_cache(str(config.id))
    monkeypatch.setattr(
        openai_compatible,
        "get_settings",
        lambda: Settings(app_env="acceptance", deterministic_test_provider_enabled=True),
    )

    provider = provider_manager.get_or_create(config)

    assert isinstance(provider, DeterministicTestProvider)
    provider_manager.clear_cache(str(config.id))


async def test_deterministic_provider_ignores_tool_results_from_previous_turn() -> None:
    provider = DeterministicTestProvider(_config())
    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [
                {"role": "user", "content": "previous request"},
                {
                    "role": "assistant",
                    "tool_calls": [{"id": "old-call", "type": "function"}],
                },
                {"role": "tool", "tool_call_id": "old-call", "content": "stale result"},
                {"role": "user", "content": "new request"},
            ],
            tools=[{"function": {"name": "catalog.read"}}],
        )
    ]

    assert chunks[0].type == "tool_calls"
    assert chunks[0].metadata["tool_calls"][0]["id"] == "test-call"


async def test_deterministic_provider_echoes_only_current_turn_tool_results() -> None:
    provider = DeterministicTestProvider(_config())
    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [
                {"role": "user", "content": "read catalog"},
                {
                    "role": "assistant",
                    "tool_calls": [{"id": "test-call", "type": "function"}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "test-call",
                    "content": "actual gateway result",
                },
            ],
            tools=[{"function": {"name": "catalog.read"}}],
        )
    ]

    assert chunks[0].type == "text"
    assert chunks[0].content == "actual gateway result"


async def test_deterministic_provider_rejects_tool_result_before_its_call() -> None:
    provider = DeterministicTestProvider(_config())
    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [
                {"role": "user", "content": "read catalog"},
                {"role": "tool", "tool_call_id": "test-call", "content": "early result"},
                {
                    "role": "assistant",
                    "tool_calls": [{"id": "test-call", "type": "function"}],
                },
            ],
            tools=[{"function": {"name": "catalog.read"}}],
        )
    ]

    assert chunks[0].type == "tool_calls"
