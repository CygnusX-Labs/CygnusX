"""Synthetic scientific safeguards; values are not public-data benchmark results."""

from uuid import uuid4

import pytest

from cygnusx.application.schemas.dataset import DataHandoff, HandoffAsset
from cygnusx.application.schemas.research_claims import ClaimDraft
from cygnusx.domain.research.scientific_validation import assess_claim, check_scientific_inputs

pytestmark = pytest.mark.unit


def handoff(dtype="RAW_INTEGER_COUNTS"):
    return DataHandoff(
        project_id=uuid4(),
        dataset_id=uuid4(),
        dataset_version_id=uuid4(),
        source=[{"repository": "synthetic", "processing": "synthetic raw counts"}],
        ingestion=[],
        assets=[
            HandoffAsset(
                asset_id=uuid4(),
                file_record_id=uuid4(),
                asset_role="raw_counts",
                data_type=dtype,
                format="tsv",
                size=100,
                sha256="a" * 64,
                checksum_status="VERIFIED",
                availability="AVAILABLE",
            )
        ],
        samples=[
            {
                "sample_id": f"synthetic-{index}",
                "mapping_status": "CONFIRMED",
                "source_metadata": {
                    "organism": "synthetic", "tissue": "synthetic tissue",
                    "metadata": {"treatment": group},
                },
                "user_annotation": {"group": group, "group_confirmed": True},
            }
            for index, group in enumerate(["control", "control", "treatment", "treatment"])
        ],
        validation={"dataset_ready": True},
        provenance={},
    )


def test_raw_counts_prepares_without_claiming_live_readiness():
    result = check_scientific_inputs(handoff(), "counts_deg")
    assert result.status == "ELIGIBLE_FOR_PREPARE"
    assert not result.gaps


@pytest.mark.parametrize(
    "dtype",
    [
        "NORMALIZED_EXPRESSION_TPM",
        "NORMALIZED_EXPRESSION_FPKM",
        "NORMALIZED_EXPRESSION_CPM",
        "TRANSFORMED_EXPRESSION",
        "MICROARRAY_EXPRESSION",
        "SINGLE_CELL_COUNT_MATRIX",
        "RAW_FASTQ",
        "UNKNOWN",
    ],
)
def test_wrong_matrix_cannot_enter_deseq2(dtype):
    result = check_scientific_inputs(handoff(dtype), "counts_deg")
    assert result.status == "REVIEW_REQUIRED" and "INPUT_TYPE_MISMATCH" in result.gaps
    if dtype == "UNKNOWN":
        assert "PROCESSING_EVIDENCE_REQUIRED" in result.gaps


def test_fastq_pairing_and_species_require_evidence():
    data = handoff("RAW_FASTQ")
    data.samples[0]["source_metadata"] = {}
    result = check_scientific_inputs(data, "rna_seq")
    assert {
        "LIBRARY_LAYOUT_REQUIRED",
        "SPECIES_EVIDENCE_REQUIRED",
        "REFERENCE_AND_FASTQ_PAIRING_REQUIRE_FLOW_PREPARE",
    } <= set(result.gaps)


def test_replicates_and_confounding_not_silently_accepted():
    data = handoff()
    for i, sample in enumerate(data.samples):
        sample["user_annotation"]["batch"] = "a" if i < 2 else "b"
    assert "DESIGN_CONFOUNDING_REVIEW_REQUIRED" in check_scientific_inputs(data, "counts_deg").gaps
    data.samples = [data.samples[0], data.samples[-1]]
    assert "BIOLOGICAL_REPLICATION_REQUIRED" in check_scientific_inputs(data, "counts_deg").gaps


def test_unsupported_omics_refused():
    assert check_scientific_inputs(handoff(), "scrna").status == "UNSUPPORTED"


def test_reference_existence_is_not_fact_verification_and_conflicts_remain():
    claim = ClaimDraft(
        claim_id="result",
        claim_text="Synthetic example: mechanism causes disease",
        claim_type="COMPUTATIONAL_RESULT",
        evidence_refs=[{"kind": "ARTIFACT", "resource_id": "a"}],
    )
    missing = assess_claim(claim, set())
    assert missing.provenance_status == "UNVERIFIED" and not missing.fact_checked
    linked = assess_claim(claim, {("ARTIFACT", "a")})
    assert linked.provenance_status == "PARTIAL" and not linked.fact_checked
    assert "NUMERIC_VALUES_REQUIRE_VERIFIED_ARTIFACT_CELL" in linked.gaps
    assert (
        assess_claim(claim, {("ARTIFACT", "a")}, contradictory=True).provenance_status
        == "CONTRADICTORY"
    )
    claim.claim_type = "HYPOTHESIS"
    assert "HYPOTHESIS_NOT_ESTABLISHED_FACT" in assess_claim(claim, set()).gaps


def test_actual_handoff_species_shape_and_conflicting_species():
    data = handoff()
    for sample in data.samples:
        sample["source_metadata"] = {
            "species": "Homo sapiens", "tissue": "synthetic tissue",
            "metadata": {"organism": "Homo sapiens", "treatment": "synthetic condition"}
        }
    assert check_scientific_inputs(data, "counts_deg").status == "ELIGIBLE_FOR_PREPARE"
    data.samples[0]["source_metadata"]["metadata"]["organism"] = "Mus musculus"
    result = check_scientific_inputs(data, "counts_deg")
    assert "SPECIES_EVIDENCE_CONFLICT" in result.gaps
    assert "MIXED_SPECIES_REVIEW_REQUIRED" in result.gaps


def test_duplicate_sample_rows_do_not_supply_biological_replicates():
    data = handoff()
    data.samples[1]["sample_id"] = data.samples[0]["sample_id"]
    result = check_scientific_inputs(data, "counts_deg")
    assert "DUPLICATE_SAMPLE_IDENTITY" in result.gaps
    assert "BIOLOGICAL_REPLICATION_REQUIRED" in result.gaps
    assert result.status == "REVIEW_REQUIRED"


def test_missing_sample_identity_requires_review():
    data = handoff()
    for sample in data.samples:
        sample.pop("sample_id")
    result = check_scientific_inputs(data, "counts_deg")
    assert "SAMPLE_IDENTITY_REQUIRED" in result.gaps
    assert result.status == "REVIEW_REQUIRED"


def test_missing_tissue_and_condition_remain_explicit_evidence_gaps():
    data = handoff()
    data.samples[0]["source_metadata"] = {"species": "synthetic"}
    result = check_scientific_inputs(data, "counts_deg")
    assert "TISSUE_EVIDENCE_REQUIRED" in result.gaps
    assert "CONDITION_EVIDENCE_REVIEW_REQUIRED" in result.gaps
    assert result.status == "REVIEW_REQUIRED"


@pytest.mark.parametrize("annotation", [[], {"group": "control", "group_confirmed": "true"}])
def test_malformed_or_non_boolean_review_does_not_establish_sample_group(annotation):
    data = handoff()
    data.samples[0]["user_annotation"] = annotation
    result = check_scientific_inputs(data, "counts_deg")
    assert result.status == "REVIEW_REQUIRED"
    assert "HUMAN_GROUP_REVIEW_REQUIRED" in result.gaps
