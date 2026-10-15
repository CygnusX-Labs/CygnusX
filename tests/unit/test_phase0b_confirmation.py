"""Deterministic races and dependency failures without external services."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.tool_confirmation_service import (
    ConfirmationError,
    ToolConfirmationService,
    _MemoryStore,
    _RedisStore,
)
from cygnusx.core.exceptions import DependencyUnavailableError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class RacingStore(_MemoryStore):
    """Hold both reads until both consumers saw APPROVED."""

    def __init__(self) -> None:
        super().__init__()
        self.barrier: asyncio.Barrier | None = None

    async def get(self, confirmation_id: str):
        record = await super().get(confirmation_id)
        if self.barrier:
            await self.barrier.wait()
        return record


async def test_forced_race_has_one_consumer() -> None:
    store = RacingStore()
    service = ToolConfirmationService(store)
    record = await service.create_for_tool("owner", "write", {"value": 1})
    await service.approve_by_human(user_id="owner", confirmation_id=record.confirmation_id)
    store.barrier = asyncio.Barrier(2)
    results = await asyncio.gather(*(
        service.consume_tool_confirmation("owner", record.confirmation_id, "write", {"value": 1})
        for _ in range(2)
    ), return_exceptions=True)
    assert sum(isinstance(result, ConfirmationError) for result in results) == 1
    assert sum(getattr(result, "status", None) == "CONSUMED" for result in results) == 1


async def test_task_approval_race_reserves_before_business_submission() -> None:
    store = RacingStore()
    service = ToolConfirmationService(store)
    context = ToolInvocationContext(user_id="owner", session_id="isolated",
                                    db=AsyncMock(spec=AsyncSession),
                                    extra={"human_confirmed": True})
    record = await service.create(context, "rna_seq", "RNA", TaskSubmitRequest(
        flow_id="rna_seq", name="isolated", parameters={"raw_data_path": "inbox"}))
    business = SimpleNamespace(submit=AsyncMock(return_value=SimpleNamespace(
        id="task-one", flow_id="rna_seq", status="queued", progress=0, created_at=None)))
    store.barrier = asyncio.Barrier(2)
    results = await asyncio.gather(*(
        service.approve(context, record.confirmation_id, business) for _ in range(2)
    ), return_exceptions=True)
    business.submit.assert_awaited_once()
    assert sum(isinstance(result, ConfirmationError) for result in results) == 1
    assert sum(getattr(result, "status", None) == "SUBMITTED" for result in results) == 1


async def test_boolean_context_cannot_approve_tool() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create_for_tool("owner", "write", {})
    with pytest.raises(ConfirmationError) as error:
        await service.consume_tool_confirmation(
            "owner", record.confirmation_id, "write", {}, human_confirmed=True
        )
    assert error.value.code == "CONFIRMATION_REQUIRED"


async def test_approved_record_expires_before_consumption_or_approval() -> None:
    store = _MemoryStore()
    service = ToolConfirmationService(store)
    record = await service.create_for_tool("owner", "write", {})
    await service.approve_by_human(user_id="owner", confirmation_id=record.confirmation_id)
    record.status = "APPROVED"
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await store.save(record)
    for operation in (
        service.approve_by_human(user_id="owner", confirmation_id=record.confirmation_id),
        service.consume_tool_confirmation("owner", record.confirmation_id, "write", {}),
    ):
        with pytest.raises(ConfirmationError) as error:
            await operation
        assert error.value.code == "CONFIRMATION_EXPIRED"


async def test_default_store_fails_closed_and_recovers(monkeypatch) -> None:
    client = SimpleNamespace(register_script=lambda _: None, get=AsyncMock())
    client.get.side_effect = RedisConnectionError("isolated test outage")
    monkeypatch.setattr("cygnusx.infrastructure.cache.redis_client.get_redis", lambda: client)
    service = ToolConfirmationService()
    with pytest.raises(DependencyUnavailableError) as error:
        await service.create_for_tool("owner", "write", {})
    assert error.value.status_code == 503
    assert service._store is None
    client.get.side_effect = None
    client.get.return_value = None
    assert isinstance(await service._get_store(), _RedisStore)


@pytest.mark.parametrize("operation", ["get", "save", "transition"])
async def test_cached_redis_outage_still_fails_closed(operation: str) -> None:
    client = SimpleNamespace(
        register_script=lambda _: None,
        get=AsyncMock(side_effect=RedisConnectionError()),
        set=AsyncMock(side_effect=RedisConnectionError()),
        ttl=AsyncMock(side_effect=RedisConnectionError()),
    )
    store = _RedisStore(client)
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create_for_tool("owner", "write", {})
    with pytest.raises(DependencyUnavailableError):
        if operation == "save":
            await store.save(record)
        elif operation == "get":
            await store.get(record.confirmation_id)
        else:
            await store.transition(record.confirmation_id, expected=("APPROVED",), to="CONSUMED")


async def test_redis_cas_loser_is_not_a_consumer() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create_for_tool("owner", "write", {})
    record.status = "CONSUMED"
    client = SimpleNamespace(
        register_script=lambda _: None, ttl=AsyncMock(return_value=60),
        eval=AsyncMock(return_value=json.dumps({"record": json.loads(record.to_json()), "changed": False})),
    )
    store = _RedisStore(client)
    assert await store.transition(record.confirmation_id, expected=("APPROVED",), to="CONSUMED") is None
    client.eval.return_value = json.dumps({"record": json.loads(record.to_json()), "changed": True})
    assert (await store.transition(record.confirmation_id, expected=("APPROVED",), to="CONSUMED")).status == "CONSUMED"
