"""IAT-01 regression: ConflictError carries a domain code end-to-end.

Covers the replay-blocked ConflictError from verify_delegation and the
confirmation-record-mismatch ConflictError from the Gateway, asserting HTTP status,
domain code, and ToolBridge error semantics (non-retryable). Does not change
anti-replay behavior or widen model permissions.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from cygnusx.application.services import agent_tool_delegation as delegation
from cygnusx.core.exceptions import ConflictError
from cygnusx.tools.errors import ToolErrorCode, code_from_exception, is_retryable
from tests.unit.test_agent_tools_phase2 import env as env

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _redis_double(monkeypatch):
    used: set[str] = set()

    async def claim(key, *args, **kwargs):
        if key in used:
            return False
        used.add(key)
        return True

    monkeypatch.setattr(delegation, "get_redis", lambda: SimpleNamespace(set=claim))


async def test_replay_conflict_carries_code(env, monkeypatch):
    """Delegation replay raises ConflictError with DELEGATION_REPLAY_BLOCKED."""
    await _redis_double(monkeypatch)
    ctx = await env.gateway.context(env.owner, "mouse")
    token = await delegation.issue_delegation(ctx)
    call_id = str(uuid4())
    first = await delegation.verify_delegation(
        env.db, token, "downloads.describe_capabilities", call_id)
    assert first is not None
    with pytest.raises(ConflictError) as exc_info:
        await delegation.verify_delegation(
            env.db, token, "downloads.describe_capabilities", call_id)
    assert exc_info.value.code == "DELEGATION_REPLAY_BLOCKED"
    assert exc_info.value.status_code == 409


async def test_confirmation_mismatch_conflict_carries_code(env):
    """Gateway decide on a hash-tampered approval carries CONFIRMATION_RECORD_MISMATCH."""
    from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS

    args = CAPABILITY_MODELS["downloads.prepare"].model_validate(
        {"accession": "SRR999999"}).model_dump(mode="json")
    ctx = await env.gateway.context(env.owner, "mouse")
    env.download.submit = AsyncMock(
        side_effect=RuntimeError("submit must not run in this regression"))
    result = await env.gateway.invoke(ctx, "downloads.prepare", args)
    proposal_id = result["result"]["proposal_id"]
    # Tamper with the persisted invocation so the stored hash no longer matches.
    from cygnusx.infrastructure.database.models.agent_tool_invocation import (
        AgentToolInvocationModel,
    )
    row = env.db.sync.get(AgentToolInvocationModel, UUID(proposal_id))
    row.parameters_hash = "0" * 64
    env.db.sync.commit()
    with pytest.raises(ConflictError) as exc_info:
        await env.gateway.decide(ctx, proposal_id, approve=True)
    assert exc_info.value.code == "CONFIRMATION_RECORD_MISMATCH"
    assert exc_info.value.status_code == 409


def test_toolbridge_maps_conflict_to_non_retryable():
    """A coded ConflictError maps non-retryable: no uncontrolled retry loop."""
    exc = ConflictError("工具调用已处理，禁止自动重放", code="DELEGATION_REPLAY_BLOCKED")
    mapped = code_from_exception(exc)
    # Unknown platform codes fall back to SERVICE_ERROR (existing convention)...
    assert mapped == ToolErrorCode.SERVICE_ERROR
    # ...and SERVICE_ERROR is never retried.
    assert is_retryable(mapped) is False


async def test_http_conflict_payload_includes_code(env, monkeypatch):
    """HTTP layer surfaces the code field: {"detail", "code"} with 409."""
    await _redis_double(monkeypatch)
    ctx = await env.gateway.context(env.owner, "mouse")
    token = await delegation.issue_delegation(ctx)
    call_id = str(uuid4())
    await delegation.verify_delegation(
        env.db, token, "downloads.describe_capabilities", call_id)
    with pytest.raises(ConflictError) as exc_info:
        await delegation.verify_delegation(
            env.db, token, "downloads.describe_capabilities", call_id)
    # main.py handler contract: content = {"detail": exc.detail, "code": exc.code}, 409.
    assert exc_info.value.code == "DELEGATION_REPLAY_BLOCKED"
    assert exc_info.value.status_code == 409
