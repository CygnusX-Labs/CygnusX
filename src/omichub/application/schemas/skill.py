"""Skill Pydantic DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SkillDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill_id: str
    name: str
    description: str = ""
    prompt: str = ""
    tool_definition: dict[str, Any] | None = None
    icon: str = "\U0001f527"
    category: str = "general"
    is_active: bool = True
    is_builtin: bool = False
    created_at: datetime
    updated_at: datetime


class CreateSkillDTO(BaseModel):
    skill_id: str
    name: str
    description: str = ""
    prompt: str = ""
    tool_definition: dict[str, Any] | None = None
    icon: str = "\U0001f527"
    category: str = "general"
    is_active: bool = True


class UpdateSkillDTO(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    tool_definition: dict[str, Any] | None = None
    icon: str | None = None
    category: str | None = None
    is_active: bool | None = None
