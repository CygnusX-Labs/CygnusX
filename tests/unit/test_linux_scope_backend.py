"""The Linux backend must refuse execution until OS enforcement is supplied."""

import asyncio
import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from cygnusx.infrastructure.download import linux_scope_backend as linux_backend
from cygnusx.infrastructure.download.linux_scope_backend import (
    LinuxEnforcedScopeBackend,
    _bwrap_command,
    _cgroup_populated,
    _claim_execution_start,
    _classify_start_state,
    _is_world_traversable,
    _pid_start_time,
    _record_process_identity,
    _scope_binding_matches,
    _trusted_binary_matches,
)
from cygnusx.infrastructure.download.supervisor_server import (
    AllowedHttpDestination,
    SupervisorDeniedError,
    VerifiedAdmission,
)
from cygnusx.infrastructure.download.trusted_execution import ExecutionBoundaryRequest

pytestmark = pytest.mark.unit


def _backend(tmp_path: Path, *, command_factory=None, cgroup_root: Path | None = None):
    return LinuxEnforcedScopeBackend(
        lambda: None,  # type: ignore[arg-type]
        root=tmp_path / "scopes",
        command_factory=command_factory,
        cgroup_root=cgroup_root or (tmp_path / "cgroup"),
        require_bwrap=False,
    )


def test_backend_denies_when_cgroup_root_is_unavailable(tmp_path: Path) -> None:
    backend = _backend(tmp_path, command_factory=lambda _admission, _work: ("true",))

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_CGROUP_V2_UNAVAILABLE"):
        backend._check_runtime()


@pytest.mark.asyncio
async def test_recovery_checks_capabilities_before_creating_scope_root(tmp_path: Path) -> None:
    backend = _backend(tmp_path, command_factory=lambda _admission, _work: ("true",))

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_CGROUP_V2_UNAVAILABLE"):
        await backend.recover_default_deny()
    assert not (tmp_path / "scopes").exists()


@pytest.mark.asyncio
async def test_recovery_stops_persisted_running_scope_before_ready(tmp_path: Path) -> None:
    scope = uuid4()
    row = SimpleNamespace(
        scope_ref=scope,
        state="running",
        pid=12345,
        pid_start_time="987",
        host_boot_id="old-boot",
        stopped_at=None,
        reason="running",
        cleanup_complete=False,
    )
    cgroup = tmp_path / "cgroup" / "cygnusx" / str(scope)
    cgroup.mkdir(parents=True)
    kill_file = cgroup / "cgroup.kill"
    kill_file.touch()
    (cgroup / "cgroup.events").write_text("populated 0\n")

    class Rows:
        def all(self):
            return [row]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalars(self, _statement):
            return Rows()

        async def scalar(self, _statement):
            return row

        async def commit(self):
            return None

    backend = _backend(tmp_path, cgroup_root=tmp_path / "cgroup")
    backend._sessions = lambda: FakeSession()  # type: ignore[method-assign]

    await backend.recover_default_deny()

    assert kill_file.read_text() == "1"
    assert row.state == "stopped"
    assert row.pid is None
    assert row.pid_start_time is None
    assert row.host_boot_id is None


def test_backend_denies_without_trusted_command_factory(tmp_path: Path) -> None:
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    backend = _backend(tmp_path, cgroup_root=cgroup_root)

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_COMMAND_FACTORY_UNCONFIGURED"):
        backend._check_runtime()


def test_backend_never_claims_signed_evidence_without_supervisor_key(tmp_path: Path) -> None:
    backend = _backend(tmp_path)

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_SIGNING_KEY_UNCONFIGURED"):
        asyncio.run(backend.evidence(uuid4()))


@pytest.mark.asyncio
async def test_observe_refuses_to_invent_runtime_measurements(tmp_path: Path) -> None:
    backend = _backend(tmp_path)

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_RUNTIME_METRICS_UNAVAILABLE"):
        await backend.observe(uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(("rowcount", "should_commit"), [(1, True), (0, False)])
async def test_lease_renewal_is_a_running_unexpired_scope_cas(
    tmp_path: Path, rowcount: int, should_commit: bool
) -> None:
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
        environment_id="test-runner",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=int((datetime.now(UTC) + timedelta(minutes=1)).timestamp()),
        lease_deadline=int((datetime.now(UTC) + timedelta(seconds=20)).timestamp()),
        rx_limit_bytes=100,
        disk_limit_bytes=100,
        inode_limit=10,
    )

    class FakeSession:
        committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, _statement):
            self.statement = str(_statement)
            return SimpleNamespace(rowcount=rowcount)

        async def commit(self):
            self.committed = True

    session = FakeSession()
    backend = _backend(tmp_path)
    backend._sessions = lambda: session  # type: ignore[method-assign]

    if rowcount:
        await backend.renew(uuid4(), admission)
        assert session.committed is True
        assert "state" in session.statement
        assert "lease_deadline" in session.statement
    else:
        with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_LEASE_SCOPE_NOT_RENEWABLE"):
            await backend.renew(uuid4(), admission)
        assert session.committed is False


