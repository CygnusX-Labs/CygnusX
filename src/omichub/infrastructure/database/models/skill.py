"""Skill ORM 模型 — 纯 prompt 注入型技能"""

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from omichub.infrastructure.database.base import Base, TimestampMixin


class SkillModel(Base, TimestampMixin):
    """技能表"""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_definition: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="\U0001F527")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
