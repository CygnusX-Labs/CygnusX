"""Owner/project-scoped read projections; no client-supplied verification facts."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from cygnusx.api.deps import CurrentJwtUserId, CurrentUserId, DbSession
from cygnusx.application.schemas.research_delivery import ResearchProvenance
from cygnusx.application.services.research_provenance_service import (
    ResearchProvenanceService,
    require_research_read,
)


async def read_enabled() -> None:
    require_research_read()


router = APIRouter(dependencies=[Depends(read_enabled)])


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
