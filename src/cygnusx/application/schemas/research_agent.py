"""科研寻宝鼠 Phase 1 的平台边界 DTO。

这些 DTO 只描述发现和证据，不代表 Dataset、FileRecord 或 Task。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DiscoveryProposal(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    proposal_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    accession: str | None = Field(default=None, max_length=128)
    title: str = Field(default="", max_length=1000)
    summary: str = Field(default="", max_length=5000)
    organism: str | None = Field(default=None, max_length=256)
    assay_type: str | None = Field(default=None, max_length=256)
    sample_count: int | None = Field(default=None, ge=0)
    metadata_status: Literal["unverified", "agent_asserted", "platform_verified"] = "unverified"
    source_links: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    retrieved_at: datetime | None = None
    project_id: str | None = None
    conversation_id: str = Field(min_length=1, max_length=64)
    provenance: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[Literal["inspect_metadata", "refine_search", "review_evidence"]] = Field(
        default=["inspect_metadata", "refine_search"]
    )


class ResearchAgentSessionCreate(BaseModel):
    project_id: UUID | None = None
    title: str = Field(default="科研发现", max_length=200)
    model_id: UUID | None = None


class ResearchAgentMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    model_id: UUID | None = None
    lang: Literal["zh", "en"] = "zh"
    request_id: UUID = Field(default_factory=uuid4)


class ResearchAgentCapabilities(BaseModel):
    native_ui_enabled: bool
    enabled: bool = False
    read_discovery: bool = False
    read_sessions: bool = False
    prepare_import: bool = False
    prepare_analysis: bool = False
    project_required_for_prepare: Literal[True] = True
    write_execution: Literal[False] = False
    reason_code: str | None = None
    cancellation_mode: Literal["browser_abort_only"] = "browser_abort_only"
    read_only: bool = True
    write_tools_enabled: Literal[False] = False
    supported_events: list[str] = Field(
        default_factory=lambda: ["delta", "tool", "cards", "polariseq", "grounding", "end", "error", "cancel"]
    )


class ResearchAgentSessionView(BaseModel):
    session: Any
    messages: list[Any] = Field(default_factory=list)



class ResearchSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["archived"] | None = None


class ResearchLiteratureRequest(BaseModel):
    kind: Literal["geo_series", "geo_sample", "go_term", "pubmed"]
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_:.-]+$")
