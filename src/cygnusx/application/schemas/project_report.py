"""Versioned project report inputs; clients provide references, never facts."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from cygnusx.application.schemas.claim_provenance import ClaimProvenance
from cygnusx.application.schemas.execution_evidence import canonical_digest
from cygnusx.application.schemas.project_delivery import SHA, DeliveryDTO, ProjectDeliveryManifest
from cygnusx.application.schemas.research_claims import ArtifactCellRequest


class ProjectClaimSelection(ArtifactCellRequest):
    source_report_id: UUID | None = None


class PrepareProjectReport(DeliveryDTO):
    source_manifest_job_id: UUID
    claims: tuple[ProjectClaimSelection, ...] = Field(default=(), max_length=100)
    format: Literal["html", "html_pdf"] = "html"

    @model_validator(mode="after")
    def unique_cells(self) -> "PrepareProjectReport":
        keys = [canonical_digest(c.model_dump(mode="json")) for c in self.claims]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate claim selection")
        return self


class FrozenProjectClaims(DeliveryDTO):
    schema_version: Literal["cygnusx.project_verified_claim_selection.v1"] = (
        "cygnusx.project_verified_claim_selection.v1"
    )
    claims: tuple[ClaimProvenance, ...] = ()

    def content_digest(self) -> str:
        data = self.model_dump(mode="json")
        data["claims"] = sorted(data["claims"], key=lambda c: c["claim_id"])
        return canonical_digest(data)


class ProjectReportSource(DeliveryDTO):
    schema_version: Literal["cygnusx.project_report_source.v1"] = "cygnusx.project_report_source.v1"
    source_kind: Literal["project"] = "project"
    report_type: Literal["project_scientific_summary"] = "project_scientific_summary"
    owner_id: UUID
    project_id: UUID
    source_manifest_job_id: UUID
    source_manifest_digest: str = Field(pattern=SHA)
    manifest: ProjectDeliveryManifest
    selection: FrozenProjectClaims
    selection_digest: str = Field(pattern=SHA)
    format: Literal["html", "html_pdf"]
    template_version: Literal["project-summary.v1"] = "project-summary.v1"
    renderer_version: Literal["project-summary-adapter.v1"] = "project-summary-adapter.v1"
    renderer_runtime: Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    redaction_policy_version: Literal["project-report-allowlist.v1"] = "project-report-allowlist.v1"

    @model_validator(mode="after")
    def validate_identity(self) -> "ProjectReportSource":
        if (self.owner_id, self.project_id) != (self.manifest.owner_id, self.manifest.project_id):
            raise ValueError("Manifest identity mismatch")
        if self.manifest.content_digest() != self.source_manifest_digest:
            raise ValueError("Manifest digest mismatch")
        if self.selection.content_digest() != self.selection_digest:
            raise ValueError("Selection digest mismatch")
        if any(c.project_id != self.project_id for c in self.selection.claims):
            raise ValueError("Claim project mismatch")
        for claim in self.selection.claims:
            if claim.task_id not in self.manifest.selection.task_ids or not any(
                f.source_kind == "file_record"
                and f.source_id == claim.file_record_id
                and f.task_id == claim.task_id
                and f.sha256 == claim.file_sha256
                for f in self.manifest.files
            ):
                raise ValueError("Claim outside M0 byte scope")
        return self

    def content_digest(self) -> str:
        data = self.model_dump(mode="json")
        data["selection"]["claims"] = sorted(
            data["selection"]["claims"], key=lambda c: c["claim_id"]
        )
        return canonical_digest(data)


class CreateProjectReport(PrepareProjectReport):
    prepare_digest: str = Field(pattern=SHA)
    request_key: UUID
