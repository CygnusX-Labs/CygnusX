"""Offline orchestration tests: doubles are NOT an OS acceptance driver."""

import time
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from cygnusx.infrastructure.download.supervisor_server import (
    MutualTLSSupervisorServer,
    SupervisorDeniedError,
    SupervisorService,
    VerifiedAdmission,
)
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
)

pytestmark = pytest.mark.unit


def fixture():
    request = ExecutionBoundaryRequest(
        task_id=uuid4(),
        owner_id=uuid4(),
        attempt_id=uuid4(),
        execution_id=uuid4(),
        execution_epoch=1,
        admission_ref=uuid4(),
        budget_ref=uuid4(),
    )
    admission = VerifiedAdmission(
        request=request,
        caller_id="worker-a",
        environment_id="offline-only",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=int(time.time()) + 100,
        lease_deadline=int(time.time()) + 90,
        rx_limit_bytes=50,
        disk_limit_bytes=100,
        inode_limit=5,
    )
    authority = AsyncMock()
    authority.revalidate.return_value = admission
    backend = AsyncMock()
    backend.resolve.return_value = request
    return request, admission, authority, backend


def stopped(request, scope):
    return ExecutionBoundaryObservation(
        task_id=request.task_id,
        scope_ref=scope,
        execution_id=request.execution_id,
        execution_epoch=1,
        policy_revision="p1",
        state="stopped",
        reason="cancelled",
        rx_admitted_bytes=0,
        rx_observed_bytes=0,
        rx_dropped_bytes=0,
        rx_limit_bytes=50,
        disk_peak_allocated_bytes=0,
        disk_limit_bytes=100,
        inode_peak_used=0,
        inode_limit=5,
        started_at=0,
        stopped_at=0,
        live_processes=0,
        cgroup_populated=False,
        egress_revoked=True,
        quota_enforced=True,
        cleanup_complete=True,
        returncode=-9,
    )


@pytest.mark.asyncio
async def test_default_service_never_authorizes_start():
    request, _, _, backend = fixture()
    service = SupervisorService("offline", backend=backend)
    with pytest.raises(SupervisorDeniedError):
        await service.start(request, "worker-a")
    backend.prepare.assert_not_awaited()
    backend.exec_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_precedes_start_and_scope_is_epoch_deterministic():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    with pytest.raises(SupervisorDeniedError):
        await service.start(request, "worker-a")
    await service.recover()
    first = await service.start(request, "worker-a")
    second = await service.start(request, "worker-a")
    assert first == second
    assert backend.method_calls[0][0] == "recover_default_deny"
    assert [c[0] for c in backend.method_calls[1:]] == ["prepare", "exec_once"] * 2
    authority.revalidate.assert_awaited_with(request, "worker-a", claim=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["caller", "task", "lease", "budget"])
async def test_mismatched_admission_has_no_scope(mutation):
    request, admission, authority, backend = fixture()
    changes = {
        "caller": {"caller_id": "forged"},
        "task": {"request": request.model_copy(update={"task_id": uuid4()})},
        "lease": {"lease_deadline": int(time.time()) + 101},
        "budget": {"rx_limit_bytes": 0},
    }
    authority.revalidate.return_value = replace(admission, **changes[mutation])
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    with pytest.raises(SupervisorDeniedError):
        await service.start(request, "worker-a")
    backend.prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_exec_revokes_before_kill_without_releasing_budget():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    scope = await service.start(request, "worker-a")
    backend.reset_mock()
    backend.exec_once.side_effect = RuntimeError("uncertain exec")
    backend.observe.return_value = stopped(request, scope)
    with pytest.raises(RuntimeError, match="uncertain exec"):
        await service.start(request, "worker-a")
    assert [c[0] for c in backend.method_calls] == [
        "prepare",
        "exec_once",
        "revoke_egress",
        "kill_and_wait_empty",
        "observe",
    ]


@pytest.mark.asyncio
async def test_revoked_lease_stops_without_renew():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    scope = await service.start(request, "worker-a")
    backend.reset_mock()
    backend.observe.return_value = stopped(request, scope)
    authority.revalidate.side_effect = SupervisorDeniedError("revoked")
    with pytest.raises(SupervisorDeniedError):
        await service.act(request.task_id, scope, "worker-a", "lease")
    backend.renew.assert_not_awaited()
    assert [c[0] for c in backend.method_calls] == [
        "resolve",
        "revoke_egress",
        "kill_and_wait_empty",
        "observe",
    ]


@pytest.mark.asyncio
async def test_unknown_stop_does_not_become_evidence():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    scope = await service.start(request, "worker-a")
    backend.observe.return_value = stopped(request, scope).model_copy(
        update={"cleanup_complete": False}
    )
    with pytest.raises(ValueError, match="RECONCILIATION_REQUIRED"):
        await service.act(request.task_id, scope, "worker-a", "evidence")
    backend.evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_watchdog_independent_of_worker_calls():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    scope = await service.start(request, "worker-a")
    backend.expired_scopes.return_value = (scope,)
    backend.observe.return_value = stopped(request, scope)
    await service.watchdog_once()
    backend.revoke_egress.assert_awaited_with(scope)
    backend.kill_and_wait_empty.assert_awaited_with(scope)


@pytest.mark.asyncio
async def test_client_start_response_and_closed_route_contract():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    server = MutualTLSSupervisorServer(service, {})
    code, body = await server.dispatch(
        "POST", "/v1/executions", request.model_dump_json().encode(), "worker-a"
    )
    assert code == 200 and body["execution_id"] == str(request.execution_id)
    with pytest.raises(ValueError):
        await server.dispatch("POST", "/shell", b"{}", "worker-a")
