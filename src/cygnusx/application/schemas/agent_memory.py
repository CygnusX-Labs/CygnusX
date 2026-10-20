"""Agent 长期记忆 API DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from cygnusx.application.schemas.base import CygnusXBaseSchema

MemoryScope = Literal["profile", "project", "preference", "summary", "episode"]


class AgentMemoryDTO(CygnusXBaseSchema):
    id: str
    agent_id: str | None = None
    project_id: str | None = None
    scope: MemoryScope
    content: str
    keywords: list[str] = Field(default_factory=list)
    source_session: str | None = None
    confidence: float = 1.0
    use_count: int = 0
    last_used_at: datetime | None = None
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentMemoryClearResponse(CygnusXBaseSchema):
    cleared_count: int


class MemoryBlockDTO(CygnusXBaseSchema):
    project_id: str | None = None
    status: str = "active"
    superseded_by: int | None = None
    id: int
    agent_id: str
    block_name: str
    content: str
    char_limit: int
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryFactDTO(CygnusXBaseSchema):
    importance: int = Field(default=5, ge=1, le=10)
    recall_count: int = Field(default=0, ge=0)
    project_id: str | None = None
    id: int
    agent_id: str
    scope: MemoryScope
    content: str
    keywords: list[str] = Field(default_factory=list)
    source_session_id: str | None = None
    source_message_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    status: str = "active"
    superseded_by: int | None = None
    created_at: datetime | None = None
    last_recalled_at: datetime | None = None


class MemoryBlockUpdateRequest(CygnusXBaseSchema):
    content: str
    expected_version: int = Field(ge=1)


class MemoryOverviewDTO(CygnusXBaseSchema):
    focus_per_project_enabled: bool = False
    mode: Literal["legacy", "v2"]
    agent_ids: list[str] = Field(default_factory=list)
    blocks: list[MemoryBlockDTO] = Field(default_factory=list)
    facts: list[MemoryFactDTO] = Field(default_factory=list)
    legacy_memories: list[AgentMemoryDTO] = Field(default_factory=list)


class MemoryResidualHintDTO(CygnusXBaseSchema):
    kind: Literal["block", "fact", "episode"]
    id: int
    excerpt: str = Field(max_length=60)
    agent_id: str
    project_id: str | None = None
    block_name: str | None = None


class MemoryForgetResponse(CygnusXBaseSchema):
    memory_id: str
    forgotten: bool
    scan_status: Literal["disabled", "complete", "partial", "failed"] = "disabled"
    residual_hints: list[MemoryResidualHintDTO] = Field(default_factory=list)


class MemoryResidualActionRequest(CygnusXBaseSchema):
    source_id: int = Field(ge=1)
    target_id: int = Field(ge=1)
    kind: Literal["block", "fact", "episode"]
    action: Literal["open_editor", "archive"]


class MemoryConsolidationRollbackRequest(CygnusXBaseSchema):
    dry_run: bool = False
