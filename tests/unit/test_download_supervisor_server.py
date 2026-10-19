"""Offline orchestration tests: doubles are NOT an OS acceptance driver."""

import asyncio
import hashlib
import ssl
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from cygnusx.infrastructure.download import supervisor_server as supervisor_module
from cygnusx.infrastructure.download.supervisor_server import (
    AllowedHttpDestination,
    MutualTLSSupervisorServer,
    SupervisorDeniedError,
    SupervisorService,
    VerifiedAdmission,
    http_targets_authorized,
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
    backend.start_state.return_value = "not_started"
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


def test_verified_http_targets_must_exactly_match_admitted_destination():
    _, admission, _, _ = fixture()
    valid = replace(
        admission,
        http_urls=("http://data.example.org/files/a.fastq",),
        allowed_destinations=(AllowedHttpDestination("data.example.org", 80, "/files/a.fastq"),),
    )
    assert http_targets_authorized(valid)
    assert not http_targets_authorized(
        replace(valid, http_urls=("http://evil.example.org/files/a.fastq",))
    )
    assert not http_targets_authorized(
        replace(valid, http_urls=("http://data.example.org/files/a.fastq?token=x",))
    )
    assert not http_targets_authorized(replace(valid, http_urls=()))


@pytest.mark.asyncio
async def test_default_service_never_authorizes_start():
    request, _, _, backend = fixture()
    service = SupervisorService("offline", backend=backend)
    with pytest.raises(SupervisorDeniedError):
        await service.start(request, "worker-a")
    backend.prepare.assert_not_awaited()
    backend.exec_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_listener_refuses_to_bind_without_trusted_backend():
    service = SupervisorService("offline")
    server = MutualTLSSupervisorServer(service, {})
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.verify_mode = ssl.CERT_REQUIRED

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_TRUSTED_BACKEND_UNAVAILABLE"):
        await server.listen("127.0.0.1", 0, tls)


@pytest.mark.asyncio
async def test_listener_rejects_non_mtls_before_recovery():
    service = SupervisorService("offline")
    server = MutualTLSSupervisorServer(service, {})
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.verify_mode = ssl.CERT_NONE

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_MTLS_REQUIRED"):
        await server.listen("127.0.0.1", 0, tls)
    assert service.ready is False


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
    assert [c[0] for c in backend.method_calls[1:]] == [
        "prepare",
        "start_state",
        "exec_once",
        "prepare",
        "start_state",
        "exec_once",
    ]
    authority.revalidate.assert_awaited_with(request, "worker-a", claim=True)


@pytest.mark.asyncio
async def test_retry_of_started_scope_does_not_exec_again():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    backend.start_state.side_effect = ["not_started", "started"]
    first = await service.start(request, "worker-a")
    second = await service.start(request, "worker-a")
    assert second == first
    assert backend.exec_once.await_count == 1


@pytest.mark.asyncio
async def test_unknown_started_state_fails_closed_without_exec():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    backend.start_state.return_value = "unknown"
    scope = SupervisorService._scope_for(request)
    backend.observe.return_value = stopped(request, scope)
    with pytest.raises(SupervisorDeniedError, match="SCOPE_STATE_UNKNOWN"):
        await service.start(request, "worker-a")
    backend.exec_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_started_state_fails_closed_without_exec():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    backend.start_state.return_value = "corrupt"
    scope = SupervisorService._scope_for(request)
    backend.observe.return_value = stopped(request, scope)
    with pytest.raises(SupervisorDeniedError, match="SCOPE_STATE_INVALID"):
        await service.start(request, "worker-a")
    backend.exec_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_identity_changes_for_attempt_even_when_epoch_matches():
    request, _, _, _ = fixture()
    other_attempt = request.model_copy(update={"attempt_id": uuid4()})
    assert SupervisorService._scope_for(request) != SupervisorService._scope_for(other_attempt)


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
        "start_state",
        "exec_once",
        "revoke_egress",
        "kill_and_wait_empty",
        "observe",
    ]


