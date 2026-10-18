"""Durable state for trusted download execution admission and receipts."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
        UniqueConstraint(
            "supervisor_id", "nonce", name="uq_download_execution_receipt_nonce"
        ),
        Index("ix_download_execution_receipt_nonces_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    supervisor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DownloadExecutionBudgetModel(Base, TimestampMixin):
    """Server-owned shared byte budget for one bounded execution admission."""

    __tablename__ = "download_execution_budgets"
    __table_args__ = (
        Index("ix_download_execution_budgets_owner_status", "owner_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    limit_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    admitted_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    policy_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DownloadExecutionAdmissionModel(Base, TimestampMixin):
    """Immutable request binding consumed by a trusted Supervisor."""

    __tablename__ = "download_execution_admissions"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_download_execution_admission_task"),
        UniqueConstraint("ingestion_id", name="uq_download_execution_admission_ingestion"),
        Index("ix_download_execution_admissions_expiry", "status", "expires_at"),
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
    allowed_destinations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="READY")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
