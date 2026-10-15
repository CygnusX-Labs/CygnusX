"""Immutable capture of a real Task's manifest and registered artifact observations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin


class ResultObservationModel(Base, TimestampMixin):
    __tablename__ = "result_manifest_observations"
    __table_args__ = (
        UniqueConstraint("task_id", "evidence_digest", name="uq_result_observation_facts"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    analysis_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_analysis_links.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


@event.listens_for(ResultObservationModel, "before_delete")
@event.listens_for(ResultObservationModel, "before_update")
def reject_result_observation_update(*args: object) -> None:
    raise ValueError("Result observations are immutable; append a new capture")
