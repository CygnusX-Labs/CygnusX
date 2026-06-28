"""Skill 域实体"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """技能实体 — 纯 prompt 注入型能力包"""

    id: UUID
    skill_id: str
    name: str
    description: str = ""
    prompt: str = ""
    tool_definition: dict[str, Any] | None = None
    icon: str = "\U0001F527"
    category: str = "general"
    is_active: bool = True
    is_builtin: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
