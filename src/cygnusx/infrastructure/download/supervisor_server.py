"""Independent, closed-by-default Supervisor control service.

The database-backed P0-A authority and the Linux backend are explicit wiring
options. No backend is installed by default: test doubles exercise orchestration
only and must never be used as runtime evidence. Deployments must opt into an
operations-owned backend that proves durable scope uniqueness and OS enforcement;
the Worker retains only an explicit client seam and the platform gate stays closed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import ssl
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from pydantic import ValidationError

from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
    ExecutionPublicationContext,
    require_quiescent,
)

logger = logging.getLogger(__name__)
_REQUEST_READ_TIMEOUT_SECONDS = 5.0


class SupervisorDeniedError(RuntimeError):
    """No execution permission or trustworthy boundary state is available."""


@dataclass(frozen=True)
class AllowedHttpDestination:
    host: str
    port: int
    path: str


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
    http_urls: tuple[str, ...] = ()
    allowed_destinations: tuple[AllowedHttpDestination, ...] = ()


class AdmissionAuthority(Protocol):
    async def revalidate(
        self,
        request: ExecutionBoundaryRequest,
        caller_id: str,
        *,
        claim: bool,
        lease_nonce: UUID | None = None,
        supervisor_id: str | None = None,
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

    async def start_state(
        self, scope: UUID, admission: VerifiedAdmission
    ) -> Literal["started", "not_started", "unknown"]:
        """Return durable state; unknown must never be treated as a new start."""
        ...

    async def resolve(
        self, task: UUID, scope: UUID, caller_id: str
    ) -> ExecutionBoundaryRequest: ...

    async def observe(self, scope: UUID) -> ExecutionBoundaryObservation: ...

    async def renew(self, scope: UUID, admission: VerifiedAdmission) -> None:
        """Durably fence exact epoch; never extend past server-owned deadline."""
        ...

    async def revoke_egress(self, scope: UUID) -> None: ...

    async def kill_and_wait_empty(self, scope: UUID) -> None: ...

    async def expired_scopes(self) -> tuple[ExecutionBoundaryRequest, ...]:
        """Return persisted exact requests for expired scopes, never bare scope IDs."""
        ...

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
        scope = self._scope_for(request)
        try:
            await backend.prepare(scope, admission)
            start_state = await backend.start_state(scope, admission)
            if start_state == "unknown":
                raise SupervisorDeniedError("SUPERVISOR_SCOPE_STATE_UNKNOWN")
            if start_state == "not_started":
                await backend.exec_once(scope, admission)
            elif start_state != "started":
                raise SupervisorDeniedError("SUPERVISOR_SCOPE_STATE_INVALID")
        except BaseException:
            # Cancellation is also uncertain start: revoke before tree cleanup.
            await asyncio.shield(self._stop_scope(scope, backend, request))
            raise
        return scope

    @staticmethod
    def _scope_for(request: ExecutionBoundaryRequest) -> UUID:
        return uuid5(
            request.task_id,
            f"download-attempt:{request.attempt_id}:epoch:{request.execution_epoch}",
        )

    @staticmethod
    def _validate(
        admission: VerifiedAdmission, request: ExecutionBoundaryRequest, caller: str
    ) -> None:
        has_url_binding = bool(admission.http_urls or admission.allowed_destinations)
        url_binding_invalid = has_url_binding and not http_targets_authorized(admission)
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
            or url_binding_invalid
        ):
            raise SupervisorDeniedError("SUPERVISOR_ADMISSION_MISMATCH")

    async def act(
        self,
        task: UUID,
        scope: UUID,
        caller: str,
        action: Literal["observe", "lease", "stop", "evidence"],
        *,
        execution_epoch: int | None = None,
        lease_nonce: UUID | None = None,
    ) -> ExecutionBoundaryObservation | ExecutionPublicationContext | None:
        authority, backend = self._dependencies()
        request = await backend.resolve(task, scope, caller)
        if request.task_id != task:
            raise SupervisorDeniedError("SUPERVISOR_SCOPE_MISMATCH")
        if action == "stop":
            return await self._stop_scope(scope, backend, request)
        if action == "lease":
            try:
                if not self.ready:
                    raise SupervisorDeniedError("SUPERVISOR_RECOVERY_REQUIRED")
                if execution_epoch != request.execution_epoch or lease_nonce is None:
                    raise SupervisorDeniedError("SUPERVISOR_LEASE_BINDING_REJECTED")
                admission = await authority.revalidate(
                    request,
                    caller,
                    claim=False,
                    lease_nonce=lease_nonce,
                    supervisor_id=self.supervisor_id,
                )
                self._validate(admission, request, caller)
                await backend.renew(scope, admission)
            except BaseException:
                await asyncio.shield(self._stop_scope(scope, backend, request))
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
        scope: UUID,
        backend: EnforcedScopeBackend,
        request: ExecutionBoundaryRequest,
    ) -> ExecutionBoundaryObservation:
        stop_error: Exception | None = None
        try:
            await backend.revoke_egress(scope)
        except Exception as exc:
            stop_error = exc
        try:
            await backend.kill_and_wait_empty(scope)
        except Exception as exc:
            stop_error = stop_error or exc
        if stop_error is not None:
            raise SupervisorDeniedError("SUPERVISOR_STOP_INCOMPLETE") from stop_error
        observation = await backend.observe(scope)
        if scope != SupervisorService._scope_for(request) or (
            observation.task_id,
            observation.scope_ref,
            observation.execution_id,
            observation.execution_epoch,
        ) != (request.task_id, scope, request.execution_id, request.execution_epoch):
            raise SupervisorDeniedError("SUPERVISOR_STOP_OBSERVATION_MISMATCH")
        require_quiescent(observation, request.task_id, scope)
        return observation

    async def watchdog_once(self) -> None:
        _, backend = self._dependencies()
        for request in await backend.expired_scopes():
            scope = self._scope_for(request)
            try:
                await self._stop_scope(scope, backend, request)
            except Exception:
                logger.exception(
                    "Supervisor lease cleanup failed task_id=%s scope_id=%s epoch=%s",
                    request.task_id,
                    scope,
                    request.execution_epoch,
                )


def http_targets_authorized(admission: VerifiedAdmission) -> bool:
    if not admission.http_urls or not admission.allowed_destinations:
        return False
    destinations = {(item.host, item.port, item.path) for item in admission.allowed_destinations}
    try:
        return all(
            (parsed := urlsplit(url)).scheme == "http"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (parsed.hostname, parsed.port or 80, parsed.path) in destinations
            for url in admission.http_urls
        )
    except ValueError:
        return False


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
            try:
                await self.service.watchdog_once()
            except Exception:
                logger.exception("Supervisor lease sweep failed")
            await asyncio.sleep(interval_seconds)

    async def serve_forever(
        self,
        host: str,
        port: int,
        tls: ssl.SSLContext,
        *,
        watchdog_interval_seconds: float = 1.0,
    ) -> None:
        """Run the control listener and lease reaper in the Supervisor process."""
        if not 0 < watchdog_interval_seconds <= 10:
            raise ValueError("SUPERVISOR_WATCHDOG_INTERVAL_INVALID")
        listener = await self.listen(host, port, tls)
        watchdog = asyncio.create_task(self.watchdog(watchdog_interval_seconds))
        try:
            async with listener:
                await listener.serve_forever()
        finally:
            watchdog.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog

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
            async with asyncio.timeout(_REQUEST_READ_TIMEOUT_SECONDS):
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
                json.dumps(result, separators=(",", ":")).encode() if result is not None else b""
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
        if (
            len(parts) not in {5, 6}
            or parts[:3] != ["", "v1", "executions"]
            or (body and not (method == "POST" and len(parts) == 6 and parts[-1] == "lease"))
        ):
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
        lease_nonce: UUID | None = None
        execution_epoch: int | None = None
        if action == "lease":
            payload = json.loads(body)
            if (
                not isinstance(payload, dict)
                or set(payload) != {"execution_epoch", "lease_nonce"}
                or isinstance(payload["execution_epoch"], bool)
                or not isinstance(payload["execution_epoch"], int)
            ):
                raise ValueError("LEASE_REQUEST_INVALID")
            execution_epoch = payload["execution_epoch"]
            lease_nonce = UUID(payload["lease_nonce"])
        result = await self.service.act(
            task,
            scope,
            caller,
            action,
            execution_epoch=execution_epoch,
            lease_nonce=lease_nonce,
        )
        return (204, None) if result is None else (200, result.model_dump(mode="json"))
