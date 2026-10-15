"""Independent, owner-scoped capture → immutable HTML → existing report centre."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.report import ReportJobResponse, ReportSnapshotResponse
from cygnusx.application.schemas.report_snapshot import ReportSnapshot
from cygnusx.application.services.report_archive import publish_archive, read_archive
from cygnusx.application.services.report_audit_pdf_renderer import (
    AuditPdfRenderError,
    render_audit_pdf,
)
from cygnusx.application.services.report_audit_renderer import TEMPLATE_VERSION, render_audit_report
from cygnusx.application.services.report_snapshot_builder import ReportSnapshotBuilder
from cygnusx.application.services.report_snapshot_sources import DatabaseTaskEvidenceSource
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.report import (
    ReportGenerationJobModel,
    ReportModel,
    ReportSnapshotModel,
)
from cygnusx.infrastructure.database.models.run import RunModel
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend

ACTIVE_STATUSES = ("queued", "collecting", "rendering", "publishing")


def _job_response(job: ReportGenerationJobModel) -> ReportJobResponse:
    return ReportJobResponse.model_validate(job, from_attributes=True)


def owner_uuid(user_id: str | UUID) -> UUID:
    return user_id if isinstance(user_id, UUID) else UUID(user_id)


def validate_snapshot_row(row: ReportSnapshotModel) -> ReportSnapshot:
    snapshot = ReportSnapshot.model_validate(row.payload)
    if (
        snapshot.snapshot_digest != row.snapshot_digest
        or snapshot.schema_version != row.schema_version
        or snapshot.source_execution.owner_id != row.user_id
        or snapshot.source_execution.task_id != row.task_id
        or snapshot.source_execution.run_id != row.run_id
    ):
        raise ValueError("Persisted snapshot identity mismatch")
    return snapshot


async def dispatch_report_job(job_id: UUID) -> None:
    """Best effort fast dispatch; the committed queued row is a recoverable outbox."""
    from cygnusx.infrastructure.celery_app.tasks.reports import generate_reproducible_report

    try:
        generate_reproducible_report.apply_async(args=[str(job_id)], retry=False)
    except Exception:
        # Do not expose broker credentials, and do not discard the durable request.
        # Beat scans queued jobs, including a crash between commit and dispatch.
        from loguru import logger

        logger.warning("Report dispatch deferred; durable job {} awaits reconciliation", job_id)


class ReproducibleReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def enqueue(
        self,
        user_id: str | UUID,
        task_id: UUID,
        run_id: UUID | None = None,
        *,
        request_key: UUID | None = None,
    ) -> ReportJobResponse:
        owner = owner_uuid(user_id)
        # Serialize requests for the same source; also protected by a partial unique index.
        task = await self.db.scalar(
            select(TaskModel)
            .where(TaskModel.id == task_id, TaskModel.user_id == owner)
            .with_for_update()
        )
        if task is None:
            raise NotFoundError("Task not found")
        if task.flow_id != "rna_seq":
            raise ValidationError("可复现报告当前仅支持 RNA-seq 任务")
        if task.status not in {"success", "completed", "failed", "cancelled"}:
            raise ConflictError("分析尚未结束，请在任务结束后生成报告")
        if run_id is not None:
            run = await self.db.scalar(
                select(RunModel).where(
                    RunModel.id == run_id,
                    RunModel.user_id == owner,
                    RunModel.task_id == task_id,
                    RunModel.flow_id == task.flow_id,
                    RunModel.confirmed_at.is_not(None),
                )
            )
            if run is None:
                raise NotFoundError("Run not found")
        key = hashlib.sha256(
            f"{owner}:{task_id}:{run_id}:{TEMPLATE_VERSION}:{request_key or uuid4()}".encode()
        ).hexdigest()
        query = select(ReportGenerationJobModel).where(
            ReportGenerationJobModel.user_id == owner,
            ReportGenerationJobModel.task_id == task_id,
            ReportGenerationJobModel.template_version == TEMPLATE_VERSION,
        )
        existing = (
            await self.db.scalar(query.where(ReportGenerationJobModel.idempotency_key == key))
            if request_key
            else None
        )
        if existing is None:
            existing = await self.db.scalar(
                query.where(ReportGenerationJobModel.status.in_(ACTIVE_STATUSES))
            )
        if existing is not None:
            response = await self.get_job(owner, existing.id)
            await self.db.commit()
            return response
        job = ReportGenerationJobModel(
            id=uuid4(),
            task_id=task_id,
            user_id=owner,
            run_id=run_id,
            idempotency_key=key,
            template_version=TEMPLATE_VERSION,
            status="queued",
            error_message="",
            evidence_partial=True,
            retryable=False,
            attempt_count=0,
        )
        self.db.add(job)
        await self.db.flush()
        response = _job_response(job)
        await self.db.commit()
        await dispatch_report_job(job.id)
        return response

    async def get_job(self, user_id: str | UUID, job_id: UUID) -> ReportJobResponse:
        job = await self._owned_job(user_id, job_id)
        response = _job_response(job)
        if job.status == "ready":
            report = await self.db.get(ReportModel, job.report_id) if job.report_id else None
            if report is None or report.user_id != job.user_id:
                return response.model_copy(
                    update={
                        "status": "failed",
                        "error_code": "report_removed",
                        "error_message": "报告记录已删除，可重新请求生成报告。",
                        "retryable": False,
                    }
                )
        return response

    async def _owned_job(self, user_id: str | UUID, job_id: UUID) -> ReportGenerationJobModel:
        job = await self.db.scalar(
            select(ReportGenerationJobModel).where(
                ReportGenerationJobModel.id == job_id,
                ReportGenerationJobModel.user_id == owner_uuid(user_id),
            )
        )
        if job is None:
            raise NotFoundError("Report job not found")
        return job

    async def retry(self, user_id: str | UUID, job_id: UUID) -> ReportJobResponse:
        job = await self._owned_job(user_id, job_id)
        # Same lock order as enqueue: Task, then job. Never lock another owner's Task.
        await self.db.scalar(
            select(TaskModel)
            .where(TaskModel.id == job.task_id, TaskModel.user_id == owner_uuid(user_id))
            .with_for_update()
        )
        await self.db.refresh(job, with_for_update=True)
        if job.status in ACTIVE_STATUSES or job.status == "ready":
            return _job_response(job)
        if not job.retryable or job.attempt_count >= get_settings().report_generation_max_attempts:
            raise ConflictError("该失败不可自动重试，请检查任务证据或联系管理员")
        active = await self.db.scalar(
            select(ReportGenerationJobModel).where(
                ReportGenerationJobModel.task_id == job.task_id,
                ReportGenerationJobModel.user_id == job.user_id,
                ReportGenerationJobModel.template_version == job.template_version,
                ReportGenerationJobModel.status.in_(ACTIVE_STATUSES),
            )
        )
        if active is not None:
            return _job_response(active)
        job.status = "queued"
        job.finished_at = None
        job.error_code = None
        job.error_message = ""
        await self.db.commit()
        await dispatch_report_job(job.id)
        return _job_response(job)

    async def get_snapshot_for_report(
        self, user_id: str | UUID, report_id: UUID
    ) -> ReportSnapshotResponse:
        owner = owner_uuid(user_id)
        snapshot = await self.db.scalar(
            select(ReportSnapshotModel)
            .join(
                ReportModel,
                ReportModel.snapshot_id == ReportSnapshotModel.id,
            )
            .where(
                ReportModel.id == report_id,
                ReportModel.user_id == owner,
                ReportSnapshotModel.user_id == owner,
                ReportModel.task_id == ReportSnapshotModel.task_id,
                ReportModel.report_kind == "reproducibility",
            )
        )
        if snapshot is None:
            raise NotFoundError("Report snapshot not found")
        try:
            validate_snapshot_row(snapshot)
        except ValueError as exc:
            raise ConflictError("报告快照完整性校验失败") from exc
        return ReportSnapshotResponse.model_validate(snapshot, from_attributes=True)


async def _transition(db: AsyncSession, job: ReportGenerationJobModel, status: str) -> None:
    job.status = status
    job.updated_at = datetime.now(UTC)
    await db.commit()


async def run_reproducible_report(db: AsyncSession, job_id: UUID) -> None:
    """Caller must hold the dedicated PostgreSQL Task advisory lock across commits."""
    job = await db.get(ReportGenerationJobModel, job_id)
    if job is None or job.status == "ready" or (job.status == "failed" and not job.retryable):
        return
    authorized_task = await db.scalar(
        select(TaskModel.id).where(
            TaskModel.id == job.task_id,
            TaskModel.user_id == job.user_id,
        )
    )
    if authorized_task is None:
        raise NotFoundError("Task not found")
    if job.attempt_count >= get_settings().report_generation_max_attempts:
        job.status = "failed"
        job.retryable = False
        job.error_code = "retry_exhausted"
        job.error_message = "报告生成重试次数已用完，请联系管理员。"
        job.finished_at = datetime.now(UTC)
        await db.commit()
        return
    other_active = await db.scalar(
        select(ReportGenerationJobModel.id).where(
            ReportGenerationJobModel.task_id == job.task_id,
            ReportGenerationJobModel.user_id == job.user_id,
            ReportGenerationJobModel.id != job.id,
            ReportGenerationJobModel.status.in_(ACTIVE_STATUSES),
        )
    )
    if job.status == "failed" and other_active is not None:
        return
    job.attempt_count += 1
    job.error_code = None
    job.error_message = ""
    job.finished_at = None
    await _transition(db, job, "collecting")
    if job.snapshot_id is None:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        snapshot = await ReportSnapshotBuilder(
            DatabaseTaskEvidenceSource(db), factory=get_path_factory()
        ).build(job.user_id, job.task_id, run_id=job.run_id)
        await db.commit()
        snapshot_model = await db.scalar(
            select(ReportSnapshotModel).where(
                ReportSnapshotModel.user_id == job.user_id,
                ReportSnapshotModel.task_id == job.task_id,
                ReportSnapshotModel.snapshot_digest == snapshot.snapshot_digest,
            )
        )
        if snapshot_model is None:
            snapshot_model = ReportSnapshotModel(
                id=uuid4(),
                task_id=job.task_id,
                user_id=job.user_id,
                run_id=snapshot.source_execution.run_id,
                schema_version=snapshot.schema_version,
                snapshot_digest=snapshot.snapshot_digest,
                payload=snapshot.model_dump(mode="json"),
                captured_at=snapshot.capture_finished_at,
            )
            db.add(snapshot_model)
            await db.flush()
        job.snapshot_id = snapshot_model.id
    else:
        snapshot_model = await db.get(ReportSnapshotModel, job.snapshot_id)
        if snapshot_model is None:
            raise ValueError("Frozen snapshot missing")
    snapshot = validate_snapshot_row(snapshot_model)
    if (
        snapshot.source_execution.owner_id != job.user_id
        or snapshot.source_execution.task_id != job.task_id
    ):
        raise ValueError("Job snapshot identity mismatch")
    job.evidence_partial = bool(snapshot.missing_evidence)
    await _transition(db, job, "rendering")
    existing = await db.scalar(
        select(ReportModel).where(
            ReportModel.user_id == job.user_id,
            ReportModel.snapshot_id == job.snapshot_id,
            ReportModel.template_version == job.template_version,
        )
    )
    if existing is not None:
        # Existing files are never silently rewritten, including deleted/modified files.
        from cygnusx.application.services.report_service import ReportService

        await ReportService(db).preview_html(existing.id, str(job.user_id))
        job.report_id = existing.id
        job.finished_at = datetime.now(UTC)
        job.retryable = False
        await _transition(db, job, "ready")
        return
    if job.template_version != TEMPLATE_VERSION:
        raise ValueError("Unsupported frozen report template version")
    html_bytes = render_audit_report(snapshot).encode("utf-8")
    sha256 = hashlib.sha256(html_bytes).hexdigest()
    pdf_bytes: bytes | None = None
    pdf_sha256: str | None = None
    try:
        pdf_bytes = await asyncio.to_thread(render_audit_pdf, html_bytes)
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    except AuditPdfRenderError:
        # HTML remains a valid execution record; the missing PDF is surfaced as
        # a partial format outcome and can be retried without recollecting facts.
        job.evidence_partial = True
    factory = get_path_factory()
    if job.archive_path is None:
        # Task names are owner supplied; use only the existing safe projection for paths.
        project = snapshot.source_execution.project_slug or "RNA-seq"
        run_dir = factory.create_project_run_dir(str(job.user_id), project, "audit-report")
        job.archive_path = factory.relative_to_root(run_dir / "output" / "index.html")
    pdf_archive_path = str(Path(job.archive_path).with_name("index.pdf"))
    await _transition(db, job, "publishing")
    # Recheck persisted paths before retrying; a DB key is not an authorization grant.
    relative = Path(job.archive_path)
    owner_root = factory.user_root(str(job.user_id)).absolute()
    if relative.is_absolute() or ".." in relative.parts or owner_root.resolve() != owner_root:
        from cygnusx.core.exceptions import AuthorizationError

        raise AuthorizationError("Unsafe report archive path")
    if not (factory.data_root / relative).resolve().is_relative_to(owner_root):
        from cygnusx.core.exceptions import AuthorizationError

        raise AuthorizationError("Report archive outside owner boundary")
    storage = get_storage_backend()
    if await storage.exists(job.archive_path):
        # Crash recovery reuses exact bytes; an incomplete write may be repaired before registration.
        published = await read_archive(storage, factory, job.archive_path)
        if hashlib.sha256(published).hexdigest() != sha256:
            await publish_archive(storage, factory, job.archive_path, html_bytes)
    else:
        await publish_archive(storage, factory, job.archive_path, html_bytes)
    published = await read_archive(storage, factory, job.archive_path)
    if len(published) != len(html_bytes) or hashlib.sha256(published).hexdigest() != sha256:
        raise OSError("Report publication integrity check failed")
    if pdf_bytes is not None and pdf_sha256 is not None:
        await publish_archive(storage, factory, pdf_archive_path, pdf_bytes)
        published_pdf = await read_archive(storage, factory, pdf_archive_path)
        if len(published_pdf) != len(pdf_bytes) or hashlib.sha256(published_pdf).hexdigest() != pdf_sha256:
            raise OSError("Audit PDF publication integrity check failed")
    from cygnusx.application.services.report_service import ReportService

    report = await ReportService(db).register_reproducibility_report(
        snapshot=snapshot,
        snapshot_id=snapshot_model.id,
        template_version=job.template_version,
        archive_path=job.archive_path,
        size=len(html_bytes),
        sha256=sha256,
        evidence_partial=job.evidence_partial,
        pdf_archive_path=pdf_archive_path if pdf_bytes is not None else None,
        pdf_size=len(pdf_bytes) if pdf_bytes is not None else None,
        pdf_sha256=pdf_sha256,
    )
    job.report_id = report.id
    job.finished_at = datetime.now(UTC)
    job.retryable = False
    await _transition(db, job, "ready")
