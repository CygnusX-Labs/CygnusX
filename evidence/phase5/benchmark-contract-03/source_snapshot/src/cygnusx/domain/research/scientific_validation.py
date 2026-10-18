"""Read-only scientific eligibility, not a replacement for Flow/DESeq2 validation.

Only accepts a server-resolved Handoff. Model-suggested annotations are not truth.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from cygnusx.application.schemas.dataset import DataHandoff, DataType
from cygnusx.application.schemas.research_claims import (
    ClaimAssessment,
    ClaimDraft,
    EvidenceReference,
)


@dataclass(frozen=True)
class ScientificEligibility:
    status: str
    flow_id: str
    gaps: tuple[str, ...]


def check_scientific_inputs(handoff: DataHandoff, flow_id: str) -> ScientificEligibility:
    gaps = set(str(x) for x in handoff.validation.get("blocking_reasons", []))
    if flow_id not in {"counts_deg", "rna_seq"}:
        return ScientificEligibility("UNSUPPORTED", flow_id, ("FLOW_UNSUPPORTED",))
    active = [
        a for a in handoff.assets if a.asset_role not in {"metadata", "annotation", "archive"}
    ]
    expected = DataType.RAW_INTEGER_COUNTS if flow_id == "counts_deg" else DataType.RAW_FASTQ
    if not active:
        gaps.add("NO_SCIENTIFIC_INPUT")
    if any(a.data_type != expected for a in active):
        gaps.add("INPUT_TYPE_MISMATCH")
    if any(a.data_type == DataType.UNKNOWN for a in active):
        gaps.add("PROCESSING_EVIDENCE_REQUIRED")
    if any(a.checksum_status != "VERIFIED" or a.availability != "AVAILABLE" for a in active):
        gaps.add("INPUT_BYTES_NOT_VERIFIED")
    if not handoff.source:
        gaps.add("SOURCE_EVIDENCE_REQUIRED")
    if not handoff.validation.get("dataset_ready"):
        gaps.add("HANDOFF_NOT_READY")
    groups: Counter[str] = Counter()
    batches: dict[str, set[str]] = defaultdict(set)
    for sample in handoff.samples:
        annotation = sample.get("user_annotation", {})
        source = sample.get("source_metadata", {})
        group = annotation.get("group")
        if not group or not annotation.get("group_confirmed"):
            gaps.add("HUMAN_GROUP_REVIEW_REQUIRED")
        else:
            groups[str(group)] += 1
            if annotation.get("batch"):
                batches[str(annotation["batch"])].add(str(group))
        if not source.get("organism"):
            gaps.add("SPECIES_EVIDENCE_REQUIRED")
        if flow_id == "rna_seq" and source.get("library_layout") not in {"PAIRED", "SINGLE"}:
            gaps.add("LIBRARY_LAYOUT_REQUIRED")
        if sample.get("mapping_status") != "CONFIRMED":
            gaps.add("SAMPLE_MAPPING_REQUIRED")
    if len(groups) < 2:
        gaps.add("CONTROL_AND_TREATMENT_REQUIRED")
    if not groups or min(groups.values()) < 2:
        gaps.add("BIOLOGICAL_REPLICATION_REQUIRED")
    if batches and len(batches) > 1 and all(len(values) == 1 for values in batches.values()):
        gaps.add("DESIGN_CONFOUNDING_REVIEW_REQUIRED")
    if flow_id == "rna_seq":
        # Real reference/paired-file checks still belong to the existing final Flow validator.
        gaps.add("REFERENCE_AND_FASTQ_PAIRING_REQUIRE_FLOW_PREPARE")
    return ScientificEligibility(
        "REVIEW_REQUIRED" if gaps else "ELIGIBLE_FOR_PREPARE", flow_id, tuple(sorted(gaps))
    )


def assess_claim(
    claim: ClaimDraft,
    available: set[tuple[str, str]],
    *,
    contradictory: bool = False,
) -> ClaimAssessment:
    """Assess reference grounding only; never promote prose to verified numeric facts."""
    supported = [ref for ref in claim.evidence_refs if (ref.kind, ref.resource_id) in available]
    gaps = []
    if len(supported) != len(claim.evidence_refs):
        gaps.append("EVIDENCE_REFERENCE_MISSING_OR_UNVERIFIED")
    if not supported:
        gaps.append("NO_VERIFIED_EVIDENCE")
    if claim.claim_type == "HYPOTHESIS":
        gaps.append("HYPOTHESIS_NOT_ESTABLISHED_FACT")
    if claim.claim_type == "COMPUTATIONAL_RESULT":
        gaps.append("NUMERIC_VALUES_REQUIRE_VERIFIED_ARTIFACT_CELL")
    # Even an existing article/manifest cannot establish that a particular sentence is true.
    gaps.append("CLAIM_TEXT_REQUIRES_FACT_REVIEW")
    return ClaimAssessment(
        claim=claim,
        provenance_status="CONTRADICTORY"
        if contradictory
        else "PARTIAL"
        if supported
        else "UNVERIFIED",
        supported_refs=[EvidenceReference.model_validate(ref.model_dump()) for ref in supported],
        gaps=gaps,
    )
