"""Untrusted claim suggestions and server-computed evidence assessments."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from cygnusx.application.schemas.research_plan import PlanInput


class EvidenceReference(PlanInput):
    kind: Literal["SOURCE", "DATASET_VERSION", "RESULT_MANIFEST", "ARTIFACT", "ARTICLE"]
    resource_id: str = Field(min_length=1, max_length=128)


class ClaimDraft(PlanInput):
    claim_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    claim_text: str = Field(min_length=1, max_length=2000)
    claim_type: Literal["DATASET_FACT", "COMPUTATIONAL_RESULT", "LITERATURE_CONTEXT", "HYPOTHESIS"]
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    alternative_explanations: list[str] = Field(default_factory=list, max_length=10)


class ClaimAssessment(PlanInput):
    claim: ClaimDraft
    provenance_status: Literal["VERIFIED", "PARTIAL", "UNVERIFIED", "CONTRADICTORY", "UNKNOWN"]
    supported_refs: list[EvidenceReference]
    gaps: list[str]
    # Free-text claim truth is not inferred from database foreign keys.
    fact_checked: Literal[False] = False


class ArtifactCellRequest(PlanInput):
    task_id: UUID
    file_record_id: UUID
    feature_id: str = Field(min_length=1, max_length=256)
    column: Literal["log2FoldChange", "pvalue", "padj", "baseMean", "lfcSE", "stat"]
