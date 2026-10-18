"""Durable project-report identity and human-confirmed source binding."""

import asyncio
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.project_report import (
    CreateProjectReport,
    PrepareProjectReport,
    ProjectReportSource,
)
from cygnusx.application.services.project_report_selection import ProjectReportSelectionService
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, DependencyUnavailableError, NotFoundError
from cygnusx.infrastructure.database.models.project_report import (
    ProjectReportJobModel,
    ProjectReportRequestModel,
)


def project_report_write_enabled() -> None:
    if not get_settings().project_report_write_enabled:
        raise DependencyUnavailableError(
            "Project scientific report generation is not admitted", code="REPORT_GATE_CLOSED"
        )


class ProjectReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.selection = ProjectReportSelectionService(db)

    async def prepare(
        self, owner: UUID, project: UUID, request: PrepareProjectReport
    ) -> ProjectReportSource:
        return await self.selection.prepare(owner, project, request)

    async def create(
        self, owner: UUID, project: UUID, request: CreateProjectReport
    ) -> ProjectReportJobModel:
        project_report_write_enabled()
        from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

        await ProjectDeliveryService(self.db).authorize(owner, project, lock=True)
        source = await self.selection.confirm(owner, project, request, request.prepare_digest)
        source_digest = source.content_digest()
        existing: ProjectReportJobModel | None = await self.db.scalar(
            select(ProjectReportJobModel)
            .join(
                ProjectReportRequestModel,
                ProjectReportRequestModel.job_id == ProjectReportJobModel.id,
            )
            .where(
                ProjectReportRequestModel.user_id == owner,
                ProjectReportRequestModel.project_id == project,
                ProjectReportRequestModel.request_key == str(request.request_key),
            )
        )
        if existing is not None:
            if existing.source_digest != source_digest:
                raise ConflictError(
                    "Request key already binds another report source", code="REPORT_DRIFT"
                )
            return existing
        existing = await self.db.scalar(
            select(ProjectReportJobModel).where(
                ProjectReportJobModel.user_id == owner,
                ProjectReportJobModel.project_id == project,
                ProjectReportJobModel.source_digest == source_digest,
            )
        )
        if existing is not None:
            self.db.add(
                ProjectReportRequestModel(
                    user_id=owner,
                    project_id=project,
                    request_key=str(request.request_key),
                    job_id=existing.id,
                )
            )
            await self.db.commit()
            return existing
        previous = await self.db.scalar(
            select(ProjectReportJobModel)
            .where(
                ProjectReportJobModel.user_id == owner,
                ProjectReportJobModel.project_id == project,
                ProjectReportJobModel.source_manifest_job_id == source.source_manifest_job_id,
            )
            .order_by(ProjectReportJobModel.version.desc())
            .limit(1)
        )
        job = ProjectReportJobModel(
            user_id=owner,
            project_id=project,
            source_manifest_job_id=source.source_manifest_job_id,
            request_key=str(request.request_key),
            source_digest=source_digest,
            source_snapshot=source.model_dump(mode="json"),
            status="queued",
            parent_id=previous.id if previous else None,
            version=previous.version + 1 if previous else 1,
            attempt_count=0,
            pdf_status="PDF_NOT_GENERATED",
        )
        self.db.add(job)
        await self.db.flush()
        self.db.add(
            ProjectReportRequestModel(
                user_id=owner,
                project_id=project,
                request_key=str(request.request_key),
                job_id=job.id,
            )
        )
        await self.db.commit()
        await dispatch_project_report(job.id)
        return job

    async def status(self, owner: UUID, project: UUID, job_id: UUID) -> ProjectReportJobModel:
        from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

        await ProjectDeliveryService(self.db).authorize(owner, project)
        job = await self.db.get(ProjectReportJobModel, job_id, populate_existing=True)
        if job is None or job.user_id != owner or job.project_id != project:
            raise NotFoundError("Project report unavailable")
        source = ProjectReportSource.model_validate(job.source_snapshot)
        if (
            source.owner_id,
            source.project_id,
            source.source_manifest_job_id,
            source.content_digest(),
        ) != (owner, project, job.source_manifest_job_id, job.source_digest):
            raise ConflictError("Frozen report identity changed", code="REPORT_DRIFT")
        return job

    async def download(
        self, owner: UUID, project: UUID, job_id: UUID, file_type: str = "html"
    ) -> bytes:
        import hashlib

        from cygnusx.application.services.project_delivery_service import read_bounded
        from cygnusx.infrastructure.database.models.file import FileRecordModel
        from cygnusx.infrastructure.database.models.report import ReportFileModel
        from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend

        job = await self.status(owner, project, job_id)
        if file_type not in {"html", "pdf"} or job.status != "ready":
            raise NotFoundError("Published project report unavailable")
        record_id = job.html_file_record_id if file_type == "html" else job.pdf_file_record_id
        sha = job.html_sha256 if file_type == "html" else job.pdf_sha256
        size = job.html_size if file_type == "html" else job.pdf_size
        if not record_id or not sha or not size:
            raise NotFoundError("Requested report format not generated")
        record = await self.db.get(FileRecordModel, record_id, populate_existing=True)
        file = await self.db.scalar(
            select(ReportFileModel).where(
                ReportFileModel.project_report_job_id == job.id,
                ReportFileModel.file_record_id == record_id,
                ReportFileModel.type == file_type,
            )
        )
        factory, backend = get_path_factory(), get_storage_backend()
        if (
            record is None
            or record.user_id != owner
            or record.owner_scope != "personal"
            or record.task_id is not None
            or record.status != "active"
            or record.lifecycle_status != "active"
            or record.source != "report"
            or (record.checksum, record.size) != (sha, size)
            or file is None
            or (file.sha256, file.size) != (sha, size)
            or file.path != str(factory.data_root / record.storage_path)
        ):
            raise NotFoundError("Project report file unavailable")
        limit = get_settings().project_export_file_max_bytes
        if size > limit:
            raise ConflictError("Project report exceeds file budget")
        path = factory.data_root / record.storage_path
        if ".." in path.parts or not path.is_relative_to(factory.user_root(str(owner))):
            raise NotFoundError("Project report file unavailable")
        if backend.name == "local":
            content = read_bounded(path, owner, limit)
        else:
            content = await backend.read(record.storage_path, limit=limit + 1)
        if len(content) != size or hashlib.sha256(content).hexdigest() != sha:
            raise ConflictError("Project report bytes changed", code="REPORT_DRIFT")
        await self.status(owner, project, job_id)
        return content


async def dispatch_project_report(job_id: UUID) -> None:
    from cygnusx.infrastructure.celery_app.tasks.project_reports import generate_project_report

    try:
        await asyncio.to_thread(
            generate_project_report.apply_async, args=[str(job_id)], retry=False
        )
    except Exception:
        logger.warning("Project report remains queued for reconciliation: {}", job_id)
