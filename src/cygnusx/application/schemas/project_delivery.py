"""Frozen project export contracts. Identity references never grant access."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cygnusx.application.schemas.execution_evidence import canonical_digest

SHA = r"^[0-9a-f]{64}$"
PackageKind = Literal["evidence", "results", "reproduction_materials"]
Association = Literal[
    "VERIFIED_ASSOCIATION", "PARTIAL_ASSOCIATION", "NOT_RECORDED", "UNAVAILABLE", "ACCESS_DENIED"
]


class DeliveryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ExportSelection(DeliveryDTO):
    kind: PackageKind = "evidence"
    # Empty means all trusted tasks within the bounded inventory, never all owner tasks.
    task_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    report_ids: tuple[UUID, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def unique_ids(self) -> ExportSelection:
        if len(set(self.task_ids)) != len(self.task_ids) or len(set(self.report_ids)) != len(
            self.report_ids
        ):
            raise ValueError("Duplicate selection")
        return self


class DeliveryReference(DeliveryDTO):
    kind: Literal[
        "project",
        "dataset_version",
        "file_record",
        "task",
        "run",
        "result_observation",
        "report",
        "report_snapshot",
        "evidence_manifest",
        "historical_association",
    ]
    id: UUID | None = None
    task_id: UUID | None = None
    status: Association = "VERIFIED_ASSOCIATION"
    disposition: Literal["reference_only", "missing", "unverified", "excluded"] = "reference_only"
    reason: str | None = None
    digest: str | None = Field(default=None, pattern=SHA)
    version: int | None = Field(default=None, ge=1)
    snapshot_id: UUID | None = None
    result_observation_id: UUID | None = None
    parent_id: UUID | None = None
    dataset_version_id: UUID | None = None
    analysis_link_id: UUID | None = None


class DeliveryFile(DeliveryDTO):
    path: str = Field(pattern=r"^[A-Za-z0-9_./-]{1,240}$")
    source_kind: Literal[
        "report_file", "file_record", "report_snapshot", "instructions", "verifier"
    ]
    source_id: UUID | None = None
    task_id: UUID | None = None
    size: int = Field(ge=0)
    sha256: str = Field(pattern=SHA)

    @model_validator(mode="after")
    def safe_path(self) -> DeliveryFile:
        if self.path.startswith("/") or any(p in {"", ".", ".."} for p in self.path.split("/")):
            raise ValueError("Unsafe archive member")
        return self


class ProjectDeliveryManifest(DeliveryDTO):
    schema_version: Literal["cygnusx.project_delivery.v1"] = "cygnusx.project_delivery.v1"
    digest_policy: Literal["sorted_utf8_json.v1"] = "sorted_utf8_json.v1"
    project_id: UUID
    owner_id: UUID
    selection: ExportSelection
    files: tuple[DeliveryFile, ...] = Field(default=(), max_length=1000)
    references: tuple[DeliveryReference, ...] = Field(default=(), max_length=4000)
    gaps: tuple[str, ...] = ()
    evidence_status: Literal["partial", "complete"] = "partial"
    reproduction_status: Literal["NOT_RUN"] = "NOT_RUN"
    association_scope: Literal["explicit_dataset_links_only"] = "explicit_dataset_links_only"
    redaction_policy: Literal["project_delivery_allowlist.v1"] = "project_delivery_allowlist.v1"

    @model_validator(mode="after")
    def unique_files(self) -> ProjectDeliveryManifest:
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("Duplicate archive member")
        if self.gaps and self.evidence_status == "complete":
            raise ValueError("Missing evidence cannot be complete")
        return self

    def content_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ExportSelectionV2(ExportSelection):
    source_manifest_job_id: UUID
    project_report_job_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_reports(self) -> ExportSelectionV2:
        if len(set(self.project_report_job_ids)) != len(self.project_report_job_ids):
            raise ValueError("Duplicate project report selection")
        return self


class ProjectReportArtifact(DeliveryDTO):
    project_report_job_id: UUID
    source_digest: str = Field(pattern=SHA)
    report_file_id: UUID
    file_record_id: UUID
    format: Literal["html", "pdf"]
    sha256: str = Field(pattern=SHA)
    size: int = Field(gt=0)


class ProjectDeliveryManifestV2(DeliveryDTO):
    schema_version: Literal["cygnusx.project_delivery.v2"] = "cygnusx.project_delivery.v2"
    digest_policy: Literal["sorted_utf8_json.v1"] = "sorted_utf8_json.v1"
    owner_id: UUID
    project_id: UUID
    selection: ExportSelectionV2
    source_manifest_digest: str = Field(pattern=SHA)
    report_artifacts: tuple[ProjectReportArtifact, ...] = Field(min_length=1, max_length=200)
    files: tuple[DeliveryFile, ...] = Field(max_length=1000)
    references: tuple[DeliveryReference, ...] = Field(max_length=4000)
    gaps: tuple[str, ...] = ()
    evidence_status: Literal["partial", "complete"] = "partial"
    reproduction_status: Literal["NOT_RUN"] = "NOT_RUN"

    @model_validator(mode="after")
    def unique_files(self) -> ProjectDeliveryManifestV2:
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("Duplicate archive member")
        if self.gaps and self.evidence_status == "complete":
            raise ValueError("Missing evidence cannot be complete")
        return self

    def content_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def parse_delivery_manifest(payload: object) -> ProjectDeliveryManifest | ProjectDeliveryManifestV2:
    if isinstance(payload, dict) and payload.get("schema_version") == "cygnusx.project_delivery.v2":
        return ProjectDeliveryManifestV2.model_validate(payload)
    return ProjectDeliveryManifest.model_validate(payload)


class CreateProjectExport(DeliveryDTO):
    selection: ExportSelectionV2 | ExportSelection
    manifest_digest: str = Field(pattern=SHA)
    request_key: UUID


class ProjectExportStatus(DeliveryDTO):
    id: UUID
    project_id: UUID
    status: Literal[
        "queued",
        "collecting",
        "validating",
        "packaging",
        "verifying",
        "publishing",
        "ready",
        "failed",
    ]
    manifest_digest: str
    evidence_partial: bool
    attempt_count: int
    retryable: bool
    error_code: str | None
    archive_sha256: str | None
    archive_size: int | None
    file_record_id: UUID | None
