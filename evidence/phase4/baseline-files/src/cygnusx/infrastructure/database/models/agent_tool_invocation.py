"""Minimal durable correlation; business Task remains the execution authority."""

import uuid
from typing import Any

from sqlalchemy import JSON, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin


class AgentToolInvocationModel(Base, TimestampMixin):
    __tablename__ = "agent_tool_invocations"
    __table_args__ = (
        Index("ix_agent_tool_invocations_owner_session", "owner_id", "conversation_id"),
        Index("ix_agent_tool_invocations_owner_project", "owner_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # Deliberately retain tombstone references on resource deletion. Access always
    # rechecks the actual user/project/session; a deleted project never becomes global.
    project_id: Mapped[str | None] = mapped_column(String(64))
    conversation_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    capability_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_id: Mapped[str | None] = mapped_column(String(128))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    # Only structured public preview, never confirmation credentials or private input.
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
