"""Versioned, immutable evidence contract; no renderer or persistence side effects."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    NOT_RECORDED = "not_recorded"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    VERIFICATION_FAILED = "verification_failed"
    ESTIMATED = "estimated"


class FrozenEvidenceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class EvidenceSource(FrozenEvidenceModel):
    source_type: Literal["task", "run", "run_event", "result_manifest", "file_record", "gap"]
    source_id: str
    source_path: str | None = None
    captured_at: AwareDatetime
    observed_at: AwareDatetime | None = None
    capture_method: Literal["database_read", "manifest_read", "file_hash", "gap_annotation"]
    verification_status: EvidenceStatus
    verification_details: str


class SourceExecution(FrozenEvidenceModel):
    source_execution_kind: Literal["task", "agent", "case"] = "task"
    task_id: UUID | None = None
    run_id: UUID | None = None
    project_id: UUID | None = None
    project_slug: str | None = None
    owner_id: UUID
    execution_attempt_id: str | None = None
    source_reference: str
    association_status: Literal["verified", "not_recorded", "not_applicable"]

    @model_validator(mode="after")
    def validate_identity(self) -> SourceExecution:
        if self.source_execution_kind == "task" and self.task_id is None:
            raise ValueError("Task source requires task_id")
        if self.run_id is not None and self.association_status != "verified":
            raise ValueError("Run association must be verified")
        if self.run_id is None and self.association_status == "verified":
            raise ValueError("Verified Task/Run association requires run_id")
        return self


class SourceWatermark(FrozenEvidenceModel):
    source_type: str
    source_id: str
    revision: str


class FileFingerprint(FrozenEvidenceModel):
    algorithm: Literal["md5", "sha256"]
    value: str
    scope: Literal["manifest_declared", "capture_bytes", "execution_bytes"]
    verified_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_hash(self) -> FileFingerprint:
        length = 32 if self.algorithm == "md5" else 64
        if len(self.value) != length or any(c not in "0123456789abcdef" for c in self.value):
            raise ValueError("Invalid lowercase hexadecimal fingerprint")
        return self


class FactEvidence(FrozenEvidenceModel):
    """Scalar fact. Arbitrary parameters, logs and prompts are deliberately unsupported."""

    field: str
    value: str | int | float | bool | None = None
    source: EvidenceSource


class ArtifactEvidence(FrozenEvidenceModel):
    artifact_reference: str
    display_name: str | None = None
    file_record_id: UUID | None = None
    category: Literal["report", "qc", "expression", "deg", "log", "other"] = "other"
    kind: Literal["file", "directory"] = "file"
    size_bytes: int | None = Field(default=None, ge=0)
    fingerprints: tuple[FileFingerprint, ...] = ()
    source: EvidenceSource
    origin: EvidenceSource


class ExecutionStepEvidence(FrozenEvidenceModel):
    sequence: int = Field(ge=0)
    phase: str
    status: str
    occurred_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    source: EvidenceSource


class ToolCallEvidence(FrozenEvidenceModel):
    tool_name: str | None = None
    source: EvidenceSource


class QualityGateEvidence(FrozenEvidenceModel):
    rule_version: str | None = None
    decision: Literal["pass", "warning", "review_required", "fail"] | None = None
    source: EvidenceSource

    @model_validator(mode="after")
    def decision_requires_evidence(self) -> QualityGateEvidence:
        if self.decision is not None and self.source.verification_status != EvidenceStatus.VERIFIED:
            raise ValueError("A QC decision requires verified decision evidence")
        return self


class ProvenanceEvidence(FrozenEvidenceModel):
    subject_reference: str
    relation: Literal["produced_by", "source_unknown"]
    object_reference: str | None = None
    source: EvidenceSource


class ReproducibilityEvidence(FrozenEvidenceModel):
    assessment: Literal["insufficient_evidence", "not_assessed"] = "insufficient_evidence"
    blockers: tuple[str, ...]
    source: EvidenceSource


class MissingEvidence(FrozenEvidenceModel):
    field: str
    source: EvidenceSource


class EvidenceCoverage(FrozenEvidenceModel):
    """Counts of evidence observations, never a scientific pass percentage."""

    verified: int = Field(default=0, ge=0)
    not_recorded: int = Field(default=0, ge=0)
    unavailable: int = Field(default=0, ge=0)
    not_applicable: int = Field(default=0, ge=0)
    verification_failed: int = Field(default=0, ge=0)
    estimated: int = Field(default=0, ge=0)


class ReportSnapshot(FrozenEvidenceModel):
    schema_version: Literal["cygnusx.report_snapshot.v1"] = "cygnusx.report_snapshot.v1"
    digest_policy_version: Literal["stable_facts.v1"] = "stable_facts.v1"
    redaction_policy_version: Literal["owner_allowlist.v1", "owner_allowlist.v2"] = "owner_allowlist.v1"
    immutable_version: int = Field(default=1, ge=1)
    report_id: UUID | None = None
    generated_at: AwareDatetime
    source_execution: SourceExecution
    source_references: tuple[EvidenceSource, ...]
    source_watermarks: tuple[SourceWatermark, ...]
    visibility_scope: Literal["owner"] = "owner"
    inputs: tuple[FactEvidence, ...]
    environment: tuple[FactEvidence, ...]
    execution_steps: tuple[ExecutionStepEvidence, ...]
    tool_calls: tuple[ToolCallEvidence, ...]
    quality_gates: tuple[QualityGateEvidence, ...]
    artifacts: tuple[ArtifactEvidence, ...]
    provenance: tuple[ProvenanceEvidence, ...]
    reproducibility: ReproducibilityEvidence
    evidence_coverage: EvidenceCoverage
    warnings: tuple[str, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    capture_started_at: AwareDatetime
    capture_finished_at: AwareDatetime
    snapshot_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_capture(self) -> ReportSnapshot:
        if self.capture_finished_at < self.capture_started_at:
            raise ValueError("Capture window is reversed")
        if self.snapshot_digest is not None and self.snapshot_digest != snapshot_digest(self):
            raise ValueError("Snapshot digest mismatch")
        counts = Counter(source.verification_status.value for source in self.source_references)
        if self.evidence_coverage != EvidenceCoverage(**counts):
            raise ValueError("Evidence coverage does not match source observations")
        return self


def canonical_serialization(snapshot: ReportSnapshot) -> bytes:
    """Full archive bytes (including capture timestamps); stable ordering, UTF-8, no NaN."""
    return json.dumps(
        snapshot.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def snapshot_digest(snapshot: ReportSnapshot) -> str:
    """Stable facts: include observation times/revisions and policy, exclude capture metadata.

    Tuple order is significant. Recapture can change availability/hashes, hence the digest.
    This is not an execution-time attestation, signature or reproducibility certification.
    """
    data = snapshot.model_dump(
        mode="json",
        exclude={
            "snapshot_digest",
            "report_id",
            "immutable_version",
            "generated_at",
            "capture_started_at",
            "capture_finished_at",
            "evidence_coverage",
        },
    )

    def scrub(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: scrub(item)
                for key, item in value.items()
                if key not in {"captured_at", "verified_at"}
                and not (key == "display_name" and item is None)
            }
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    content = json.dumps(
        scrub(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def freeze_snapshot(snapshot: ReportSnapshot) -> ReportSnapshot:
    """Seal and validate; persisted/untrusted copies must use model_validate[_json]."""
    data = snapshot.model_dump(mode="python")
    data["snapshot_digest"] = snapshot_digest(snapshot)
    return ReportSnapshot.model_validate(data)