@pytest.mark.asyncio
async def test_unknown_scope_persists_validated_failure_reason(tmp_path: Path) -> None:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement):
            self.statement = statement

        async def commit(self):
            self.committed = True

    session = FakeSession()
    backend = _backend(tmp_path)
    backend._sessions = lambda: session  # type: ignore[method-assign]

    await backend._mark_unknown(uuid4(), "bwrap_unavailable")

    assert session.statement.compile().params["reason"] == "bwrap_unavailable"
    assert session.statement.compile().params["state"] == "unknown"
    assert session.committed is True


@pytest.mark.asyncio
async def test_unknown_scope_rejects_untrusted_reason_text(tmp_path: Path) -> None:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement):
            self.statement = statement

        async def commit(self):
            return None

    session = FakeSession()
    backend = _backend(tmp_path)
    backend._sessions = lambda: session  # type: ignore[method-assign]

    await backend._mark_unknown(uuid4(), "bad reason; overwrite")

    assert session.statement.compile().params["reason"] == "unknown"


def test_pid_start_time_is_reported_as_kernel_identity_not_boolean() -> None:
    start_time = _pid_start_time(os.getpid())
    assert start_time is not None
    assert start_time.isdecimal()


def test_missing_pid_start_time_is_persistable_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace()
    monkeypatch.setattr(linux_backend, "_pid_start_time", lambda _pid: None)
    monkeypatch.setattr(linux_backend, "_host_boot_id", lambda: "test-boot")

    assert not _record_process_identity(row, 123)
    assert row.state == "unknown"
    assert row.reason == "process_identity_unavailable"
    assert row.pid == 123
    assert row.host_boot_id == "test-boot"


def test_cgroup_population_requires_authoritative_kernel_event(tmp_path: Path) -> None:
    cgroup = tmp_path / "cg"
    cgroup.mkdir()
    (cgroup / "cgroup.events").write_text("populated 1\nfrozen 0\n")
    assert _cgroup_populated(cgroup) is True
    (cgroup / "cgroup.events").write_text("populated 0\nfrozen 0\n")
    assert _cgroup_populated(cgroup) is False
    (cgroup / "cgroup.events").write_text("frozen 0\n")
    assert _cgroup_populated(cgroup) is None


@pytest.mark.parametrize(
    ("initial_state", "expected_launch", "expected_state"),
    [
        ("prepared", True, "starting"),
        ("starting", False, "starting"),
        ("running", False, "running"),
    ],
)
def test_locked_scope_start_claim_is_idempotent(
    initial_state: str, expected_launch: bool, expected_state: str
) -> None:
    row = SimpleNamespace(state=initial_state, egress_revoked=True)

    assert _claim_execution_start(row) is expected_launch  # type: ignore[arg-type]
    assert row.state == expected_state
    assert row.egress_revoked is (not expected_launch)


def test_locked_unknown_scope_cannot_claim_start() -> None:
    row = SimpleNamespace(state="unknown", egress_revoked=True)

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_START_STATE_UNKNOWN"):
        _claim_execution_start(row)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["starting", "running"])
async def test_exec_once_does_not_spawn_when_durable_claim_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    row = SimpleNamespace(state=state, egress_revoked=False)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def begin(self):
            return self

        async def scalar(self, _statement):
            return row

    session = FakeSession()
    command_factory_called = False

    def command_factory(_admission, _work):
        nonlocal command_factory_called
        command_factory_called = True
        return ("/usr/bin/true",)

    backend = _backend(tmp_path, command_factory=command_factory)
    backend._sessions = lambda: session  # type: ignore[method-assign]
    monkeypatch.setattr(backend, "_check_runtime", lambda: None)

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
        environment_id="test-runner",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=int((datetime.now(UTC) + timedelta(minutes=1)).timestamp()),
        lease_deadline=int((datetime.now(UTC) + timedelta(seconds=20)).timestamp()),
        rx_limit_bytes=100,
        disk_limit_bytes=100,
        inode_limit=10,
    )

    await backend.exec_once(uuid4(), admission)

    assert command_factory_called is False
    assert row.state == state


