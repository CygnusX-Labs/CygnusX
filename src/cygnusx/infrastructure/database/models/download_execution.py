"""Durable state for trusted download execution admission and receipts."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin


class DownloadExecutionReceiptNonceModel(Base, TimestampMixin):
    __tablename__ = "download_execution_receipt_nonces"
    __table_args__ = (
        UniqueConstraint("supervisor_id", "nonce", name="uq_download_execution_receipt_nonce"),
        Index("ix_download_execution_receipt_nonces_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    supervisor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DownloadExecutionLeaseNonceModel(Base, TimestampMixin):
    __tablename__ = "download_execution_lease_nonces"
    __table_args__ = (
        UniqueConstraint("supervisor_id", "nonce", name="uq_download_execution_lease_nonce"),
        Index("ix_download_execution_lease_nonces_expires_at", "expires_at"),
        CheckConstraint(
            "length(trim(supervisor_id)) > 0", name="ck_download_lease_nonce_supervisor"
        ),
        CheckConstraint("execution_epoch > 0", name="ck_download_lease_nonce_epoch"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    supervisor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    execution_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DownloadExecutionBudgetModel(Base, TimestampMixin):
    """Server-owned shared byte budget for one bounded execution admission."""

    __tablename__ = "download_execution_budgets"
    __table_args__ = (
        Index("ix_download_execution_budgets_owner_status", "owner_id", "status"),
        CheckConstraint(
            "limit_bytes > 0 AND reserved_bytes >= 0 AND reserved_bytes <= limit_bytes",
            name="ck_download_budget_reservation",
        ),
        CheckConstraint(
            "admitted_bytes IS NULL OR (admitted_bytes >= 0 AND admitted_bytes <= reserved_bytes)",
            name="ck_download_budget_measurement",
        ),
        CheckConstraint(
            "disk_block_limit_bytes > 0 AND disk_inodes_limit > 0", name="ck_download_budget_disk"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    admitted_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_block_limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_inodes_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    policy_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DownloadExecutionAdmissionModel(Base, TimestampMixin):
    """Immutable request binding consumed by a trusted Supervisor."""

    __tablename__ = "download_execution_admissions"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_download_execution_admission_task"),
        UniqueConstraint("ingestion_id", name="uq_download_execution_admission_ingestion"),
        Index("ix_download_execution_admissions_expiry", "status", "expires_at"),
        UniqueConstraint(
            "task_id", "attempt_id", "execution_epoch", name="uq_download_admission_attempt"
        ),
        UniqueConstraint(
            "task_id", "execution_id", name="uq_download_admission_execution_identity"
        ),
        CheckConstraint(
            "execution_epoch >= 0 AND reserved_bytes >= 0", name="ck_download_admission_epoch"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("download_execution_budgets.id", ondelete="RESTRICT"), nullable=False
    )
    ingestion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_ingestions.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    confirmation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    caller_id: Mapped[str] = mapped_column(String(128), nullable=False)
    caller_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    tool_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, default=uuid.uuid4)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    allowed_destinations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DownloadExecutionScopeModel(Base, TimestampMixin):
    """Durable Supervisor scope and process-start facts.

    This is deliberately separate from Task: a scope records what the
    Supervisor observed, including an uncertain start or cleanup, so a Worker
    retry cannot infer that a missing process is safe to start again.
    """

    __tablename__ = "download_execution_scopes"
    __table_args__ = (
        UniqueConstraint("task_id", "execution_id", name="uq_download_scope_execution"),
        UniqueConstraint("scope_ref", name="uq_download_scope_ref"),
        CheckConstraint("execution_epoch > 0", name="ck_download_scope_epoch"),
        CheckConstraint(
            "state IN ('prepared', 'starting', 'running', 'stopped', 'unknown')",
            name="ck_download_scope_state",
        ),
        Index("ix_download_execution_scopes_expiry", "state", "lease_deadline"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scope_ref: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    admission_ref: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    budget_ref: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    execution_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    caller_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="prepared")
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returncode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pid_start_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    host_boot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    egress_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cleanup_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
