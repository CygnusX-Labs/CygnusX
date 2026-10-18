"""Durable replay protection for trusted download execution receipts."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, Uuid
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
