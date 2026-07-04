"""Agent 模板 DTO — 多智能体协作平台资产"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentTemplateDTO(BaseModel):
    """Agent 模板（前台集市 + 后台编排共用）"""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    name: str
    description: str = ""
    avatar: str = "\U0001F916"
    color: str = "#4f8ef7"
    category: str = "general"
    model_id: UUID | None = None
    model_name: str = ""
    model_engine: str = ""
    system_prompt: str = ""
    welcome_message: str = ""
    mcp_ids: list[Any] = Field(default_factory=list)
    skill_ids: list[Any] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    temperature: float = 0.7
    max_tokens: int = 4096
    is_builtin: bool = False
    is_active: bool = True
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateAgentRequest(BaseModel):
    agent_id: str = ""
    name: str
    description: str = ""
    avatar: str = "\U0001F916"
    color: str = "#4f8ef7"
    category: str = "general"
    model_id: UUID | None = None
    system_prompt: str = ""
    welcome_message: str = ""
    mcp_ids: list[Any] = Field(default_factory=list)
    skill_ids: list[Any] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    temperature: float = 0.7
    max_tokens: int = 4096
    is_active: bool = True


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    avatar: str | None = None
    color: str | None = None
    category: str | None = None
    model_id: UUID | None = None
    system_prompt: str | None = None
    welcome_message: str | None = None
    mcp_ids: list[Any] | None = None
    skill_ids: list[Any] | None = None
    features: dict[str, Any] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None
    is_default: bool | None = None