@pytest.mark.asyncio
async def test_prepare_recovers_concurrent_unique_insert_for_same_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        environment_id="test-runner",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=int((datetime.now(UTC) + timedelta(minutes=1)).timestamp()),
        lease_deadline=int((datetime.now(UTC) + timedelta(seconds=20)).timestamp()),
        rx_limit_bytes=100,
        disk_limit_bytes=100,
        inode_limit=10,
        http_urls=("http://example.test/file",),
        allowed_destinations=(AllowedHttpDestination("example.test", 80, "/file"),),
    )
    scope = uuid4()
    existing = SimpleNamespace(
        task_id=request.task_id,
        owner_id=request.owner_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        execution_epoch=request.execution_epoch,
        admission_ref=request.admission_ref,
        budget_ref=request.budget_ref,
        caller_id=admission.caller_id,
        environment_id=admission.environment_id,
        policy_revision=admission.policy_digest,
        lease_deadline=datetime.now(UTC) + timedelta(seconds=7),
    )
    persisted_lease_deadline = existing.lease_deadline

    class FakeSession:
        def __init__(self):
            self.read_count = 0
            self.rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _statement):
            self.read_count += 1
            return None if self.read_count == 1 else existing

        def add(self, _row):
            return None

        async def commit(self):
            raise IntegrityError("insert", {}, RuntimeError("unique conflict"))

        async def rollback(self):
            self.rolled_back = True

    cgroup = tmp_path / "cgroup" / "cygnusx" / str(scope)
    cgroup.mkdir(parents=True)
    (cgroup / "cgroup.kill").touch()
    (cgroup / "cgroup.events").write_text("populated 0\n")
    session = FakeSession()
    backend = _backend(tmp_path, cgroup_root=tmp_path / "cgroup")
    backend._sessions = lambda: session  # type: ignore[method-assign]
    monkeypatch.setattr(backend, "_check_runtime", lambda: None)

    await backend.prepare(scope, admission)

    assert session.rolled_back is True
    assert session.read_count == 2
    assert existing.lease_deadline == persisted_lease_deadline


@pytest.mark.asyncio
async def test_prepare_persists_scope_before_cgroup_and_marks_failure_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        environment_id="test-runner",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=int((datetime.now(UTC) + timedelta(minutes=1)).timestamp()),
        lease_deadline=int((datetime.now(UTC) + timedelta(seconds=20)).timestamp()),
        rx_limit_bytes=100,
        disk_limit_bytes=100,
        inode_limit=10,
        http_urls=("http://example.test/file",),
        allowed_destinations=(AllowedHttpDestination("example.test", 80, "/file"),),
    )

    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.added = None
            self.failure_update = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _statement):
            return None

        def add(self, row):
            self.added = row

        async def execute(self, statement):
            self.failure_update = statement

        async def commit(self):
            self.commits += 1

    scope = uuid4()
    cgroup_root = tmp_path / "cgroup"
    (cgroup_root / "cygnusx" / str(scope)).mkdir(parents=True)
    session = FakeSession()
    backend = _backend(tmp_path, cgroup_root=cgroup_root)
    backend._sessions = lambda: session  # type: ignore[method-assign]
    monkeypatch.setattr(backend, "_check_runtime", lambda: None)

    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_CGROUP_V2_CONTROLS_UNAVAILABLE"):
        await backend.prepare(scope, admission)

    assert session.added.state == "prepared"
    assert session.commits == 2
    assert session.failure_update.compile().params["state"] == "unknown"
    assert session.failure_update.compile().params["reason"] == "cgroup_controls_unavailable"


