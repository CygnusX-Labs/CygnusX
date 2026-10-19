"""Fail-closed Linux Supervisor backend for an explicitly supplied trusted command.

The backend owns the scope directory and process lifecycle.  It never accepts a
URL, argv, environment, or path from a Worker.  A deployment must provide a
trusted command factory and a writable cgroup v2 root; otherwise startup is
refused.  This keeps the implementation useful in an operations-owned Linux
runner without turning a normal web/worker process into a fake Supervisor.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import stat
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cygnusx.infrastructure.database.models.download_execution import DownloadExecutionScopeModel
from cygnusx.infrastructure.download.supervisor_server import (
    EnforcedScopeBackend,
    SupervisorDeniedError,
    VerifiedAdmission,
    http_targets_authorized,
)
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
    ExecutionPublicationContext,
)

if TYPE_CHECKING:
    from cygnusx.infrastructure.download.supervisor_server import SupervisorService

CommandFactory = Callable[[VerifiedAdmission, Path], Sequence[str]]


def create_linux_supervisor_service(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    supervisor_id: str,
    root: Path,
    command_factory: CommandFactory,
    launcher_path: Path = Path("/usr/local/libexec/cygnusx-scope-exec"),
) -> SupervisorService:
    """Explicit production wiring; callers must opt in to the OS backend."""
    from cygnusx.infrastructure.download.supervisor_server import SupervisorService

    backend = LinuxEnforcedScopeBackend(
        session_factory,
        root=root,
        command_factory=command_factory,
        launcher_path=launcher_path,
    )
    from cygnusx.infrastructure.download.supervisor_authority import DatabaseAdmissionAuthority

    return SupervisorService(
        supervisor_id,
        authority=DatabaseAdmissionAuthority(session_factory=session_factory),
        backend=backend,
    )


class LinuxEnforcedScopeBackend(EnforcedScopeBackend):
    """Durable scope implementation; runtime gates remain closed by policy."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        root: Path,
        command_factory: CommandFactory | None = None,
        launcher_path: Path | None = Path("/usr/local/libexec/cygnusx-scope-exec"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        require_bwrap: bool = True,
    ) -> None:
        self._sessions = session_factory
        self._root = root
        self._command_factory = command_factory
        self._launcher_path = launcher_path
        self._cgroup_root = cgroup_root
        self._require_bwrap = require_bwrap
        self._process_waiters: dict[UUID, asyncio.Task[None]] = {}

    def _scope_dir(self, scope: UUID) -> Path:
        return self._root / "supervisor-scopes" / str(scope)

    def _cgroup_dir(self, scope: UUID) -> Path:
        return self._cgroup_root / "cygnusx" / str(scope)

    def _check_runtime(self) -> None:
        if os.name != "posix" or not Path("/proc/self/cgroup").exists():
            raise SupervisorDeniedError("SUPERVISOR_LINUX_REQUIRED")
        if self._require_bwrap and shutil.which("bwrap") is None:
            raise SupervisorDeniedError("SUPERVISOR_BWRAP_UNAVAILABLE")
        if not self._cgroup_root.is_dir() or not os.access(self._cgroup_root, os.W_OK):
            raise SupervisorDeniedError("SUPERVISOR_CGROUP_V2_UNAVAILABLE")
        if self._command_factory is None:
            raise SupervisorDeniedError("SUPERVISOR_COMMAND_FACTORY_UNCONFIGURED")
        launcher = self._launcher_path
        try:
            metadata = launcher.lstat() if launcher is not None else None
        except OSError:
            metadata = None
        if (
            launcher is None
            or metadata is None
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
            or not os.access(launcher, os.X_OK)
        ):
            raise SupervisorDeniedError("SUPERVISOR_ATOMIC_LAUNCHER_UNAVAILABLE")

    async def prepare(self, scope: UUID, admission: VerifiedAdmission) -> None:
        self._check_runtime()
        if not http_targets_authorized(admission):
            raise SupervisorDeniedError("SUPERVISOR_HTTP_TARGET_BINDING_INVALID")
        directory = self._scope_dir(scope)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        scopes_root = directory.parent
        scopes_root.chmod(0o711)
        directory.chmod(0o711)
        async with self._sessions() as session:
            row = await session.scalar(
                select(DownloadExecutionScopeModel)
                .where(DownloadExecutionScopeModel.scope_ref == scope)
                .with_for_update()
            )
            if row is None:
                session.add(
                    DownloadExecutionScopeModel(
                        scope_ref=scope,
                        admission_ref=admission.request.admission_ref,
                        budget_ref=admission.request.budget_ref,
                        task_id=admission.request.task_id,
                        owner_id=admission.request.owner_id,
                        attempt_id=admission.request.attempt_id,
                        execution_id=admission.request.execution_id,
                        execution_epoch=admission.request.execution_epoch,
                        caller_id=admission.caller_id,
                        environment_id=admission.environment_id,
                        policy_revision=admission.policy_digest,
                        state="prepared",
                        lease_deadline=datetime.fromtimestamp(admission.lease_deadline, UTC),
                        reason="running",
                        egress_revoked=True,
                        cleanup_complete=False,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    row = await session.scalar(
                        select(DownloadExecutionScopeModel).where(
                            DownloadExecutionScopeModel.scope_ref == scope
                        )
                    )
                    if row is None or not _scope_binding_matches(row, admission):
                        raise SupervisorDeniedError("SUPERVISOR_SCOPE_BINDING_REJECTED") from None
            elif not _scope_binding_matches(row, admission):
                raise SupervisorDeniedError("SUPERVISOR_SCOPE_BINDING_REJECTED")
            else:
                await session.commit()
        cgroup = self._cgroup_dir(scope)
        try:
            cgroup.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError:
            await self._mark_unknown(scope, "cgroup_prepare_failed")
            raise SupervisorDeniedError("SUPERVISOR_CGROUP_V2_CONTROLS_UNAVAILABLE") from None
        if not (cgroup / "cgroup.kill").is_file() or _cgroup_populated(cgroup) is None:
            await self._mark_unknown(scope, "cgroup_controls_unavailable")
            raise SupervisorDeniedError("SUPERVISOR_CGROUP_V2_CONTROLS_UNAVAILABLE")

    async def start_state(
        self, scope: UUID, admission: VerifiedAdmission
    ) -> Literal["started", "not_started", "unknown"]:
        for attempt in range(101):
            async with self._sessions() as session:
                row = await session.scalar(
                    select(DownloadExecutionScopeModel).where(
                        DownloadExecutionScopeModel.scope_ref == scope
                    )
                )
            if row is None or row.execution_id != admission.request.execution_id:
                return "unknown"
            identity_matches = bool(
                row.pid
                and row.pid_start_time
                and row.host_boot_id == _host_boot_id()
                and _pid_start_time(row.pid) == row.pid_start_time
            )
            populated = _cgroup_populated(self._cgroup_dir(scope))
            state = _classify_start_state(row.state, identity_matches, populated)
            if row.state != "starting" or attempt == 100:
                return state
            await asyncio.sleep(0.05)
        return "unknown"

    async def exec_once(self, scope: UUID, admission: VerifiedAdmission) -> None:
        self._check_runtime()
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(DownloadExecutionScopeModel)
                .where(DownloadExecutionScopeModel.scope_ref == scope)
                .with_for_update()
            )
            if row is None:
                raise SupervisorDeniedError("SUPERVISOR_START_STATE_UNKNOWN")
            should_launch = _claim_execution_start(row)
        if not should_launch:
            return
        work = self._scope_dir(scope) / "work"
        work.mkdir(mode=0o700, exist_ok=True)
        if not _is_world_traversable(work.parent):
            await self._mark_unknown(scope, "scope_path_untraversable")
            raise SupervisorDeniedError("SUPERVISOR_SCOPE_PATH_PERMISSION_DENIED")
        user_dirs = {"home": work / "home", "tmp": work / "tmp"}
        user_dirs["cache"] = user_dirs["home"] / ".cache"
        for path in user_dirs.values():
            path.mkdir(mode=0o700, exist_ok=True)
            os.chown(path, 10001, 10001)
            path.chmod(0o700)
        os.chown(work, 10001, 10001)
        work.chmod(0o700)
        command = list(self._command_factory(admission, work)) if self._command_factory else []
        if (
            not command
            or any(not isinstance(part, str) or "\x00" in part for part in command)
            or not _trusted_binary_matches(command[0], admission.tool_digest)
        ):
            await self._mark_unknown(scope, "invalid_command")
            raise SupervisorDeniedError("SUPERVISOR_TOOL_DIGEST_REJECTED")
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            await self._mark_unknown(scope, "bwrap_unavailable")
            raise SupervisorDeniedError("SUPERVISOR_BWRAP_UNAVAILABLE")
        wrapped = _bwrap_command(bwrap_path, command, work, user_dirs)
        try:
            assert self._launcher_path is not None
            process = await asyncio.create_subprocess_exec(
                str(self._launcher_path),
                "--cgroup",
                str(self._cgroup_dir(scope)),
                "--",
                *wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                env={},
            )
        except (OSError, ValueError):
            await self._mark_unknown(scope, "spawn_failed")
            raise SupervisorDeniedError("SUPERVISOR_EXEC_FAILED") from None
        try:
            async with asyncio.timeout(5.0):
                pid_line = await process.stdout.readline() if process.stdout else b""
            child_pid = int(pid_line.strip())
            if child_pid <= 0:
                raise ValueError("SUPERVISOR_CHILD_PID_INVALID")
        except (TimeoutError, ValueError):
            await self._mark_unknown(scope, "atomic_launcher_start_unknown")
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise SupervisorDeniedError("SUPERVISOR_ATOMIC_LAUNCH_UNKNOWN") from None
        async with self._sessions() as session:
            row = await session.scalar(
                select(DownloadExecutionScopeModel)
                .where(DownloadExecutionScopeModel.scope_ref == scope)
                .with_for_update()
            )
            if row is None:
                raise SupervisorDeniedError("SUPERVISOR_SCOPE_MISSING")
            if not _record_process_identity(row, child_pid):
                await session.commit()
                raise SupervisorDeniedError("SUPERVISOR_PROCESS_IDENTITY_UNAVAILABLE")
            await session.commit()
        self._process_waiters[scope] = asyncio.create_task(
            self._record_process_exit(scope, process)
        )

    async def _record_process_exit(self, scope: UUID, process: asyncio.subprocess.Process) -> None:
        returncode = await process.wait()
        cgroup = self._cgroup_dir(scope)
        populated = _cgroup_populated(cgroup)
        if populated is None:
            await self._mark_unknown(scope, "cgroup_state_unavailable")
            return
        if populated:
            try:
                (cgroup / "cgroup.kill").write_text("1")
            except OSError:
                await self._mark_unknown(scope, "orphan_process_cleanup_failed")
                return
            deadline = time.monotonic() + 5.0
            while _cgroup_populated(cgroup) is not False:
                if time.monotonic() >= deadline:
                    await self._mark_unknown(scope, "orphan_processes_remain")
                    return
                await asyncio.sleep(0.05)
        async with self._sessions() as session:
            row = await session.scalar(
                select(DownloadExecutionScopeModel)
                .where(DownloadExecutionScopeModel.scope_ref == scope)
                .with_for_update()
            )
            if row is not None and row.state != "stopped":
                row.state = "stopped"
                row.returncode = returncode
                row.stopped_at = datetime.now(UTC)
                row.reason = "completed" if returncode == 0 and not populated else "failed"
                row.cleanup_complete = False
                await session.commit()
        self._process_waiters.pop(scope, None)

    async def observe(self, scope: UUID) -> ExecutionBoundaryObservation:
        raise SupervisorDeniedError("SUPERVISOR_RUNTIME_METRICS_UNAVAILABLE")

    async def revoke_egress(self, scope: UUID) -> None:
        # A private netns starts with no routes, but this process has no trusted
        # network-policy controller to prove or revoke its state after launch.
        raise SupervisorDeniedError("SUPERVISOR_EGRESS_CONTROLLER_UNAVAILABLE")

    async def kill_and_wait_empty(self, scope: UUID) -> None:
        cgroup = self._cgroup_dir(scope)
        kill_file = cgroup / "cgroup.kill"
        if not kill_file.is_file():
            raise SupervisorDeniedError("SUPERVISOR_CGROUP_KILL_UNAVAILABLE")
        try:
            kill_file.write_text("1")
        except OSError as exc:
            await self._mark_unknown(scope, "cgroup_kill_failed")
            raise SupervisorDeniedError("SUPERVISOR_CGROUP_KILL_FAILED") from exc
        deadline = time.monotonic() + 5.0
        while _cgroup_populated(cgroup) is not False:
            if time.monotonic() >= deadline:
                await self._mark_unknown(scope, "cgroup_not_empty")
                raise SupervisorDeniedError("SUPERVISOR_CGROUP_NOT_EMPTY")
            await asyncio.sleep(0.05)
        async with self._sessions() as session:
            row = await session.scalar(
                select(DownloadExecutionScopeModel)
                .where(DownloadExecutionScopeModel.scope_ref == scope)
                .with_for_update()
            )
            if row is not None:
                row.state = "stopped"
                row.pid = None
                row.stopped_at = datetime.now(UTC)
                row.reason = "cancelled"
                row.pid_start_time = None
                row.host_boot_id = None
                row.cleanup_complete = False
                await session.commit()

    async def expired_scopes(self) -> tuple[ExecutionBoundaryRequest, ...]:
        now = datetime.now(UTC)
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(DownloadExecutionScopeModel).where(
                        DownloadExecutionScopeModel.state.in_(("starting", "running", "unknown")),
                        DownloadExecutionScopeModel.lease_deadline <= now,
                    )
                )
            ).all()
            return tuple(
                ExecutionBoundaryRequest(
                    task_id=r.task_id,
                    owner_id=r.owner_id,
                    attempt_id=r.attempt_id,
                    execution_id=r.execution_id,
                    execution_epoch=r.execution_epoch,
                    admission_ref=r.admission_ref,
                    budget_ref=r.budget_ref,
                    protocol="http",
                )
                for r in rows
            )

    async def recover_default_deny(self) -> None:
        if os.name != "posix":
            raise SupervisorDeniedError("SUPERVISOR_LINUX_REQUIRED")
        if not self._cgroup_root.is_dir():
            raise SupervisorDeniedError("SUPERVISOR_CGROUP_V2_UNAVAILABLE")
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(DownloadExecutionScopeModel).where(
                        DownloadExecutionScopeModel.state.in_(("starting", "running", "unknown"))
                    )
                )
            ).all()
        for row in rows:
            try:
                await self.kill_and_wait_empty(row.scope_ref)
            except SupervisorDeniedError:
                await self._mark_unknown(row.scope_ref, "recovery_unverified")

    async def resolve(self, task: UUID, scope: UUID, caller_id: str) -> ExecutionBoundaryRequest:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DownloadExecutionScopeModel).where(
                    DownloadExecutionScopeModel.scope_ref == scope,
                    DownloadExecutionScopeModel.task_id == task,
                    DownloadExecutionScopeModel.caller_id == caller_id,
                )
            )
            if row is None:
                raise SupervisorDeniedError("SUPERVISOR_SCOPE_NOT_FOUND")
            return ExecutionBoundaryRequest(
                task_id=row.task_id,
                owner_id=row.owner_id,
                attempt_id=row.attempt_id,
                execution_id=row.execution_id,
                execution_epoch=row.execution_epoch,
                admission_ref=row.admission_ref,
                budget_ref=row.budget_ref,
                protocol="http",
            )

    async def evidence(self, scope: UUID) -> ExecutionPublicationContext:
        raise SupervisorDeniedError("SUPERVISOR_SIGNING_KEY_UNCONFIGURED")

    async def renew(self, scope: UUID, admission: VerifiedAdmission) -> None:
        now = datetime.now(UTC)
        new_deadline = datetime.fromtimestamp(admission.lease_deadline, UTC)
        if new_deadline <= now:
            raise SupervisorDeniedError("SUPERVISOR_LEASE_DEADLINE_EXPIRED")
        async with self._sessions() as session:
            result = await session.execute(
                update(DownloadExecutionScopeModel)
                .where(
                    DownloadExecutionScopeModel.scope_ref == scope,
                    DownloadExecutionScopeModel.execution_id == admission.request.execution_id,
                    DownloadExecutionScopeModel.state == "running",
                    DownloadExecutionScopeModel.lease_deadline > now,
                )
                .values(lease_deadline=new_deadline)
            )
            if getattr(result, "rowcount", None) != 1:
                raise SupervisorDeniedError("SUPERVISOR_LEASE_SCOPE_NOT_RENEWABLE")
            await session.commit()

    async def _mark_unknown(self, scope: UUID, reason: str) -> None:
        reason_code = (
            reason
            if reason
            and len(reason) <= 32
            and reason.isascii()
            and reason.replace("_", "").isalnum()
            else "unknown"
        )
        async with self._sessions() as session:
            await session.execute(
                update(DownloadExecutionScopeModel)
                .where(DownloadExecutionScopeModel.scope_ref == scope)
                .values(state="unknown", reason=reason_code, cleanup_complete=False)
            )
            await session.commit()


