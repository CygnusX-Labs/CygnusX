"""Atomic persistence helpers for trusted execution receipts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionReceiptNonceModel,
)
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    SignedExecutionReceipt,
    verify_publishable_execution_receipt,
)


def execution_receipt_nonce_consumer(
    session: AsyncSession,
) -> Callable[[str, UUID, int], Awaitable[bool]]:
    """Adapt the current transaction to the signed-receipt verifier callback."""

    async def consume(supervisor_id: str, nonce: UUID, expires_at: int) -> bool:
        return await consume_execution_receipt_nonce(session, supervisor_id, nonce, expires_at)

    return consume


async def verify_publishable_execution_receipt_in_transaction(
    session: AsyncSession,
    receipt: SignedExecutionReceipt,
    *,
    supervisor_public_key: bytes,
    expected_supervisor_id: str,
    expected_task_id: UUID,
    expected_attempt_id: UUID,
    expected_execution_id: UUID,
    expected_scope_ref: UUID,
    expected_execution_epoch: int,
    expected_policy_revision: str,
    expected_environment_id: str,
    expected_binary_sha256: str,
    expected_artifact_manifest_sha256: str,
    now_epoch_seconds: int | None = None,
) -> ExecutionBoundaryObservation:
    """Verify and consume a receipt without committing the caller's transaction."""
    return await verify_publishable_execution_receipt(
        receipt,
        supervisor_public_key=supervisor_public_key,
        expected_supervisor_id=expected_supervisor_id,
        expected_task_id=expected_task_id,
        expected_attempt_id=expected_attempt_id,
        expected_execution_id=expected_execution_id,
        expected_scope_ref=expected_scope_ref,
        expected_execution_epoch=expected_execution_epoch,
        expected_policy_revision=expected_policy_revision,
        expected_environment_id=expected_environment_id,
        expected_binary_sha256=expected_binary_sha256,
        expected_artifact_manifest_sha256=expected_artifact_manifest_sha256,
        consume_nonce=execution_receipt_nonce_consumer(session),
        now_epoch_seconds=now_epoch_seconds,
    )


async def consume_execution_receipt_nonce(
    session: AsyncSession,
    supervisor_id: str,
    nonce: UUID,
    expires_at_epoch_seconds: int,
) -> bool:
    """Insert a nonce once; caller owns commit/rollback with publication work."""
    expires_at = datetime.fromtimestamp(expires_at_epoch_seconds, tz=UTC)
    if expires_at <= datetime.now(UTC):
        return False
    dialect_name = session.get_bind().dialect.name
    values = {
        "supervisor_id": supervisor_id,
        "nonce": nonce,
        "expires_at": expires_at,
    }
    conflict_target = ["supervisor_id", "nonce"]
    statement: Any
    if dialect_name == "postgresql":
        statement = (
            postgresql_insert(DownloadExecutionReceiptNonceModel)
            .values(**values)
            .on_conflict_do_nothing(index_elements=conflict_target)
        )
    elif dialect_name == "sqlite":
        statement = (
            sqlite_insert(DownloadExecutionReceiptNonceModel)
            .values(**values)
            .on_conflict_do_nothing(index_elements=conflict_target)
        )
    else:
        raise RuntimeError("DOWNLOAD_RECEIPT_NONCE_DIALECT_UNSUPPORTED")

    statement = statement.returning(DownloadExecutionReceiptNonceModel.id)
    result = await session.execute(statement)
    return result.scalar_one_or_none() is not None


async def purge_expired_execution_receipt_nonces(
    session: AsyncSession, *, now: datetime | None = None
) -> int:
    """Remove only expired replay keys; caller owns the maintenance transaction."""
    current_time = now or datetime.now(UTC)
    result = await session.execute(
        delete(DownloadExecutionReceiptNonceModel).where(
            DownloadExecutionReceiptNonceModel.expires_at <= current_time
        )
    )
    return max(0, int(getattr(result, "rowcount", 0) or 0))
