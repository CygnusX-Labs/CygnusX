"""Read-only grounding and actual statistical-cell retrieval, never generated numbers."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from cygnusx.api.deps import CurrentUserId, DbSession
from cygnusx.api.v1.research_plans import enabled
from cygnusx.application.schemas.research_claims import (
    ArtifactCellRequest,
    ClaimAssessment,
    ClaimDraft,
)
from cygnusx.application.services.research_claim_service import ResearchClaimService

router = APIRouter(
    prefix="/projects/{project_id}/research-evidence", dependencies=[Depends(enabled)]
)


@router.post("/tasks/{task_id}/claims", response_model=ClaimAssessment)
async def assess(
    project_id: UUID,
    task_id: UUID,
    request: ClaimDraft,
    user: CurrentUserId,
    db: DbSession,
) -> ClaimAssessment:
    return await ResearchClaimService(db).assessment(UUID(user), project_id, task_id, request)


@router.post("/artifact-cells")
async def cell(
    project_id: UUID,
    request: ArtifactCellRequest,
    user: CurrentUserId,
    db: DbSession,
) -> dict[str, Any]:
    return await ResearchClaimService(db).cell(UUID(user), project_id, request)
