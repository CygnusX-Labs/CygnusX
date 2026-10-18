"""Versioned contracts for scientific report rendering and delivery packages."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    manifest_schema_version: Literal[
        "cygnusx.evidence_manifest.v1", "cygnusx.evidence_manifest.v1.1"
    ] = "cygnusx.evidence_manifest.v1"
    package_id: UUID
    task_id: UUID
    snapshot_id: UUID | None
    snapshot_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
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

    @model_validator(mode="after")
    def coherent_snapshot_and_missing_state(self) -> EvidenceManifest:
        if (
            self.manifest_schema_version == "cygnusx.evidence_manifest.v1"
            and self.snapshot_id is None
        ):
            raise ValueError("v1快照必填；缺快照交付必须使用v1.1")
        if (self.snapshot_id is None) != (self.snapshot_digest is None):
            raise ValueError("快照身份与摘要必须同时存在或同时缺失")
        absent = {item.logical_name for item in self.files if item.availability == "missing"}
        if absent != set(self.missing_files):
            raise ValueError("缺失文件声明不一致")
        if self.evidence_status == "complete" and (absent or self.snapshot_id is None):
            raise ValueError("缺少文件或快照时不能声明完整交付")
        return self
