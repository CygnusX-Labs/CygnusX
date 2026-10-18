"""Owner/project-scoped read projections; no client-supplied verification facts."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from cygnusx.api.deps import CurrentJwtUserId, CurrentUserId, DbSession
from cygnusx.application.schemas.project_delivery import (
    CreateProjectExport,
    ExportSelection,
    ProjectExportStatus,
)
from cygnusx.application.schemas.research_delivery import ResearchProvenance
from cygnusx.application.services.research_provenance_service import (
    ResearchProvenanceService,
    require_research_read,
)


async def read_enabled() -> None:
    require_research_read()


router = APIRouter(dependencies=[Depends(read_enabled)])


@router.get("/projects/{project_id}/delivery-inventory")
async def delivery_inventory(
    project_id: UUID, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

    return await ProjectDeliveryService(db).inventory(UUID(user), project_id)


@router.post("/projects/{project_id}/exports/prepare")
async def prepare_project_export(
    project_id: UUID, selection: ExportSelection, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

    manifest = await ProjectDeliveryService(db).prepare(UUID(user), project_id, selection)
    return {
        "manifest": manifest.model_dump(mode="json"),
        "manifest_digest": manifest.content_digest(),
    }


@router.post("/projects/{project_id}/exports", response_model=ProjectExportStatus)
async def create_project_export(
    project_id: UUID, request: CreateProjectExport, user: CurrentJwtUserId, db: DbSession
) -> ProjectExportStatus:
    from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

    service = ProjectDeliveryService(db)
    return service.status(await service.create(UUID(user), project_id, request))


@router.get("/projects/{project_id}/exports/{job_id}", response_model=ProjectExportStatus)
async def project_export_status(
    project_id: UUID, job_id: UUID, user: CurrentUserId, db: DbSession
) -> ProjectExportStatus:
    from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

    service = ProjectDeliveryService(db)
    return service.status(await service.job(UUID(user), project_id, job_id))


@router.post("/projects/{project_id}/exports/{job_id}/retry", response_model=ProjectExportStatus)
async def retry_project_export(
    project_id: UUID, job_id: UUID, user: CurrentJwtUserId, db: DbSession
) -> ProjectExportStatus:
    from cygnusx.application.services.project_delivery_service import (
        ProjectDeliveryService,
        dispatch_export,
        export_enabled,
    )
    from cygnusx.core.exceptions import ConflictError

    export_enabled()
    service = ProjectDeliveryService(db)
    await service.authorize(UUID(user), project_id, lock=True)
    job = await service.job(UUID(user), project_id, job_id)
    if job.status != "failed" or not job.retryable:
        raise ConflictError("Export is not retryable")
    job.status = "queued"
    await db.commit()
    await dispatch_export(job.id)
    return service.status(job)


@router.get("/projects/{project_id}/exports/{job_id}/download")
async def download_project_export(
    project_id: UUID, job_id: UUID, user: CurrentJwtUserId, db: DbSession
) -> Response:
    from cygnusx.application.services.project_delivery_service import ProjectDeliveryService

    content = await ProjectDeliveryService(db).download(UUID(user), project_id, job_id)
    import hashlib

    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="project-delivery.zip"',
            "X-Content-SHA256": hashlib.sha256(content).hexdigest(),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/projects/{project_id}/research-delivery")
async def project_delivery(project_id: UUID, user: CurrentUserId, db: DbSession) -> dict[str, Any]:
    return await ResearchProvenanceService(db).project(UUID(user), project_id)


@router.get("/tasks/{task_id}/provenance", response_model=ResearchProvenance)
async def task_provenance(task_id: UUID, user: CurrentUserId, db: DbSession) -> ResearchProvenance:
    return await ResearchProvenanceService(db).task(UUID(user), task_id)


@router.get("/reports/{report_id}/provenance", response_model=ResearchProvenance)
async def report_provenance(
    report_id: UUID, user: CurrentUserId, db: DbSession
) -> ResearchProvenance:
    return await ResearchProvenanceService(db).report(UUID(user), report_id)


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    repair_reports: bool = False


@router.post("/tasks/{task_id}/research-delivery/reconcile", response_model=ResearchProvenance)
async def reconcile_delivery(
    task_id: UUID, request: ReconcileRequest, user: CurrentJwtUserId, db: DbSession
) -> ResearchProvenance:
    from cygnusx.application.services.reproducible_report_service import ReproducibleReportService

    service = ResearchProvenanceService(db)
    graph = await service.reconcile(UUID(user), task_id)
    await db.commit()
    if request.repair_reports and graph.result_observation_id is not None:
        await ReproducibleReportService(db).enqueue(user, task_id, request_key=request.request_key)
        if graph.flow.get("id") == "counts_deg" and graph.compute_state in {"success", "completed"}:
            await ReproducibleReportService(db).enqueue(
                user, task_id, request_key=request.request_key, scientific=True
            )
    return await service.task(UUID(user), task_id)
