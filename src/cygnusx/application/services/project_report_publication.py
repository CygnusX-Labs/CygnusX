"""Publish frozen project HTML using the existing archive and report services."""

import asyncio
import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.project_report import (
    PrepareProjectReport,
    ProjectClaimSelection,
    ProjectReportSource,
)
from cygnusx.application.services.bioreport_adapter import BioReportAdapter
from cygnusx.application.services.project_delivery_service import ProjectDeliveryService
from cygnusx.application.services.project_report_renderer import render_project_report
from cygnusx.application.services.project_report_selection import ProjectReportSelectionService
from cygnusx.application.services.project_report_service import project_report_write_enabled
from cygnusx.application.services.report_archive import publish_archive
from cygnusx.application.services.report_audit_pdf_renderer import AuditPdfRenderError
from cygnusx.application.services.report_service import ReportService
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import (
    ConflictError,
    NotFoundError,
    QuotaExceededError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.file import FileRecordModel
from cygnusx.infrastructure.database.models.project_report import ProjectReportJobModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend


async def run_project_report(db: AsyncSession, job_id: UUID) -> None:
    """Caller holds the durable per-job worker lock across stage commits."""
    project_report_write_enabled()
    job = await db.get(ProjectReportJobModel, job_id, populate_existing=True)
    if job is None:
        raise NotFoundError("Project report unavailable")
    delivery = ProjectDeliveryService(db)
    project = await delivery.authorize(job.user_id, job.project_id)
    source = ProjectReportSource.model_validate(job.source_snapshot)
    if (
        source.owner_id,
        source.project_id,
        source.source_manifest_job_id,
        source.content_digest(),
    ) != (job.user_id, job.project_id, job.source_manifest_job_id, job.source_digest):
        raise ConflictError("Project report frozen identity mismatch", code="REPORT_DRIFT")
    if job.status == "ready":
        return
    if job.status == "failed" and not job.retryable:
        return
    if job.attempt_count >= get_settings().report_generation_max_attempts:
        raise ConflictError("Project report retry budget exhausted")
    request = PrepareProjectReport(
        source_manifest_job_id=source.source_manifest_job_id,
        format=source.format,
        claims=tuple(
            ProjectClaimSelection(
                task_id=c.task_id,
                file_record_id=c.file_record_id,
                feature_id=c.row_identifier,
                column=c.column_identifier,
                source_report_id=c.source_report_id,
            )
            for c in source.selection.claims
        ),
    )
    job.status = "validating"
    job.retryable, job.error_code = False, None
    job.attempt_count += 1
    await db.commit()
    await ProjectReportSelectionService(db).confirm(
        job.user_id, job.project_id, request, job.source_digest
    )
    job.status = "rendering"
    await db.commit()
    adapter = BioReportAdapter(timeout_seconds=300)
    content = adapter.render_project_document(render_project_report(source))
    pdf = None
    if source.format == "html_pdf" and get_settings().project_report_pdf_enabled:
        try:
            pdf = await asyncio.to_thread(
                adapter.render_project_document, content, output_format="pdf"
            )
            if (
                not pdf.startswith(b"%PDF-")
                or len(pdf) > get_settings().project_export_file_max_bytes
            ):
                pdf = None
        except AuditPdfRenderError:
            pdf = None
    if len(content) > get_settings().project_export_file_max_bytes:
        raise ValidationError("Project report file budget exceeded", code="REPORT_LIMIT")
    factory, backend = get_path_factory(), get_storage_backend()
    if job.archive_path is None:
        run = factory.create_project_run_dir(str(job.user_id), project.slug, "project-report")
        job.archive_path = (run / "output/index.html").relative_to(factory.data_root).as_posix()
    job.status = "publishing"
    await db.commit()
    await ProjectReportSelectionService(db).confirm(
        job.user_id, job.project_id, request, job.source_digest
    )
    await db.execute(select(UserModel.id).where(UserModel.id == job.user_id).with_for_update())
    user = await db.get(UserModel, job.user_id, populate_existing=True)
    existing_record = await db.scalar(
        select(FileRecordModel).where(
            FileRecordModel.user_id == job.user_id, FileRecordModel.storage_path == job.archive_path
        )
    )
    additional = 0 if existing_record else len(content)
    if existing_record and (existing_record.checksum, existing_record.size) != (
        hashlib.sha256(content).hexdigest(),
        len(content),
    ):
        raise ConflictError("Published project report cannot be replaced")
    if pdf:
        additional += len(pdf)
    if user is None or user.used_storage + additional > user.storage_quota:
        raise QuotaExceededError("Project report storage quota exceeded")
    await publish_archive(backend, factory, job.archive_path, content)
    file = await ReportService(db, backend=backend).register_project_report_file(
        owner=job.user_id,
        project=job.project_id,
        job_id=job.id,
        archive_path=job.archive_path,
        content=content,
        file_type="html",
    )
    job.html_file_record_id, job.html_sha256, job.html_size = (
        file.file_record_id,
        file.sha256,
        file.size,
    )
    job.pdf_status = "PDF_NOT_GENERATED"
    if pdf:
        pdf_path = str(job.archive_path).removesuffix("index.html") + "index.pdf"
        await publish_archive(backend, factory, pdf_path, pdf)
        pdf_file = await ReportService(db, backend=backend).register_project_report_file(
            owner=job.user_id,
            project=job.project_id,
            job_id=job.id,
            archive_path=pdf_path,
            content=pdf,
            file_type="pdf",
        )
        job.pdf_file_record_id, job.pdf_sha256, job.pdf_size = (
            pdf_file.file_record_id,
            pdf_file.sha256,
            pdf_file.size,
        )
        job.pdf_status = "PDF_GENERATED"
    user.used_storage += additional
    job.status = "ready"
    await db.commit()
