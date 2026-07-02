"""Agent 模板公开 API — 前台智能体集市/沙盒读取 Agent 设定"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.agent import AgentTemplateDTO
from omichub.application.services.agent_service import AgentService

router = APIRouter()


def get_agent_service(db: DbSession) -> AgentService:
    return AgentService(db)


AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]


@router.get("", response_model=list[AgentTemplateDTO], summary="启用中的 Agent 列表")
async def list_agents(
    _user: CurrentUserId,
    service: AgentServiceDep,
) -> list[AgentTemplateDTO]:
    return await service.list_agents(active_only=True)


@router.get("/{agent_id}", response_model=AgentTemplateDTO, summary="Agent 详情")
async def get_agent(
    _user: CurrentUserId,
    service: AgentServiceDep,
    agent_id: str,
) -> AgentTemplateDTO:
    return await service.get_agent_dto(agent_id)
