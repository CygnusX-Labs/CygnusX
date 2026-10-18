"""Project-scoped research intent, review and bounded read/prepare coordination."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field

from cygnusx.api.deps import CurrentJwtUserId, CurrentUserId, DbSession
from cygnusx.application.schemas.research_plan import (
    PlanInput,
    PlanPrepare,
    PlanRevision,
    ResearchPlanView,
)
from cygnusx.application.services.research_plan_service import (
    ResearchPlanService,
    require_plan_enabled,
)


async def enabled() -> None:
    require_plan_enabled()


router = APIRouter(prefix="/projects/{project_id}/research-plans", dependencies=[Depends(enabled)])


class ReviewRequest(PlanInput):
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AdvanceRequest(PlanInput):
    session_id: str = Field(min_length=1, max_length=50)


class ControlRequest(PlanInput):
    action: Literal["pause", "resume", "cancel"]


@router.get("", response_model=list[ResearchPlanView])
async def list_plans(
    project_id: UUID, user: CurrentUserId, db: DbSession
) -> list[ResearchPlanView]:
    return await ResearchPlanService(db).list(UUID(user), project_id)


@router.post("", response_model=ResearchPlanView)
async def prepare(
    project_id: UUID,
    request: PlanPrepare,
    user: CurrentUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).prepare(UUID(user), project_id, request)


@router.get("/{plan_id}", response_model=ResearchPlanView)
async def get_plan(
    project_id: UUID,
    plan_id: UUID,
    user: CurrentUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).view(UUID(user), project_id, plan_id)


@router.post("/{plan_id}/versions", response_model=ResearchPlanView)
async def revise(
    project_id: UUID,
    plan_id: UUID,
    request: PlanRevision,
    user: CurrentUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).revise(UUID(user), project_id, plan_id, request)


@router.post("/{plan_id}/review", response_model=ResearchPlanView)
async def review(
    project_id: UUID,
    plan_id: UUID,
    request: ReviewRequest,
    user: CurrentJwtUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).review(
        UUID(user), project_id, plan_id, request.expected_digest
    )


@router.post("/{plan_id}/advance", response_model=ResearchPlanView)
async def advance(
    project_id: UUID,
    plan_id: UUID,
    request: AdvanceRequest,
    user: CurrentJwtUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).advance(
        UUID(user), project_id, plan_id, request.session_id
    )


@router.post("/{plan_id}/control", response_model=ResearchPlanView)
async def control(
    project_id: UUID,
    plan_id: UUID,
    request: ControlRequest,
    user: CurrentJwtUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).control(UUID(user), project_id, plan_id, request.action)


@router.get("/{plan_id}/events")
async def events(
    project_id: UUID,
    plan_id: UUID,
    user: CurrentUserId,
    db: DbSession,
) -> list[dict[str, Any]]:
    service = ResearchPlanService(db)
    await service.view(UUID(user), project_id, plan_id)
    return (await service.owned(UUID(user), project_id, plan_id)).events


@router.post("/{plan_id}/reconcile", response_model=ResearchPlanView)
async def reconcile(
    project_id: UUID,
    plan_id: UUID,
    user: CurrentJwtUserId,
    db: DbSession,
) -> ResearchPlanView:
    return await ResearchPlanService(db).reconcile(UUID(user), project_id, plan_id)
