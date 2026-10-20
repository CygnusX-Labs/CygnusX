"""Runtime memory gating across configuration, administration and tools."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cygnusx.application.services.agent_memory_tool_service import AgentMemoryToolService
from cygnusx.application.services.memory_runtime_policy import is_memory_runtime_enabled
from cygnusx.core.exceptions import BusinessError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.mark.parametrize("feature,db_present,site", [
    (False, True, True), (True, False, True),
    (True, True, False), (True, True, True), (True, True, "error"),
])
async def test_runtime_policy_requires_both_gates_and_verifiable_database(monkeypatch, feature, db_present, site):
    monkeypatch.setattr(
        "cygnusx.core.config.get_settings", lambda: SimpleNamespace(memory_v2_enabled=feature)
    )
    lookup = AsyncMock(side_effect=RuntimeError("site lookup unavailable") if site == "error" else None,
                       return_value=site is True)
    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled", lookup
    )
    result = await is_memory_runtime_enabled(object() if db_present else None)
    assert result is (feature and db_present and site is True)
    if not feature or not db_present:
        lookup.assert_not_awaited()


@pytest.mark.parametrize("method,arguments", [
    ("save_memory", {"scope": "preference", "content": "remember"}),
    ("update_memory", {"memory_id": "1", "content": "updated"}),
    ("forget_memory", {"memory_id": "1"}),
    ("search_memory", {"query": "query"}),
    ("update_memory_block", {"block_name": "profile", "content": "profile", "expected_version": 1}),
])
@pytest.mark.parametrize("reason", ["site_disabled", "identity_mismatch"])
async def test_memory_tools_reject_disabled_or_mismatched_context_before_dispatch(monkeypatch, method, arguments, reason):
    tools = AgentMemoryToolService()
    service = Mock(side_effect=AssertionError("Blocked tools must not dispatch"))
    monkeypatch.setattr(tools, "_service", service)
    gate = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled", gate
    )
    context = SimpleNamespace(user_id="other" if reason == "identity_mismatch" else "owner",
                              agent_id="a", session_id="s", db=object())
    with pytest.raises(BusinessError):
        await getattr(tools, method)(user_id="owner", context=context, **arguments)
    service.assert_not_called()
    if reason == "identity_mismatch":
        gate.assert_not_awaited()


async def test_project_context_lookup_is_owned_by_invoking_user() -> None:
    from sqlalchemy.dialects import postgresql

    db = SimpleNamespace(scalar=AsyncMock(return_value=None))
    context = SimpleNamespace(db=db, session_id="session", user_id="owner")
    assert await AgentMemoryToolService._project_id(context) is None
    query = db.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "chat_sessions.user_id =" in str(query)
    assert {"session", "owner"}.issubset(set(query.params.values()))


async def test_queued_recall_batch_stops_when_site_memory_is_disabled(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    from cygnusx.infrastructure.celery_app.tasks.memory import _record_recall_batch

    db = SimpleNamespace(scalar=AsyncMock(), commit=AsyncMock())

    @asynccontextmanager
    async def context():
        yield db

    monkeypatch.setattr(
        "cygnusx.core.config.get_settings",
        lambda: SimpleNamespace(memory_v2_enabled=True, memory_recall_tracking_enabled=True),
    )
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: context)
    monkeypatch.setattr(
        "cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled",
        AsyncMock(return_value=False),
    )
    assert await _record_recall_batch("owner", [1], "batch") == {"status": "disabled"}
    db.scalar.assert_not_awaited()
    db.commit.assert_not_awaited()
