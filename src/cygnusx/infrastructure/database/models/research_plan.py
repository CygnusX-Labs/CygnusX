"""Versioned intent only. Task, Run and tool approvals retain their own authorities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin


class ResearchPlanModel(Base, TimestampMixin):
    __tablename__ = "research_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "request_key", name="uq_research_plan_request"),
        UniqueConstraint("series_id", "version", name="uq_research_plan_version"),
        Index("ix_research_plans_owner_project", "user_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str] = mapped_column(String(80), nullable=False)
    draft: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    gaps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("research_plans.id", ondelete="RESTRICT")
    )


def immutable_plan_document(mapper: Any, connection: Any, target: ResearchPlanModel) -> None:
    from sqlalchemy import inspect

    state = inspect(target)
    immutable = ("user_id", "project_id", "series_id", "version", "request_key", "draft", "digest")
    if any(state.attrs[field].history.has_changes() for field in immutable):
        raise ValueError("Research intent is immutable; create a new version")


event.listen(ResearchPlanModel, "before_update", immutable_plan_document)
