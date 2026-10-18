"""Read-only M0-bound claim capture, shared by prepare and create revalidation."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.claim_provenance import ClaimProvenanceRequest
from cygnusx.application.schemas.project_delivery import ProjectDeliveryManifest
from cygnusx.application.schemas.project_report import (
    FrozenProjectClaims,
    PrepareProjectReport,
    ProjectReportSource,
)
from cygnusx.application.services.project_delivery_service import ProjectDeliveryService
from cygnusx.application.services.research_claim_service import ResearchClaimService
from cygnusx.core.exceptions import ConflictError, NotFoundError
from cygnusx.infrastructure.database.models.project_export import ProjectExportJobModel


class ProjectReportSelectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def prepare(
        self, owner: UUID, project: UUID, request: PrepareProjectReport
    ) -> ProjectReportSource:
        delivery = ProjectDeliveryService(self.db)
        await delivery.authorize(owner, project)
        # Report read/prepare does not borrow the export write flag. No dispatch or writes.
        job = await self.db.get(
            ProjectExportJobModel, request.source_manifest_job_id, populate_existing=True
        )
        if not job or job.user_id != owner or job.project_id != project or job.status != "ready":
            raise NotFoundError("Published source manifest unavailable")
        manifest = ProjectDeliveryManifest.model_validate(job.manifest)
        if (manifest.owner_id, manifest.project_id, manifest.content_digest()) != (
            owner,
            project,
            job.manifest_digest,
        ):
            raise ConflictError("Frozen source manifest mismatch", code="REPORT_DRIFT")
        await delivery.validate_associations(manifest)
        reports = {
            r.id: r
            for r in manifest.references
            if r.kind == "report" and r.disposition == "reference_only"
        }
        files = {
            (f.task_id, f.source_id): f for f in manifest.files if f.source_kind == "file_record"
        }
        captured = []
        for cell in request.claims:
            if cell.task_id not in manifest.selection.task_ids:
                raise NotFoundError("Selected source unavailable in M0")
            file = files.get((cell.task_id, cell.file_record_id))
            if file is None:
                raise NotFoundError("Selected source bytes not included in M0")
            report = reports.get(cell.source_report_id) if cell.source_report_id else None
            if cell.source_report_id and (report is None or report.task_id != cell.task_id):
                raise NotFoundError("Selected report unavailable in M0")
            claim = await ResearchClaimService(self.db).provenance(
                owner, project, ClaimProvenanceRequest(**cell.model_dump())
            )
            task_refs = [
                r for r in manifest.references if r.kind == "task" and r.id == cell.task_id
            ]
            observation_refs = {
                r.id
                for r in manifest.references
                if r.kind == "result_observation" and r.task_id == cell.task_id
            }
            if len(task_refs) != 1 or (claim.dataset_version_id, claim.analysis_link_id) != (
                task_refs[0].dataset_version_id,
                task_refs[0].analysis_link_id,
            ):
                raise ConflictError(
                    "Selected dataset binding changed since M0", code="REPORT_DRIFT"
                )
            # An explicitly selected historical report is checked against its frozen
            # report reference below. A report-less selection must use M0's observation.
            if report is None and claim.result_observation_id not in observation_refs:
                raise ConflictError("Selected observation changed since M0", code="REPORT_DRIFT")
            if claim.file_sha256 != file.sha256 or (
                report is not None
                and (
                    claim.report_version != report.version
                    or claim.report_snapshot_id != report.snapshot_id
                    or claim.result_observation_id != report.result_observation_id
                )
            ):
                raise ConflictError("Selected evidence changed since M0", code="REPORT_DRIFT")
            captured.append(claim)
        selection = FrozenProjectClaims(claims=tuple(sorted(captured, key=lambda c: c.claim_id)))
        return ProjectReportSource(
            owner_id=owner,
            project_id=project,
            source_manifest_job_id=job.id,
            source_manifest_digest=job.manifest_digest,
            manifest=manifest,
            selection=selection,
            selection_digest=selection.content_digest(),
            format=request.format,
        )

    async def confirm(
        self, owner: UUID, project: UUID, request: PrepareProjectReport, expected: str
    ) -> ProjectReportSource:
        source = await self.prepare(owner, project, request)
        if source.content_digest() != expected:
            raise ConflictError("Report source changed; prepare again", code="REPORT_DRIFT")
        return source
