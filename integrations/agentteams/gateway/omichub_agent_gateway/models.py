"""Public Gateway contracts; raw OmicHub sessions and tool traces never cross this boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCIENTIFIC_INTERPRETATION_SCHEMA_VERSION = "1.0"
ConsultationStatus = Literal["completed", "manual_review", "rejected"]


class ConsultationRequest(BaseModel):
    """Manager request limited to logical references and an approved read-only capability."""

    case_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=8_000)
    capability: Literal["interpretation", "planning_advice", "result_interpretation", "qc_advice"]
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    requested_tools: list[str] = Field(default_factory=list, max_length=20)


class ConsultationError(BaseModel):
    code: str
    message: str
    retry_after_seconds: int | None = None


class ScientificInterpretationResponse(BaseModel):
    """Fixed output envelope exposed to AgentTeams Manager."""

    schema_version: str = SCIENTIFIC_INTERPRETATION_SCHEMA_VERSION
    status: ConsultationStatus
    conclusion: str
    recommendations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    agent_id: str
    schema_ver: str = SCIENTIFIC_INTERPRETATION_SCHEMA_VERSION
    duration_ms: int = Field(ge=0)
    token_usage: int = Field(ge=0)
    error: ConsultationError | None = None


class UpstreamConsultationResponse(BaseModel):
    """The minimal sanctioned response expected from OmicHub's future controlled endpoint."""

    conclusion: str = Field(min_length=1, max_length=20_000)
    recommendations: list[str] = Field(default_factory=list, max_length=50)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=50)
    token_usage: int = Field(ge=0)