@pytest.mark.asyncio
async def test_start_state_waits_for_durable_starting_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        environment_id="test-runner",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=int((datetime.now(UTC) + timedelta(minutes=1)).timestamp()),
        lease_deadline=int((datetime.now(UTC) + timedelta(seconds=20)).timestamp()),
        rx_limit_bytes=100,
        disk_limit_bytes=100,
        inode_limit=10,
    )

    class FakeSession:
        states = iter(("starting", "running"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _statement):
            return SimpleNamespace(
                state=next(self.states),
                execution_id=request.execution_id,
                pid=os.getpid(),
                pid_start_time="123",
                host_boot_id="test-boot",
            )

    backend = _backend(tmp_path)
    backend._sessions = lambda: FakeSession()  # type: ignore[method-assign]
    monkeypatch.setattr(linux_backend, "_cgroup_populated", lambda _path: True)
    monkeypatch.setattr(linux_backend, "_pid_start_time", lambda _pid: "123")
    monkeypatch.setattr(linux_backend, "_host_boot_id", lambda: "test-boot")

    async def no_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(linux_backend.asyncio, "sleep", no_wait)

    assert await backend.start_state(uuid4(), admission) == "started"


@pytest.mark.parametrize(
    ("state", "identity_matches", "populated", "expected"),
    [
        ("prepared", False, False, "not_started"),
        ("prepared", False, True, "unknown"),
        ("prepared", False, None, "unknown"),
        ("running", True, True, "started"),
        ("running", False, True, "unknown"),
        ("running", True, None, "unknown"),
        ("stopped", False, False, "unknown"),
        ("corrupt", False, False, "unknown"),
    ],
)
def test_start_state_only_allows_prepared_empty_scope_or_verified_running(
    state: str, identity_matches: bool, populated: bool | None, expected: str
) -> None:
    assert _classify_start_state(state, identity_matches, populated) == expected


def test_bwrap_contract_uses_private_user_namespace_and_isolated_writable_paths(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    user_dirs = {"home": work / "home", "tmp": work / "tmp"}
    user_dirs["cache"] = user_dirs["home"] / ".cache"
    command = _bwrap_command("/usr/bin/bwrap", ("/usr/bin/tool", "--version"), work, user_dirs)

    assert command[command.index("--unshare-user") + 1 :][:3] == ["--uid", "0", "--gid"]
    assert command.count("--unshare-pid") == 1
    assert command.count("--unshare-net") == 1
    assert command[command.index("--bind") + 1 : command.index("--bind") + 3] == [
        str(work),
        "/work",
    ]
    assert "/home/cygnusx" in command
    assert "/tmp" in command
    assert command[command.index("XDG_CACHE_HOME") + 1] == "/home/cygnusx/.cache"
    assert command[command.index("--clearenv")] == "--clearenv"


def test_runtime_uid_cannot_enter_scope_through_private_ancestor(tmp_path: Path) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    scope_parent = private_root / "supervisor-scopes"
    scope_parent.mkdir(mode=0o711)

    assert not _is_world_traversable(scope_parent)


def test_trusted_binary_rejects_symlinks_and_digest_mismatch(tmp_path: Path) -> None:
    symlink = tmp_path / "tool"
    symlink.symlink_to("/usr/bin/true")

    assert not _trusted_binary_matches(str(symlink), "0" * 64)
    assert not _trusted_binary_matches("/usr/bin/true", "0" * 64)


def test_trusted_binary_accepts_only_immutable_usr_binary_with_matching_digest() -> None:
    binary = Path("/usr/bin/true")
    if not binary.is_file():
        pytest.skip("system /usr/bin/true unavailable")
    if binary.lstat().st_uid != 0:
        pytest.skip("system binary is not owned by host root in this user namespace")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()

    assert _trusted_binary_matches(str(binary), digest)


def test_existing_scope_binding_includes_attempt_admission_and_budget() -> None:
    request = ExecutionBoundaryRequest(
        task_id=uuid4(),
        owner_id=uuid4(),
        attempt_id=uuid4(),
        execution_id=uuid4(),
        execution_epoch=3,
        admission_ref=uuid4(),
        budget_ref=uuid4(),
    )
    admission = VerifiedAdmission(
        request=request,
        caller_id="worker-a",
        environment_id="test-runner",
        policy_digest="a" * 64,
        tool_digest="b" * 64,
        project_id=uuid4(),
        source_digest="c" * 64,
        destination_policy_digest="d" * 64,
        expires_at=2_000,
        lease_deadline=1_900,
        rx_limit_bytes=100,
        disk_limit_bytes=100,
        inode_limit=10,
    )
    row = SimpleNamespace(
        task_id=request.task_id,
        owner_id=request.owner_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        execution_epoch=request.execution_epoch,
        admission_ref=request.admission_ref,
        budget_ref=request.budget_ref,
        caller_id=admission.caller_id,
        environment_id=admission.environment_id,
        policy_revision=admission.policy_digest,
    )

    assert _scope_binding_matches(row, admission)  # type: ignore[arg-type]
    row.budget_ref = uuid4()
    assert not _scope_binding_matches(row, admission)  # type: ignore[arg-type]
    row.budget_ref = request.budget_ref
    changed_request = request.model_copy(update={"attempt_id": uuid4()})
    assert not _scope_binding_matches(row, replace(admission, request=changed_request))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_egress_revoke_does_not_claim_a_database_flag_is_enforcement(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    with pytest.raises(SupervisorDeniedError, match="SUPERVISOR_EGRESS_CONTROLLER_UNAVAILABLE"):
        await backend.revoke_egress(uuid4())