@pytest.mark.asyncio
async def test_stop_attempts_tree_kill_after_egress_revocation_error():
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    scope = await service.start(request, "worker-a")
    backend.reset_mock()
    backend.revoke_egress.side_effect = RuntimeError("isolated egress failure")

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_STOP_INCOMPLETE"):
        await service.act(request.task_id, scope, "worker-a", "stop")

    assert [call[0] for call in backend.method_calls] == [
        "resolve",
        "revoke_egress",
        "kill_and_wait_empty",
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
    backend.expired_scopes.return_value = (request,)
    backend.observe.return_value = stopped(request, scope)
    await service.watchdog_once()
    backend.revoke_egress.assert_awaited_with(scope)
    backend.kill_and_wait_empty.assert_awaited_with(scope)


@pytest.mark.asyncio
async def test_supervisor_serve_forever_runs_and_cancels_watchdog(monkeypatch):
    server = MutualTLSSupervisorServer(SupervisorService("offline"), {})
    watchdog_started = asyncio.Event()
    watchdog_stopped = asyncio.Event()

    class StopListenerError(Exception):
        pass

    class FakeListener:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def serve_forever(self):
            await watchdog_started.wait()
            raise StopListenerError

    async def fake_listen(_host, _port, _tls):
        return FakeListener()

    async def fake_watchdog(_interval):
        watchdog_started.set()
        try:
            await asyncio.Future()
        finally:
            watchdog_stopped.set()

    monkeypatch.setattr(server, "listen", fake_listen)
    monkeypatch.setattr(server, "watchdog", fake_watchdog)

    with pytest.raises(StopListenerError):
        await server.serve_forever("127.0.0.1", 0, ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER))

    assert watchdog_started.is_set()
    assert watchdog_stopped.is_set()


@pytest.mark.asyncio
async def test_watchdog_continues_after_one_scope_cleanup_error(caplog):
    request, _, authority, backend = fixture()
    second_request = request.model_copy(
        update={
            "task_id": uuid4(),
            "execution_id": uuid4(),
            "execution_epoch": 2,
        }
    )
    first_scope = SupervisorService._scope_for(request)
    second_scope = SupervisorService._scope_for(second_request)
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    backend.expired_scopes.return_value = (request, second_request)
    backend.observe.side_effect = [
        RuntimeError("isolated observation failure"),
        stopped(second_request, second_scope),
    ]

    await service.watchdog_once()

    assert backend.observe.await_count == 2
    backend.revoke_egress.assert_any_await(first_scope)
    backend.kill_and_wait_empty.assert_any_await(first_scope)
    backend.revoke_egress.assert_any_await(second_scope)
    backend.kill_and_wait_empty.assert_any_await(second_scope)
    assert "Supervisor lease cleanup failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["task_id", "execution_id", "execution_epoch", "scope_ref"])
async def test_stop_rejects_observation_for_another_execution(field):
    request, _, authority, backend = fixture()
    service = SupervisorService("offline", authority=authority, backend=backend)
    await service.recover()
    scope = await service.start(request, "worker-a")
    backend.observe.return_value = stopped(request, scope).model_copy(
        update={field: uuid4() if field != "execution_epoch" else 2}
    )

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_STOP_OBSERVATION_MISMATCH"):
        await service.act(request.task_id, scope, "worker-a", "stop")


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


@pytest.mark.asyncio
async def test_http_read_deadline_does_not_cancel_supervisor_operation(monkeypatch):
    certificate = b"isolated-client-certificate"
    caller_map = {hashlib.sha256(certificate).hexdigest(): "worker-a"}
    service = SupervisorService("offline")
    server = MutualTLSSupervisorServer(service, caller_map)
    monkeypatch.setattr(supervisor_module, "_REQUEST_READ_TIMEOUT_SECONDS", 0.001)

    async def slow_dispatch(method, path, body, caller):
        await asyncio.sleep(0.02)
        return 200, {"caller": caller}

    monkeypatch.setattr(server, "dispatch", slow_dispatch)

    class Reader:
        async def readuntil(self, separator):
            return b"POST /v1/executions HTTP/1.1\r\nContent-Length: 0\r\n\r\n"

        async def readexactly(self, size):
            assert size == 0
            return b""

    class Writer:
        def __init__(self):
            self.response = bytearray()
            self.closed = False

        def get_extra_info(self, name):
            assert name == "ssl_object"
            return SimpleNamespace(
                getpeercert=lambda *, binary_form: certificate if binary_form else None
            )

        def write(self, data):
            self.response.extend(data)

        async def drain(self):
            return None

        def close(self):
            self.closed = True

        async def wait_closed(self):
            return None

    writer = Writer()
    await server.handle(Reader(), writer)

    assert b"HTTP/1.1 200 Response" in writer.response
    assert b'"caller":"worker-a"' in writer.response
    assert writer.closed
