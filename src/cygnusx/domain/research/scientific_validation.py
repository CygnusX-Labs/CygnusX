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
    if handoff.validation.get("dataset_ready") is not True:
        gaps.add("HANDOFF_NOT_READY")
    groups: Counter[str] = Counter()
    batches: dict[str, set[str]] = defaultdict(set)
    seen_samples: set[str] = set()
    species: set[str] = set()
    for sample in handoff.samples:
        annotation = sample.get("user_annotation", {})
        source = sample.get("source_metadata", {})
        if not isinstance(annotation, dict) or not isinstance(source, dict):
            gaps.add("SAMPLE_METADATA_INVALID")
            annotation = annotation if isinstance(annotation, dict) else {}
            source = source if isinstance(source, dict) else {}
        raw_identity = sample.get("sample_id") or sample.get("sample_key")
        identity = raw_identity.strip() if isinstance(raw_identity, str) else ""
        unique = bool(identity)
        if not unique:
            gaps.add("SAMPLE_IDENTITY_REQUIRED")
        elif identity in seen_samples:
            unique = False
            gaps.add("DUPLICATE_SAMPLE_IDENTITY")
        else:
            seen_samples.add(identity)
        group = annotation.get("group")
        if (
            not isinstance(group, str)
            or not group.strip()
            or annotation.get("group_confirmed") is not True
        ):
            gaps.add("HUMAN_GROUP_REVIEW_REQUIRED")
        elif unique:
            groups[str(group)] += 1
            if annotation.get("batch"):
                batches[str(annotation["batch"])].add(str(group))
        metadata = source.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        tissue = source.get("tissue") or metadata.get("tissue")
        if not isinstance(tissue, str) or not tissue.strip():
            gaps.add("TISSUE_EVIDENCE_REQUIRED")
        condition = [
            source.get("treatment"), source.get("disease"),
            metadata.get("treatment"), metadata.get("disease"),
            metadata.get("characteristics"),
        ]
        if not any(
            isinstance(value, str) and value.strip()
            or isinstance(value, list) and any(isinstance(v, str) and v.strip() for v in value)
            for value in condition
        ):
            gaps.add("CONDITION_EVIDENCE_REVIEW_REQUIRED")
        labels = [source.get("species"), source.get("organism")]
        if isinstance(metadata, dict):
            labels.append(metadata.get("organism"))
        normalized = {
            " ".join(label.split()).casefold()
            for label in labels
            if isinstance(label, str) and label.strip()
        }
        if not normalized:
            gaps.add("SPECIES_EVIDENCE_REQUIRED")
        if len(normalized) > 1:
            gaps.add("SPECIES_EVIDENCE_CONFLICT")
        species.update(normalized)
        if flow_id == "rna_seq" and source.get("library_layout") not in {"PAIRED", "SINGLE"}:
            gaps.add("LIBRARY_LAYOUT_REQUIRED")
        if sample.get("mapping_status") != "CONFIRMED":
            gaps.add("SAMPLE_MAPPING_REQUIRED")
    if len(species) > 1:
        gaps.add("MIXED_SPECIES_REVIEW_REQUIRED")
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
