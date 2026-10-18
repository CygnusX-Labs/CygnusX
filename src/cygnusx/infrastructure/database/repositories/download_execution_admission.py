"""Transactional creation and consumption of trusted download admissions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
    DownloadExecutionBudgetModel,
)


def _utc(value: datetime) -> datetime:
    """Normalize PostgreSQL/SQLite timestamp results before comparison."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class DownloadExecutionAdmissionError(RuntimeError):
    """A caller cannot use the requested admission or budget."""


async def issue_processed_http_admission(
    session: AsyncSession,
    *,
    ingestion_id: UUID,
    task_id: UUID,
    owner_id: UUID,
    project_id: UUID,
    confirmation_id: str,
    request_digest: str,
    limit_bytes: int,
    policy_revision: str,
    environment_id: str,
    caller_id: str,
    allowed_destinations: list[dict[str, Any]],
    expires_at: datetime,
) -> DownloadExecutionAdmissionModel:
    """Create a server-issued admission for exactly one processed HTTP Task.

    The caller must already have validated the DatasetIngestion approval and created
    the Task in the same transaction. This function never accepts a Worker-supplied
    admission or budget ID.
    """
    if limit_bytes <= 0 or expires_at <= datetime.now(UTC):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_INVALID_BUDGET")
    if not confirmation_id or not request_digest or not policy_revision:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_BINDING_MISSING")
    if not allowed_destinations:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_DESTINATION_MISSING")

    budget = DownloadExecutionBudgetModel(
        id=uuid4(),
        owner_id=owner_id,
        project_id=project_id,
        limit_bytes=limit_bytes,
        reserved_bytes=0,
        admitted_bytes=0,
        status="ACTIVE",
        policy_revision=policy_revision,
        expires_at=expires_at,
    )
    admission = DownloadExecutionAdmissionModel(
        id=uuid4(),
        budget_id=budget.id,
        ingestion_id=ingestion_id,
        task_id=task_id,
        owner_id=owner_id,
        project_id=project_id,
        confirmation_id=confirmation_id,
        request_digest=request_digest,
        source="direct_link",
        protocol="http",
        policy_revision=policy_revision,
        environment_id=environment_id,
        caller_id=caller_id,
        allowed_destinations=allowed_destinations,
        status="READY",
        expires_at=expires_at,
        execution_epoch=0,
        revoked=False,
    )
    session.add(budget)
    session.add(admission)
    await session.flush()
    return admission


async def consume_execution_admission(
    session: AsyncSession,
    admission_id: UUID,
    *,
    task_id: UUID,
    owner_id: UUID,
    request_digest: str,
    caller_id: str,
    now: datetime | None = None,
    budget_id: UUID | None = None,
) -> DownloadExecutionAdmissionModel:
    """Atomically consume a ready admission and advance its execution epoch."""
    current = now or datetime.now(UTC)
    result = await session.execute(
        select(DownloadExecutionAdmissionModel)
        .where(DownloadExecutionAdmissionModel.id == admission_id)
        .with_for_update()
    )
    admission = result.scalar_one_or_none()
    if admission is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_NOT_FOUND")
    if (
        admission.status != "READY"
        or admission.revoked
        or _utc(admission.expires_at) <= current
        or admission.task_id != task_id
        or admission.owner_id != owner_id
        or admission.request_digest != request_digest
        or admission.caller_id != caller_id
        or (budget_id is not None and admission.budget_id != budget_id)
    ):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    admission.status = "CONSUMED"
    admission.consumed_at = current
    admission.execution_epoch += 1
    await session.flush()
    return admission


async def resolve_execution_admission(
    session: AsyncSession,
    admission_id: UUID,
    budget_id: UUID,
    *,
    task_id: UUID,
    owner_id: UUID,
    caller_id: str,
    now: datetime | None = None,
) -> tuple[DownloadExecutionAdmissionModel, DownloadExecutionBudgetModel]:
    """Resolve both server-issued references before a Supervisor may start.

    The request's UUIDs are lookup keys only. Ownership, Task binding, expiry,
    protocol, status, caller and budget linkage are checked from database state.
    """
    current = now or datetime.now(UTC)
    result = await session.execute(
        select(DownloadExecutionAdmissionModel, DownloadExecutionBudgetModel)
        .join(
            DownloadExecutionBudgetModel,
            DownloadExecutionBudgetModel.id == DownloadExecutionAdmissionModel.budget_id,
        )
        .where(
            DownloadExecutionAdmissionModel.id == admission_id,
            DownloadExecutionBudgetModel.id == budget_id,
        )
        .with_for_update()
    )
    pair = result.one_or_none()
    if pair is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    admission, budget = pair
    if (
        admission.status != "READY"
        or admission.revoked
        or _utc(admission.expires_at) <= current
        or admission.task_id != task_id
        or admission.owner_id != owner_id
        or admission.caller_id != caller_id
        or admission.protocol != "http"
        or admission.source != "direct_link"
        or budget.status != "ACTIVE"
        or _utc(budget.expires_at) <= current
        or budget.owner_id != owner_id
        or budget.policy_revision != admission.policy_revision
    ):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    return admission, budget


async def reserve_execution_budget(
    session: AsyncSession,
    budget_id: UUID,
    *,
    amount: int,
    now: datetime | None = None,
) -> DownloadExecutionBudgetModel:
    """Reserve bytes with one conditional SQL update; never reserve after expiry."""
    if amount <= 0:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_AMOUNT_INVALID")
    current = now or datetime.now(UTC)
    result = await session.execute(
        update(DownloadExecutionBudgetModel)
        .where(
            DownloadExecutionBudgetModel.id == budget_id,
            DownloadExecutionBudgetModel.status == "ACTIVE",
            DownloadExecutionBudgetModel.expires_at > current,
            DownloadExecutionBudgetModel.reserved_bytes + amount
            <= DownloadExecutionBudgetModel.limit_bytes,
        )
        .values(reserved_bytes=DownloadExecutionBudgetModel.reserved_bytes + amount)
        .returning(DownloadExecutionBudgetModel.id)
    )
    if result.scalar_one_or_none() is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_EXCEEDED")
    budget = (
        await session.execute(
            select(DownloadExecutionBudgetModel).where(
                DownloadExecutionBudgetModel.id == budget_id
            )
        )
    ).scalar_one()
    return budget


async def revoke_execution_admission(session: AsyncSession, admission_id: UUID) -> None:
    """Revoke a not-yet-consumed admission; caller owns commit/rollback."""
    result = await session.execute(
        select(DownloadExecutionAdmissionModel)
        .where(DownloadExecutionAdmissionModel.id == admission_id)
        .with_for_update()
    )
    admission = result.scalar_one_or_none()
    if admission is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_NOT_FOUND")
    if admission.status == "CONSUMED":
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_ALREADY_CONSUMED")
    admission.status = "REVOKED"
    admission.revoked = True
    await session.flush()
