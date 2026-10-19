"""Database-backed P0-A authority for the independent download Supervisor.

This verifies and claims durable admission facts only. It does not implement OS
isolation, provide a runtime service configuration, or authorize a transport gate.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.repositories import (
    download_execution_admission as admission_repo,
)
from cygnusx.infrastructure.database.repositories import download_execution_receipt as receipt_repo
from cygnusx.infrastructure.database.session import get_session_factory
from cygnusx.infrastructure.download.supervisor_server import (
    AllowedHttpDestination,
    SupervisorDeniedError,
    VerifiedAdmission,
)
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryRequest,
    deterministic_execution_id,
)

SessionFactory = Callable[[], Any]


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class DatabaseAdmissionAuthority:
    """Revalidate a Task's durable Admission and claim its exact execution epoch.

    The certificate-to-caller mapping is owned by the Supervisor server. The caller
    string passed here is therefore authenticated transport identity, never request
    JSON. Claim and admission resolution share one SQL transaction.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory | async_sessionmaker[AsyncSession] | None = None,
        lease_seconds: int = 15,
    ) -> None:
        if isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 60:
            raise ValueError("SUPERVISOR_LEASE_SECONDS_INVALID")
        self._session_factory = session_factory
        self._lease_seconds = lease_seconds

    async def revalidate(
        self,
        request: ExecutionBoundaryRequest,
        caller_id: str,
        *,
        claim: bool,
        lease_nonce: UUID | None = None,
        supervisor_id: str | None = None,
    ) -> VerifiedAdmission:
        factory = self._session_factory or get_session_factory()
        try:
            async with factory() as session:
                result = await self._revalidate_in_session(
                    session,
                    request,
                    caller_id,
                    claim=claim,
                    lease_nonce=lease_nonce,
                    supervisor_id=supervisor_id,
                )
                await session.commit()
                return result
        except admission_repo.DownloadExecutionAdmissionError as exc:
            raise SupervisorDeniedError(str(exc)) from None

    async def _revalidate_in_session(
        self,
        session: AsyncSession,
        request: ExecutionBoundaryRequest,
        caller_id: str,
        *,
        claim: bool,
        lease_nonce: UUID | None,
        supervisor_id: str | None,
    ) -> VerifiedAdmission:
        expected_execution_id = deterministic_execution_id(
            request.task_id, request.attempt_id, request.execution_epoch
        )
        if request.execution_id != expected_execution_id:
            raise SupervisorDeniedError("SUPERVISOR_EXECUTION_ID_REJECTED")
        task = await session.get(TaskModel, request.task_id)
        if task is None or task.user_id != request.owner_id:
            raise SupervisorDeniedError("SUPERVISOR_TASK_BINDING_REJECTED")
        expected_binding = {
            "version": 1,
            "admission_ref": str(request.admission_ref),
            "budget_ref": str(request.budget_ref),
        }
        if (task.parameters or {}).get("_download_execution_binding") != expected_binding:
            raise SupervisorDeniedError("SUPERVISOR_TASK_BINDING_REJECTED")

        admission, budget = await admission_repo.resolve_execution_admission(
            session,
            request.admission_ref,
            request.budget_ref,
            task_id=request.task_id,
            owner_id=request.owner_id,
            caller_id=caller_id,
            allow_consumed=None if claim else True,
        )
        already_claimed = claim and admission.status == "CONSUMED"
        expected_epoch = admission.execution_epoch if already_claimed else (
            admission.execution_epoch + 1 if claim else admission.execution_epoch
        )
        if (
            admission.attempt_id != request.attempt_id
            or request.execution_epoch != expected_epoch
            or request.protocol != admission.protocol
            or ((already_claimed or not claim) and admission.execution_id != request.execution_id)
        ):
            raise SupervisorDeniedError("SUPERVISOR_ATTEMPT_BINDING_REJECTED")

        profile = admission_repo.get_execution_admission_profile(admission.environment_id)

        if claim and not already_claimed:
            await admission_repo.consume_execution_admission(
                session,
                admission.id,
                task_id=task.id,
                owner_id=task.user_id,
                request_digest=admission.request_digest,
                caller_id=caller_id,
                budget_id=budget.id,
                attempt_id=request.attempt_id,
                expected_epoch=admission.execution_epoch,
                tool_digest=admission.tool_digest,
                environment_id=admission.environment_id,
                execution_id=request.execution_id,
            )
        elif lease_nonce is not None:
            if supervisor_id is None or request.execution_epoch != admission.execution_epoch:
                raise SupervisorDeniedError("SUPERVISOR_LEASE_BINDING_REJECTED")
            consumed = await receipt_repo.consume_execution_lease_nonce(
                session,
                supervisor_id,
                lease_nonce,
                request.task_id,
                request.execution_epoch,
                int(time.time()) + self._lease_seconds,
            )
            if not consumed:
                raise SupervisorDeniedError("SUPERVISOR_LEASE_NONCE_REPLAY")

        now = int(time.time())
        expiry = admission.expires_at
        expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
        expires_at = int(expiry.timestamp())
        lease_deadline = min(expires_at, now + self._lease_seconds)
        if lease_deadline <= now:
            raise SupervisorDeniedError("SUPERVISOR_ADMISSION_EXPIRED")
        policy_fields = {
            key: profile[key]
            for key in (
                "allowed_destinations",
                "caller_id",
                "caller_kind",
                "disk_block_limit_bytes",
                "disk_inodes_limit",
                "environment_id",
                "policy_revision",
                "tool_digest",
            )
        }
        raw_urls = (task.parameters or {}).get("links")
        raw_destinations = profile["allowed_destinations"]
        if (
            not isinstance(raw_urls, list)
            or not raw_urls
            or any(not isinstance(url, str) for url in raw_urls)
            or not isinstance(raw_destinations, list)
        ):
            raise SupervisorDeniedError("SUPERVISOR_HTTP_TARGET_BINDING_INVALID")
        return VerifiedAdmission(
            request=request,
            caller_id=caller_id,
            environment_id=admission.environment_id,
            policy_digest=_canonical_digest(policy_fields),
            tool_digest=admission.tool_digest,
            project_id=admission.project_id,
            source_digest=admission.source_digest,
            destination_policy_digest=_canonical_digest(admission.allowed_destinations),
            expires_at=expires_at,
            lease_deadline=lease_deadline,
            rx_limit_bytes=budget.limit_bytes,
            disk_limit_bytes=budget.disk_block_limit_bytes,
            inode_limit=budget.disk_inodes_limit,
            http_urls=tuple(raw_urls),
            allowed_destinations=tuple(
                AllowedHttpDestination(
                    host=item["host"], port=item["port"], path=item["path"]
                )
                for item in raw_destinations
            ),
        )
