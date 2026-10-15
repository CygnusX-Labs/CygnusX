"""Versioned contracts for scientific report rendering and delivery packages."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BioReportRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    report_snapshot_id: UUID
    report_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_report_source: str
    report_config: str
    input_artifacts: tuple[str, ...] = ()
    output_format: Literal["html", "pdf"]
    renderer_version: str
    template_version: str
    visibility_scope: Literal["owner"] = "owner"


class DeliveryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_name: str
    file_type: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_object: str
    original_artifact_id: UUID | None = None
    generation: Literal["reused", "rendered", "generated"]
    availability: Literal["available", "missing"]
    integrity: Literal["verified", "not_applicable", "failed"]


class EvidenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_schema_version: Literal["cygnusx.evidence_manifest.v1"] = (
        "cygnusx.evidence_manifest.v1"
    )
    package_id: UUID
    task_id: UUID
    snapshot_id: UUID
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_version: str
    source_artifacts: tuple[str, ...] = ()
    renderer_version: str
    template_version: str
    files: tuple[DeliveryFile, ...]
    checksum_algorithm: Literal["sha256"] = "sha256"
    evidence_status: Literal["complete", "partial"]
    missing_files: tuple[str, ...] = ()
    validation_status: Literal["validated", "invalid"]
    generated_at: datetime

