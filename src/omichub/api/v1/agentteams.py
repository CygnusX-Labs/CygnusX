"""Authenticated read-only Case views backed by the external AgentTeams Bridge."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.services.agentteams_bridge_settings_service import (
    AgentTeamsBridgeSettingsService,
)
from omichub.application.services.agentteams_service import AgentTeamsService
from omichub.core.config import get_settings

router = APIRouter()


async def get_agentteams_service(db: DbSession) -> AgentTeamsService:
    settings = get_settings()
    bridge_config = await AgentTeamsBridgeSettingsService(db, settings).get_runtime_config()
    return AgentTeamsService(settings, bridge_config)


AgentTeamsServiceDep = Annotated[AgentTeamsService, Depends(get_agentteams_service)]


class AgentTeamsCaseCreateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=256)
    intent: str = Field(min_length=1, max_length=256)
    flow_id: str = Field(default="rna_seq", min_length=1, max_length=128)
    sample_sheet: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)
    comparisons: list[dict[str, Any]] | None = Field(default=None, max_length=1_000)


class AgentTeamsCaseSubmitRequest(BaseModel):
    task_name: str = Field(min_length=1, max_length=128)


@router.get("/status", summary="获取 AgentTeams Bridge 接入状态")
async def get_status(service: AgentTeamsServiceDep) -> dict[str, bool]:
    return {"available": await service.is_connected()}


@router.get("/cases", summary="获取当前用户的 Agent 协作案例")
async def list_cases(
    current_user_id: CurrentUserId,
    service: AgentTeamsServiceDep,
    case_status: Annotated[str | None, Query(alias="status")] = None,
    project_id: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    return await service.list_cases(
        current_user_id,
        case_status=case_status,
        project_id=project_id,
        cursor=cursor,
        limit=limit,
    )


@router.post("/cases", status_code=status.HTTP_201_CREATED, summary="创建当前用户的协作案例")
async def create_case(
    request: AgentTeamsCaseCreateRequest,
    current_user_id: CurrentUserId,
    service: AgentTeamsServiceDep,
) -> dict[str, Any]:
    return await service.create_case(
        case_id=f"bioops_{uuid4().hex}",
        project_id=request.project_id,
        intent=request.intent,
        requester_ref=current_user_id,
        flow_id=request.flow_id,
        sample_sheet=request.sample_sheet,
        comparisons=request.comparisons,
    )


@router.get("/cases/{case_id}", summary="获取当前用户的 Agent 协作案例详情")
async def get_case(
    case_id: str, current_user_id: CurrentUserId, service: AgentTeamsServiceDep
) -> dict[str, Any]:
    return await service.get_case(case_id, current_user_id)


@router.post("/cases/{case_id}/refresh", summary="同步当前协作案例的任务状态")
async def refresh_case(
    case_id: str, current_user_id: CurrentUserId, service: AgentTeamsServiceDep
) -> dict[str, Any]:
    return await service.refresh_case(case_id, current_user_id)


@router.post(
    "/cases/{case_id}/submit",
    status_code=status.HTTP_201_CREATED,
    summary="人工确认并提交协作任务",
)
async def approve_and_submit_case_task(
    case_id: str,
    request: AgentTeamsCaseSubmitRequest,
    current_user_id: CurrentUserId,
    service: AgentTeamsServiceDep,
) -> dict[str, Any]:
    return await service.approve_and_submit_task(
        case_id=case_id,
        requester_ref=current_user_id,
        task_name=request.task_name,
    )


@router.get("/cases/{case_id}/events", summary="获取协作案例审计事件")
async def get_case_events(
    case_id: str,
    current_user_id: CurrentUserId,
    service: AgentTeamsServiceDep,
    cursor: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    return await service.get_case_events(case_id, current_user_id, cursor=cursor, limit=limit)
