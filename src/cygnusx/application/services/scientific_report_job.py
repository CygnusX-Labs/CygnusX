"""Independent counts BioReport job. Reads completed outputs; never invokes a workflow."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.report_delivery import BioReportRenderRequest
from cygnusx.application.schemas.research_delivery import ResearchArtifact
from cygnusx.application.services.bioreport_adapter import BioReportAdapter
from cygnusx.application.services.file_service import ensure_directory_chain
from cygnusx.application.services.report_archive import publish_archive
from cygnusx.application.services.report_service import ReportService
from cygnusx.application.services.report_snapshot_builder import ReportSnapshotBuilder
from cygnusx.application.services.report_snapshot_sources import DatabaseTaskEvidenceSource
from cygnusx.application.services.research_provenance_service import (
    ResearchProvenanceService,
    require_research_write,
)
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, ValidationError
from cygnusx.domain.dataset.validation import open_owned_file
from cygnusx.domain.file.value_objects import FileSource
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.report import (
    ReportGenerationJobModel,
    ReportSnapshotModel,
)
from cygnusx.infrastructure.database.models.result_observation import ResultObservationModel
from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend
from cygnusx.infrastructure.storage.file_registry import FileRegistry


def render_counts(
    scoped_inputs: dict[str, bytes], output: Path, request: BioReportRenderRequest
) -> bytes:
    """Only the repository-owned template and copied verified files enter BioReport."""
    for name, content in scoped_inputs.items():
        (output / name).write_bytes(content)
    template = Path(__file__).resolve().parents[4] / "pipelines/CountsDEGFlow/report/counts.qmd"
    config = {
        "report": {
            "type": "counts-deg",
            "title": "Counts-only differential expression",
            "modules": ["custom.counts"],
            "module_definitions": {
                "custom.counts": {
                    "path": str(template),
                    "title": "Counts-only results",
                    "required_inputs": ["deg", "sample_qc"],
                }
            },
        },
        "input_files": {"data_dir": str(output), "deg": "deg.tsv", "sample_qc": "sample_qc.tsv"},
        "ai": {"enabled": False},
    }
    config_path = output / "report-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    rendered = BioReportAdapter(
        timeout_seconds=300, python_executable=get_settings().research_report_python_executable
    ).render(
        request.model_copy(
            update={
                "scientific_report_source": str(output / "not-rendered.html"),
                "report_config": str(config_path),
            }
        ),
        output / "rendered",
    )
    BioReportAdapter.validate_html_dependencies(rendered.output)
    content = rendered.output.read_bytes()
    if len(content) > get_settings().research_artifact_max_bytes:
        raise ValidationError("Scientific report exceeds capture budget")
    return content


async def run_scientific_report(db: AsyncSession, job: ReportGenerationJobModel) -> None:
    require_research_write()
    service = ResearchProvenanceService(db)
    task, _ = await service.task_scope(job.user_id, job.task_id)
    if task.flow_id != "counts_deg" or task.status not in {"success", "completed"}:
        raise ConflictError("Scientific report requires a completed counts analysis")
    if job.attempt_count >= get_settings().report_generation_max_attempts:
        job.status = "failed"
        job.error_code = "retry_exhausted"
        job.retryable = False
        await db.commit()
        return
    job.attempt_count += 1
    job.status = "collecting"
    await db.commit()
    graph = await service.task(job.user_id, job.task_id, include_reports=False)
    if (
        graph.input_integrity != "VERIFIED"
        or graph.result_integrity != "VERIFIED"
        or graph.result_observation_id is None
    ):
        raise ConflictError("Verified input/result observation required")
    observation = await db.get(ResultObservationModel, graph.result_observation_id)
    if observation is None:
        raise ConflictError("Result observation missing")
    if job.snapshot_id is None:
        snapshot = await ReportSnapshotBuilder(
            DatabaseTaskEvidenceSource(db), factory=get_path_factory()
        ).build(job.user_id, job.task_id)
        row = (
            await db.execute(
                select(ReportSnapshotModel).where(
                    ReportSnapshotModel.user_id == job.user_id,
                    ReportSnapshotModel.task_id == job.task_id,
                    ReportSnapshotModel.snapshot_digest == snapshot.snapshot_digest,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ReportSnapshotModel(
                id=uuid4(),
                task_id=job.task_id,
                user_id=job.user_id,
                run_id=snapshot.source_execution.run_id,
                schema_version=snapshot.schema_version,
                snapshot_digest=snapshot.snapshot_digest,
                payload=snapshot.model_dump(mode="json"),
                captured_at=snapshot.capture_finished_at,
            )
            db.add(row)
            await db.flush()
        job.snapshot_id = row.id
    else:
        row = await db.get(ReportSnapshotModel, job.snapshot_id)
        if row is None:
            raise ConflictError("Scientific snapshot missing")
        from cygnusx.application.services.reproducible_report_service import validate_snapshot_row

        snapshot = validate_snapshot_row(row)
        if (
            snapshot.research_delivery is None
            or snapshot.research_delivery.result_observation_id != observation.id
        ):
            raise ConflictError("Retry input changed; request a new report version")
    factory = get_path_factory()
    inputs = {}
    for path, asset in service._verified_paths:
        if path.name in {"deg.tsv", "sample_qc.tsv"} and asset.integrity == "VERIFIED":
            with open_owned_file(path, factory.user_root(str(job.user_id))) as stream:
                content = stream.read(get_settings().research_artifact_max_bytes + 1)
            if hashlib.sha256(content).hexdigest() != asset.sha256:
                raise ConflictError("Scientific input changed during capture")
            inputs[path.name] = content
    if set(inputs) != {"deg.tsv", "sample_qc.tsv"}:
        raise ValidationError("Counts scientific report inputs missing")
    job.status = "rendering"
    await db.commit()
    with tempfile.TemporaryDirectory(prefix="cygnusx-counts-report-") as temporary:
        request = BioReportRenderRequest(
            task_id=job.task_id,
            report_snapshot_id=row.id,
            report_snapshot_digest=row.snapshot_digest,
            scientific_report_source="",
            report_config="",
            output_format="html",
            renderer_version="NOT_ATTESTED",
            template_version="scientific-counts-v1",
        )
        content = await asyncio.to_thread(render_counts, inputs, Path(temporary), request)
    await service.task_scope(job.user_id, job.task_id)
    project = await db.get(ProjectModel, graph.project_id)
    if project is None:
        raise ConflictError("Project missing")
    # Each attempt has a fresh path; never overwrite an archived report or snapshot.
    run_dir = factory.create_project_run_dir(str(job.user_id), project.slug, "scientific-report")
    target = run_dir / "output" / "index.html"
    relative = factory.relative_to_root(target)
    job.status = "publishing"
    job.archive_path = relative
    await db.commit()
    await publish_archive(get_storage_backend(), factory, relative, content)
    directory = target.parent.relative_to(factory.user_root(str(job.user_id))).as_posix()
    await ensure_directory_chain(db, job.user_id, directory)
    sha = hashlib.sha256(content).hexdigest()
    record = await FileRegistry(db).register(
        job.user_id,
        target,
        source=FileSource.PIPELINE,
        task_id=job.task_id,
        directory=directory,
        checksum=sha,
    )
    report = await ReportService(db).register_verified_scientific_result(
        job.user_id,
        task,
        observation,
        [
            (
                target,
                ResearchArtifact(
                    file_record_id=record.id,
                    logical_name="scientific-report",
                    category="report",
                    size=len(content),
                    sha256=sha,
                    integrity="VERIFIED",
                ),
            )
        ],
    )
    if report is None:
        raise ConflictError("Scientific report registration incomplete")
    if report.snapshot_id is None:
        report.snapshot_id = row.id
        report.template_version = job.template_version
        report.evidence_partial = True
    job.report_id = report.id
    job.status = "ready"
    job.retryable = False
    job.error_code = None
    job.error_message = ""
    job.finished_at = datetime.now(UTC)
    await db.commit()