def _pid_start_time(pid: int) -> str | None:
    """Linux /proc start-time ticks distinguish a live PID from PID reuse."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2 :].split()
        return fields[19]
    except (OSError, IndexError):
        return None


def _record_process_identity(row: DownloadExecutionScopeModel, pid: int) -> bool:
    row.pid = pid
    row.pid_start_time = _pid_start_time(pid)
    row.host_boot_id = _host_boot_id()
    row.started_at = datetime.now(UTC)
    if row.pid_start_time is None:
        row.state = "unknown"
        row.reason = "process_identity_unavailable"
        return False
    row.state = "running"
    row.reason = "running"
    return True


def _classify_start_state(
    state: str, identity_matches: bool, populated: bool | None
) -> Literal["started", "not_started", "unknown"]:
    if state == "prepared" and populated is False:
        return "not_started"
    if state == "running" and identity_matches and populated is True:
        return "started"
    return "unknown"


def _host_boot_id() -> str | None:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def _cgroup_populated(cgroup: Path) -> bool | None:
    try:
        values = dict(line.split() for line in (cgroup / "cgroup.events").read_text().splitlines())
        return values.get("populated") == "1" if values.get("populated") in {"0", "1"} else None
    except (OSError, ValueError):
        return None


def _scope_binding_matches(row: DownloadExecutionScopeModel, admission: VerifiedAdmission) -> bool:
    request = admission.request
    return (
        row.task_id,
        row.owner_id,
        row.attempt_id,
        row.execution_id,
        row.execution_epoch,
        row.admission_ref,
        row.budget_ref,
        row.caller_id,
        row.environment_id,
        row.policy_revision,
    ) == (
        request.task_id,
        request.owner_id,
        request.attempt_id,
        request.execution_id,
        request.execution_epoch,
        request.admission_ref,
        request.budget_ref,
        admission.caller_id,
        admission.environment_id,
        admission.policy_digest,
    )


def _claim_execution_start(row: DownloadExecutionScopeModel) -> bool:
    """Transition a locked durable scope to starting at most once."""
    if row.state in {"starting", "running"}:
        return False
    if row.state != "prepared":
        raise SupervisorDeniedError("SUPERVISOR_START_STATE_UNKNOWN")
    row.state = "starting"
    row.egress_revoked = False
    return True


def _trusted_binary_matches(value: str, expected_sha256: str) -> bool:
    path = Path(value)
    try:
        metadata = path.lstat()
        if (
            not path.is_absolute()
            or path.resolve(strict=True) != path
            or not path.is_relative_to(Path("/usr"))
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
            or not os.access(path, os.X_OK)
        ):
            return False
        for parent in path.parents:
            if parent == Path("/"):
                break
            parent_metadata = parent.lstat()
            if (
                not stat.S_ISDIR(parent_metadata.st_mode)
                or parent_metadata.st_uid != 0
                or parent_metadata.st_mode & 0o022
            ):
                return False
        digest = hashlib.sha256()
        with path.open("rb") as binary:
            for chunk in iter(lambda: binary.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected_sha256
    except (OSError, RuntimeError):
        return False


def _is_world_traversable(path: Path) -> bool:
    for parent in (path, *path.parents):
        try:
            mode = parent.stat().st_mode
            if not stat.S_ISDIR(mode) or not mode & stat.S_IXOTH:
                return False
        except OSError:
            return False
    return True


def _bwrap_command(
    bwrap_path: str, command: Sequence[str], work: Path, user_dirs: dict[str, Path]
) -> list[str]:
    return [
        bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
        "--unshare-pid",
        "--unshare-net",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--dir",
        "/home",
        "--dir",
        "/home/cygnusx",
        "--bind",
        str(work),
        "/work",
        "--bind",
        str(user_dirs["home"]),
        "/home/cygnusx",
        "--bind",
        str(user_dirs["tmp"]),
        "/tmp",
        "--setenv",
        "HOME",
        "/home/cygnusx",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "XDG_CACHE_HOME",
        "/home/cygnusx/.cache",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--chdir",
        "/work",
        "--",
        *command,
    ]
