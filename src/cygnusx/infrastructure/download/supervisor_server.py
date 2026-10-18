"""Independent, closed-by-default Supervisor control service.

No Linux enforcement backend or P0-A authority is installed by this module.
The backend contract requires durable scope uniqueness and OS enforcement; test
doubles exercise orchestration only and must never be used as runtime evidence.
This module is deliberately absent from the platform API and Worker wiring.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID, uuid5

from pydantic import ValidationError

from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
    ExecutionPublicationContext,
    require_quiescent,
)


class SupervisorDeniedError(RuntimeError):
    """No execution permission or trustworthy boundary state is available."""


@dataclass(frozen=True)
class VerifiedAdmission:
    """Only an independently trusted P0-A verifier may construct this value.

    Verifier must requery durable approval, Task, reservation and scope fields and
    claim the exact attempt/epoch atomically. Worker JSON cannot be its source.
    Revalidation also covers revoke/expiry and budget on every lease renewal.
    """

    request: ExecutionBoundaryRequest
    caller_id: str
    environment_id: str
    policy_digest: str
    tool_digest: str
    project_id: UUID
    source_digest: str
    destination_policy_digest: str
    expires_at: int
    lease_deadline: int
    rx_limit_bytes: int
    disk_limit_bytes: int
    inode_limit: int


class AdmissionAuthority(Protocol):
    async def revalidate(
        self, request: ExecutionBoundaryRequest, caller_id: str, *, claim: bool
    ) -> VerifiedAdmission:
        """Requery original P0-A state; claim is durable CAS, never new budget."""
        ...


class EnforcedScopeBackend(Protocol):
    """Trusted OS adapter; no implementation/certification is implied here.

    Must durably map scope to exact request+caller, including across restarts.
    prepare is idempotent, creates default-deny egress, all-writable block/inode
    quota, immutable tool, cgroup/net/mount/user boundaries before exec. exec
    verifies tool digest and fixed argv/env/FDs; no Worker-controlled paths.
    Atomic RX credit is shared across all connections BEFORE Task admission.
    Unknown counters/stops cannot produce publication evidence or free budget.
    """

    async def recover_default_deny(self) -> None:
        """Block egress first, recover durable scopes, stop all unverified work."""
        ...

    async def prepare(self, scope: UUID, admission: VerifiedAdmission) -> None: ...

    async def exec_once(self, scope: UUID, admission: VerifiedAdmission) -> None: ...

    async def resolve(
        self, task: UUID, scope: UUID, caller_id: str
    ) -> ExecutionBoundaryRequest: ...

    async def observe(self, scope: UUID) -> ExecutionBoundaryObservation: ...

    async def renew(self, scope: UUID, admission: VerifiedAdmission) -> None:
        """Durably fence exact epoch; never extend past server-owned deadline."""
        ...

    async def revoke_egress(self, scope: UUID) -> None: ...

    async def kill_and_wait_empty(self, scope: UUID) -> None: ...

    async def expired_scopes(self) -> tuple[UUID, ...]: ...

    async def evidence(self, scope: UUID) -> ExecutionPublicationContext:
        """Sign actual stable OS observations; private key stays Supervisor-only."""
        ...


class SupervisorService:
    """Orchestrate trusted checks; no fallback to a generic process executor."""

    def __init__(
        self,
        supervisor_id: str,
        *,
        authority: AdmissionAuthority | None = None,
        backend: EnforcedScopeBackend | None = None,
    ) -> None:
        self.supervisor_id = supervisor_id
        self.authority = authority
        self.backend = backend
        self.ready = False

    def _dependencies(self) -> tuple[AdmissionAuthority, EnforcedScopeBackend]:
        if self.authority is None or self.backend is None:
            raise SupervisorDeniedError("SUPERVISOR_TRUSTED_BACKEND_UNAVAILABLE")
        return self.authority, self.backend

    async def recover(self) -> None:
        self.ready = False
        _, backend = self._dependencies()
        await backend.recover_default_deny()
        self.ready = True

    async def start(self, request: ExecutionBoundaryRequest, caller: str) -> UUID:
        authority, backend = self._dependencies()
        if not self.ready:
            raise SupervisorDeniedError("SUPERVISOR_RECOVERY_REQUIRED")
        admission = await authority.revalidate(request, caller, claim=True)
        self._validate(admission, request, caller)
        # Same Task/epoch always resolves to one scope; backend enforces durable
        # uniqueness and refuses a changed attempt/execution/request at this ID.
        scope = uuid5(request.task_id, f"download-epoch:{request.execution_epoch}")
        try:
            await backend.prepare(scope, admission)
            await backend.exec_once(scope, admission)
        except BaseException:
            # Cancellation is also uncertain start: revoke before tree cleanup.
            await asyncio.shield(self._stop_scope(scope, backend))
            raise
        return scope

    @staticmethod
    def _validate(
        admission: VerifiedAdmission, request: ExecutionBoundaryRequest, caller: str
    ) -> None:
        if (
            admission.request != request
            or admission.caller_id != caller
            or not admission.environment_id
            or admission.lease_deadline > admission.expires_at
            or admission.expires_at <= int(time.time())
            or admission.lease_deadline <= int(time.time())
            or any(
                re.fullmatch(r"[a-f0-9]{64}", digest) is None
                for digest in (
                    admission.policy_digest,
                    admission.tool_digest,
                    admission.source_digest,
                    admission.destination_policy_digest,
                )
            )
            or min(admission.rx_limit_bytes, admission.disk_limit_bytes, admission.inode_limit) <= 0
        ):
            raise SupervisorDeniedError("SUPERVISOR_ADMISSION_MISMATCH")

    async def act(
        self,
        task: UUID,
        scope: UUID,
        caller: str,
        action: Literal["observe", "lease", "stop", "evidence"],
    ) -> ExecutionBoundaryObservation | ExecutionPublicationContext | None:
        authority, backend = self._dependencies()
        request = await backend.resolve(task, scope, caller)
        if request.task_id != task:
            raise SupervisorDeniedError("SUPERVISOR_SCOPE_MISMATCH")
        if action == "stop":
            return await self._stop_scope(scope, backend)
        if action == "lease":
            try:
                if not self.ready:
                    raise SupervisorDeniedError("SUPERVISOR_RECOVERY_REQUIRED")
                admission = await authority.revalidate(request, caller, claim=False)
                self._validate(admission, request, caller)
                await backend.renew(scope, admission)
            except BaseException:
                await asyncio.shield(self._stop_scope(scope, backend))
                raise
            return None
        observation = await backend.observe(scope)
        if (
            observation.task_id,
            observation.scope_ref,
            observation.execution_id,
            observation.execution_epoch,
        ) != (task, scope, request.execution_id, request.execution_epoch):
            raise SupervisorDeniedError("SUPERVISOR_OBSERVATION_MISMATCH")
        if action == "evidence":
            require_quiescent(observation, task, scope)
            return await backend.evidence(scope)
        return observation

    @staticmethod
    async def _stop_scope(
        scope: UUID, backend: EnforcedScopeBackend
    ) -> ExecutionBoundaryObservation:
        await backend.revoke_egress(scope)
        await backend.kill_and_wait_empty(scope)
        observation = await backend.observe(scope)
        require_quiescent(observation, observation.task_id, scope)
        return observation

    async def watchdog_once(self) -> None:
        _, backend = self._dependencies()
        for scope in await backend.expired_scopes():
            await self._stop_scope(scope, backend)


class MutualTLSSupervisorServer:
    """Small independent HTTP/1 control listener with real TLS peer identity.

    One bounded request per TLS connection; no redirects, proxies, compression,
    chunking, caller headers, shell or implicit startup. Operations owns listener
    binding, certificate loading, watchdog process management and host approval.
    """

    def __init__(self, service: SupervisorService, certificate_callers: Mapping[str, str]) -> None:
        self.service = service
        self.certificate_callers = dict(certificate_callers)

    async def listen(self, host: str, port: int, tls: ssl.SSLContext) -> asyncio.Server:
        if tls.verify_mode != ssl.CERT_REQUIRED or tls.minimum_version < ssl.TLSVersion.TLSv1_2:
            raise SupervisorDeniedError("SUPERVISOR_MTLS_REQUIRED")
        await self.service.recover()
        return await asyncio.start_server(self.handle, host, port, ssl=tls, limit=16384)

    async def watchdog(self, interval_seconds: float = 1.0) -> None:
        if not 0 < interval_seconds <= 10:
            raise ValueError("SUPERVISOR_WATCHDOG_INTERVAL_INVALID")
        while True:
            await self.service.watchdog_once()
            await asyncio.sleep(interval_seconds)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status, payload = 503, b'{"error":"SUPERVISOR_UNAVAILABLE"}'
        try:
            tls = writer.get_extra_info("ssl_object")
            certificate = tls.getpeercert(binary_form=True) if tls else None
            caller = (
                self.certificate_callers.get(hashlib.sha256(certificate).hexdigest())
                if certificate
                else None
            )
            if not caller:
                raise SupervisorDeniedError("SUPERVISOR_CALLER_DENIED")
            async with asyncio.timeout(5):
                raw = await reader.readuntil(b"\r\n\r\n")
                method, path, version = raw.split(b"\r\n", 1)[0].decode("ascii").split(" ")
                headers: dict[str, str] = {}
                for line in raw.split(b"\r\n")[1:-2]:
                    key, value = line.decode("ascii").split(":", 1)
                    key = key.lower()
                    if key in headers:
                        raise ValueError("DUPLICATE_HEADER")
                    headers[key] = value.strip()
                length = int(headers.get("content-length", "0"))
                if (
                    version != "HTTP/1.1"
                    or not 0 <= length <= 8192
                    or "transfer-encoding" in headers
                    or headers.get("content-encoding", "identity") != "identity"
                ):
                    raise ValueError("REQUEST_REJECTED")
                body = await reader.readexactly(length)
                status, result = await self.dispatch(method, path, body, caller)
                payload = (
                    json.dumps(result, separators=(",", ":")).encode()
                    if result is not None
                    else b""
                )
        except SupervisorDeniedError:
            status, payload = 403, b'{"error":"SUPERVISOR_DENIED"}'
        except (
            ValueError,
            ValidationError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            status, payload = 400, b'{"error":"SUPERVISOR_REQUEST_INVALID"}'
        except (TimeoutError, RuntimeError, OSError):
            pass
        finally:
            writer.write(
                f"HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode()
                + payload
            )
            try:
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

    async def dispatch(
        self, method: str, path: str, body: bytes, caller: str
    ) -> tuple[int, dict[str, object] | None]:
        if method == "POST" and path == "/v1/executions":
            request = ExecutionBoundaryRequest.model_validate_json(body)
            scope = await self.service.start(request, caller)
            return 200, {
                "supervisor_id": self.service.supervisor_id,
                "task_id": str(request.task_id),
                "scope_ref": str(scope),
                "execution_id": str(request.execution_id),
                "execution_epoch": request.execution_epoch,
            }
        parts = path.split("/")
        if len(parts) not in {5, 6} or parts[:3] != ["", "v1", "executions"] or body:
            raise ValueError("ROUTE_REJECTED")
        task, scope = UUID(parts[3]), UUID(parts[4])
        action: Literal["observe", "lease", "stop", "evidence"]
        if method == "GET" and len(parts) == 5:
            action = "observe"
        elif method == "GET" and parts[-1] == "evidence":
            action = "evidence"
        elif method == "POST" and parts[-1] in {"lease", "stop"}:
            action = "lease" if parts[-1] == "lease" else "stop"
        else:
            raise ValueError("ROUTE_REJECTED")
        result = await self.service.act(task, scope, caller, action)
        return (204, None) if result is None else (200, result.model_dump(mode="json"))
