"""Read-only RI10 projection, not a persisted or general-purpose claim engine."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cygnusx.application.schemas.research_claims import ArtifactCellRequest, ClaimDraft


class ClaimProvenanceRequest(ArtifactCellRequest):
    source_report_id: UUID | None = None
    claim: ClaimDraft | None = None


class ClaimProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    schema_version: Literal["cygnusx.claim_provenance.v1"] = "cygnusx.claim_provenance.v1"
    claim_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_type: Literal["DEG_TABLE_CELL"] = "DEG_TABLE_CELL"
    claim_text: str
    claim_text_verified: Literal[False] = False
    project_id: UUID
    source_report_id: UUID | None
    report_version: int | None
    report_snapshot_id: UUID | None
    snapshot_digest: str | None
    task_id: UUID
    result_observation_id: UUID | None
    observation_digest: str | None
    observation_binding: Literal["VERIFIED_ASSOCIATION", "NOT_RECORDED"]
    file_record_id: UUID
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    table_identifier: Literal["deg.tsv"] = "deg.tsv"
    row_identifier: str
    row_number: int
    column_identifier: str
    value: float | None
    transformation: Literal["identity"] = "identity"
    verification_status: Literal["VERIFIED_VALUE", "NOT_VERIFIED"]
    supported_statement: str | None
    supported_statement_status: Literal["SUPPORTED_CLAIM", "NOT_VERIFIED"]
    interpretation_status: Literal["AI_INTERPRETATION"] | None
    dataset_version_id: UUID | None
    analysis_link_id: UUID | None
    definition_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    execution_binding_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    definition_status: Literal["VERIFIED_DOCUMENT", "REFERENCE_ONLY", "NOT_RECORDED"]
    input_file_record_ids: tuple[UUID, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    verification_scope: Literal["current_cell_bytes_not_claim_truth_or_historical_execution"] = (
        "current_cell_bytes_not_claim_truth_or_historical_execution"
    )
    reproducibility_status: Literal["NOT_RUN"] = "NOT_RUN"
