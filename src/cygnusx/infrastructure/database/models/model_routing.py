"""动态模型路由决策审计记录。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base


class ModelRoutingDecisionModel(Base):
    __tablename__ = "model_routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    agent_id: Mapped[str] = mapped_column(String(64))
    complexity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    explicit_model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    chosen_provider: Mapped[str] = mapped_column(String(64))
    cascade_providers: Mapped[list[Any]] = mapped_column(JSON, default=list)
    candidates_considered: Mapped[list[Any]] = mapped_column(JSON, default=list)
    decision_reason: Mapped[str] = mapped_column(String(64))
    cascade_events: Mapped[list[Any]] = mapped_column(JSON, default=list)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degrade_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
