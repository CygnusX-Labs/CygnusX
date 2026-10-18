"""Task-first Phase 0 collector. No scheduling, LLM, rendering or business writes."""

from __future__ import annotations

import asyncio
import math
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from cygnusx.application.schemas.report_snapshot import (
    EvidenceCoverage,
    EvidenceSource,
    EvidenceStatus,
    ExecutionStepEvidence,
    FactEvidence,
    MissingEvidence,
    ProvenanceEvidence,
    QualityGateEvidence,
    ReportSnapshot,
    ReproducibilityEvidence,
    SourceExecution,
    SourceWatermark,
    ToolCallEvidence,
    freeze_snapshot,
)
from cygnusx.application.services.report_snapshot_manifest import (
    RNAResultManifestAdapter,
    evidence,
    safe_display_label,
    safe_label,
)
from cygnusx.application.services.report_snapshot_sources import (
    TaskEvidenceSource,
    validate_records,
)
from cygnusx.infrastructure.storage import get_path_factory
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory

# Owner projection v1: only numeric/switch values, no sample labels, paths or arbitrary text.
SAFE_PARAMETER_KEYS = frozenset(
    {
        "qc_clean",
        "mapping",
        "count",
        "DEG",
        "call_variant",
        "detect_novel_transcripts",
        "rmats",
        "gene_fusion",
        "report",
        "cores",
        "threads",
        "padj",
        "pvalue",
        "log2fc",
    }
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReportSnapshotBuilder:
    def __init__(
        self,
        source: TaskEvidenceSource,
        *,
        factory: StoragePathFactory | None = None,
        clock: Callable[[], datetime] = utc_now,
    ):
        self._source = source
        self._manifest = RNAResultManifestAdapter(factory or get_path_factory())
        self._clock = clock

    async def build(
        self,
        owner_id: UUID,
        task_id: UUID,
        *,
        run_id: UUID | None = None,
        report_id: UUID | None = None,
        immutable_version: int = 1,
    ) -> ReportSnapshot:
        started = self._clock()
        records = await self._source.read(owner_id, task_id, run_id)
        validate_records(records, owner_id, task_id, run_id)
        task, run = records.task, records.run
        projection = await asyncio.to_thread(self._manifest.read, records, started)
        task_source = evidence(
            "task",
            str(task.id),
            started,
            EvidenceStatus.VERIFIED,
            "Owner-scoped Task record; status is not scientific verification",
            observed_at=task.updated_at,
        )
        sources = [task_source, projection.source]
        watermarks = [
            SourceWatermark(
                source_type="task", source_id=str(task.id), revision=task.updated_at.isoformat()
            )
        ]
        watermarks.extend(projection.watermarks)
        watermarks.extend(
            SourceWatermark(
                source_type="file_record",
                source_id=str(file.id),
                revision=file.updated_at.isoformat(),
            )
            for file in records.files
        )
        warnings = [
            "parameters_and_labels_redacted:owner_allowlist.v2",
            "capture_is_not_execution_attestation",
            "input_lineage_not_recorded",
        ]
        missing: list[MissingEvidence] = []

        def gap(
            field: str, details: str, status: EvidenceStatus = EvidenceStatus.NOT_RECORDED
        ) -> EvidenceSource:
            source = evidence("gap", field, started, status, details, method="gap_annotation")
            missing.append(MissingEvidence(field=field, source=source))
            sources.append(source)
            return source

        if records.files_truncated:
            warnings.append("file_records_truncated_at_2000")
            gap(
                "artifacts.complete",
                "File record capture limit reached",
                EvidenceStatus.UNAVAILABLE,
            )
        inputs = [
            FactEvidence(field="flow_id", value=task.flow_id, source=task_source),
            FactEvidence(field="sample_count", value=task.sample_count, source=task_source),
        ]
        for key in sorted(SAFE_PARAMETER_KEYS):
            value = task.parameters.get(key)
            if isinstance(value, (bool, int, float)) and (
                not isinstance(value, float) or math.isfinite(value)
            ):
                inputs.append(
                    FactEvidence(field=f"parameters.{key}", value=value, source=task_source)
                )
        inputs.append(
            FactEvidence(
                field="input_file_identity",
                source=gap(
                    "inputs",
                    "Task parameters/sample paths do not establish immutable input file lineage",
                ),
            )
        )
        inputs.append(
            FactEvidence(
                field="task_name",
                value=safe_display_label(task.name),
                source=task_source
                if safe_display_label(task.name)
                else gap(
                    "task_name",
                    "Task label absent or omitted by owner bounded-label redaction policy",
                ),
            )
        )
        environment = list(projection.facts)
        if run:
            run_source = evidence(
                "run",
                str(run.id),
                started,
                EvidenceStatus.VERIFIED,
                "Explicit confirmed Run.task_id and owner association; plan is not runtime",
                observed_at=run.confirmed_at,
            )
            sources.append(run_source)
            watermarks.append(
                SourceWatermark(
                    source_type="run", source_id=str(run.id), revision=run.updated_at.isoformat()
                )
            )
            if release := safe_label(run.release_id):
                environment.append(
                    FactEvidence(field="requested_flow_release", value=release, source=run_source)
                )
        else:
            gap("run_association", "Ordinary Task has no recorded Run; no inferred link")
        environment.extend(
            [
                FactEvidence(
                    field="observed_software_versions",
                    source=gap(
                        "software_versions",
                        "No execution-bound software probe; current environment excluded",
                    ),
                ),
                FactEvidence(
                    field="runtime_image_digest",
                    source=gap(
                        "runtime_image_digest", "No execution-bound runtime image digest recorded"
                    ),
                ),
                FactEvidence(
                    field="reference_fingerprints",
                    source=gap(
                        "reference_fingerprints",
                        "No immutable execution-bound reference fingerprints",
                    ),
                ),
            ]
        )
        steps = [
            ExecutionStepEvidence(
                sequence=0,
                phase="task",
                status=safe_label(task.status) or "redacted",
                occurred_at=task.started_at,
                finished_at=task.finished_at,
                source=task_source,
            )
        ]
        steps.extend(projection.steps)
        for event in records.events:
            source = evidence(
                "run_event",
                str(event.id),
                started,
                EvidenceStatus.VERIFIED,
                "Recorded Run event; payload/log/commands omitted",
                observed_at=event.occurred_at,
            )
            sources.append(source)
            steps.append(
                ExecutionStepEvidence(
                    sequence=event.sequence,
                    phase=safe_label(event.phase) or "redacted",
                    status=safe_label(event.status) or "redacted",
                    occurred_at=event.occurred_at,
                    source=source,
                )
            )
        if records.events:
            watermarks.append(
                SourceWatermark(
                    source_type="run_events",
                    source_id=str(run.id) if run else str(task.id),
                    revision=str(records.events[-1].sequence),
                )
            )
        if records.events_truncated:
            warnings.append("run_events_truncated_at_1000")
            gap(
                "execution_steps.complete",
                "Capture budget reached; event history is incomplete",
                EvidenceStatus.UNAVAILABLE,
            )
        gap("execution_steps.io", "Events do not establish full scientific step inputs/outputs")
        tool_calls = (
            ToolCallEvidence(
                source=gap(
                    "tool_calls",
                    "MCP/Skill/Chat calls have no verified Task association in this adapter",
                )
            ),
        )
        gates = (
            QualityGateEvidence(
                source=gap(
                    "quality_gates", "QC artifacts are measurements, not recorded decision gates"
                )
            ),
        )
        if projection.source.verification_status != EvidenceStatus.VERIFIED:
            missing.append(MissingEvidence(field="result_manifest", source=projection.source))
        provenance: list[ProvenanceEvidence] = []
        for artifact in projection.artifacts:
            sources.extend((artifact.source, artifact.origin))
            if artifact.source.verification_status in {
                EvidenceStatus.UNAVAILABLE,
                EvidenceStatus.VERIFICATION_FAILED,
            }:
                missing.append(
                    MissingEvidence(field=artifact.artifact_reference, source=artifact.source)
                )
                warnings.append(f"artifact_{artifact.source.verification_status.value}")
            if artifact.origin.verification_status != EvidenceStatus.VERIFIED:
                missing.append(
                    MissingEvidence(
                        field=f"{artifact.artifact_reference}.origin", source=artifact.origin
                    )
                )
            provenance.append(
                ProvenanceEvidence(
                    subject_reference=artifact.artifact_reference,
                    relation="produced_by"
                    if artifact.origin.verification_status == EvidenceStatus.VERIFIED
                    else "source_unknown",
                    object_reference=f"task:{task.id}"
                    if artifact.origin.verification_status == EvidenceStatus.VERIFIED
                    else None,
                    source=artifact.origin,
                )
            )
        if not projection.artifacts:
            gap("artifacts", "No explicitly associated artifacts captured")
        for fact in projection.facts:
            sources.append(fact.source)
        reproducibility_source = gap(
            "reproducibility",
            "No rerun or scientific comparison performed",
            EvidenceStatus.NOT_APPLICABLE,
        )
        counts = Counter(source.verification_status.value for source in sources)
        finished = self._clock()
        return freeze_snapshot(
            ReportSnapshot(
                research_delivery=records.research_delivery,
                redaction_policy_version="owner_allowlist.v2",
                report_id=report_id,
                immutable_version=immutable_version,
                generated_at=finished,
                source_execution=SourceExecution(
                    task_id=task.id,
                    project_id=records.research_delivery.project_id
                    if records.research_delivery
                    else None,
                    run_id=run.id if run else None,
                    project_slug=safe_display_label(run.project_slug) if run else None,
                    owner_id=owner_id,
                    source_reference=f"task:{task.id}",
                    association_status="verified" if run else "not_recorded",
                ),
                source_references=tuple(sources),
                source_watermarks=tuple(watermarks),
                inputs=tuple(inputs),
                environment=tuple(environment),
                execution_steps=tuple(steps),
                tool_calls=tool_calls,
                quality_gates=gates,
                artifacts=projection.artifacts,
                provenance=tuple(provenance),
                reproducibility=ReproducibilityEvidence(
                    blockers=("input_lineage", "runtime_environment", "scientific_comparison"),
                    source=reproducibility_source,
                ),
                evidence_coverage=EvidenceCoverage(**counts),
                warnings=tuple(sorted(set(warnings + list(projection.warnings)))),
                missing_evidence=tuple(missing),
                capture_started_at=started,
                capture_finished_at=finished,
            )
        )
