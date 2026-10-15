"""Owner/project research lineage; assertions are server observations, never Agent inputs."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Integrity = Literal["VERIFIED", "PARTIAL", "UNKNOWN", "MISSING", "FAILED", "NOT_APPLICABLE"]


class ResearchDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ResearchArtifact(ResearchDTO):
    file_record_id: UUID | None = None
    logical_name: str
    category: str = "other"
    size: int | None = None
    sha256: str | None = None
    integrity: Integrity = "UNKNOWN"
    declared_sha256: str | None = None
    file_url: str | None = None


class ResearchReportLink(ResearchDTO):
    report_id: UUID
    kind: Literal["scientific", "reproducibility", "delivery"]
    state: str
    integrity: Integrity = "UNKNOWN"
    result_observation_id: UUID | None = None
    report_url: str


class ResearchProvenance(ResearchDTO):
    schema_version: Literal["cygnusx.research_provenance.v1"] = "cygnusx.research_provenance.v1"
    owner_id: UUID
    project_id: UUID | None = None
    dataset_id: UUID | None = None
    dataset_version_id: UUID | None = None
    analysis_link_id: UUID | None = None
    task_id: UUID
    run_id: UUID | None = None
    handoff_hash: str | None = None
    flow: dict[str, Any] = Field(default_factory=dict)
    parameters_sha256: str | None = None
    analysis_parameters: dict[str, Any] = Field(default_factory=dict)
    source: list[dict[str, Any]] = Field(default_factory=list)
    samples: list[dict[str, Any]] = Field(default_factory=list)
    inputs: list[ResearchArtifact] = Field(default_factory=list)
    compute_state: str = "UNKNOWN"
    input_integrity: Integrity = "UNKNOWN"
    result_integrity: Integrity = "UNKNOWN"
    evidence_state: Integrity = "UNKNOWN"
    delivery_state: Literal["READY", "PARTIAL", "BLOCKED", "UNKNOWN"] = "UNKNOWN"
    result_observation_id: UUID | None = None
    manifest_sha256: str | None = None
    artifacts: list[ResearchArtifact] = Field(default_factory=list)
    reports: list[ResearchReportLink] = Field(default_factory=list)
    report_jobs: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    observation_scope: Literal["capture_time_bytes_not_execution_attestation"] = (
        "capture_time_bytes_not_execution_attestation"
    )
