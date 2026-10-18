"""Explicit M0 -> published report -> M1; never modifies a frozen v1 manifest."""

import hashlib
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from cygnusx.application.schemas.project_delivery import (
    DeliveryFile,
    ExportSelectionV2,
    ProjectDeliveryManifest,
    ProjectDeliveryManifestV2,
    ProjectReportArtifact,
)
from cygnusx.core.exceptions import ConflictError, NotFoundError
from cygnusx.infrastructure.database.models.report import ReportFileModel

if TYPE_CHECKING:
    from cygnusx.application.services.project_delivery_service import ProjectDeliveryService


async def prepare_report_delivery(
    service: "ProjectDeliveryService", owner: UUID, project: UUID, selection: ExportSelectionV2
) -> ProjectDeliveryManifestV2:
    from cygnusx.application.services.project_report_service import ProjectReportService

    m0 = await service.job(owner, project, selection.source_manifest_job_id)
    if m0.status != "ready":
        raise NotFoundError("Source delivery is not ready")
    frozen = ProjectDeliveryManifest.model_validate(m0.manifest)
    if frozen.content_digest() != m0.manifest_digest:
        raise ConflictError("Source delivery drifted")
    if (selection.kind, selection.task_ids, selection.report_ids) != (
        frozen.selection.kind,
        frozen.selection.task_ids,
        frozen.selection.report_ids,
    ):
        raise ConflictError("M1 must preserve the explicitly selected M0 scope")
    await service.validate_associations(frozen)
    files = list(frozen.files)
    # M0 retains its historical verifier bytes. M1 explicitly freezes the current
    # verifier instead of assuming the deployment still has M0's source revision.
    from cygnusx.application.services.project_delivery_service import verifier_bytes

    verifier = verifier_bytes()
    files = [
        f.model_copy(update={"size": len(verifier), "sha256": hashlib.sha256(verifier).hexdigest()})
        if f.source_kind == "verifier" else f
        for f in files
    ]
    reports = ProjectReportService(service.db)
    gaps = list(frozen.gaps)
    artifacts = []
    for report_id in sorted(selection.project_report_job_ids, key=str):
        job = await reports.status(owner, project, report_id)
        if job.status != "ready" or job.source_manifest_job_id != m0.id:
            raise NotFoundError("Published report does not belong to M0")
        if job.source_snapshot.get("source_manifest_digest") != m0.manifest_digest:
            raise ConflictError("Published report source drifted")
        for kind in ("html", "pdf"):
            record_id = job.html_file_record_id if kind == "html" else job.pdf_file_record_id
            if not record_id:
                if kind == "pdf":
                    gaps.append(f"PROJECT_REPORT:{job.id}:PDF_NOT_GENERATED")
                continue
            content = await reports.download(owner, project, job.id, kind)
            file = await service.db.scalar(
                select(ReportFileModel).where(
                    ReportFileModel.project_report_job_id == job.id,
                    ReportFileModel.type == kind,
                    ReportFileModel.file_record_id == record_id,
                )
            )
            if file is None:
                raise NotFoundError("Published report registration unavailable")
            files.append(
                DeliveryFile(
                    path=f"project_reports/{job.id}/report.{kind}",
                    source_kind="report_file",
                    source_id=file.id,
                    size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                )
            )
            artifacts.append(
                ProjectReportArtifact(
                    project_report_job_id=job.id,
                    source_digest=job.source_digest,
                    report_file_id=file.id,
                    file_record_id=record_id,
                    format=kind,
                    sha256=hashlib.sha256(content).hexdigest(),
                    size=len(content),
                )
            )
    service.budget(files)
    return ProjectDeliveryManifestV2(
        owner_id=owner,
        project_id=project,
        selection=selection,
        source_manifest_digest=m0.manifest_digest,
        files=tuple(files),
        report_artifacts=tuple(artifacts),
        references=frozen.references,
        gaps=tuple(gaps),
        evidence_status="partial" if gaps else frozen.evidence_status,
    )


async def validate_report_delivery(
    service: "ProjectDeliveryService", manifest: ProjectDeliveryManifestV2
) -> None:
    current = await prepare_report_delivery(
        service, manifest.owner_id, manifest.project_id, manifest.selection
    )
    if current.content_digest() != manifest.content_digest():
        raise ConflictError("Frozen M1 report identity changed", code="EXPORT_DRIFT")
