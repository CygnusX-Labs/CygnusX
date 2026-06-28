"""Skill 管理 API — 管理员 CRUD"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from omichub.api.deps import DbSession
from omichub.api.v1.admin.users import AdminRequired
from omichub.application.schemas.skill import (
    CreateSkillDTO,
    SkillDTO,
    UpdateSkillDTO,
)
from omichub.application.services.skill_service import SkillService

router = APIRouter()


def get_skill_service(db: DbSession) -> SkillService:
    return SkillService(db)


SkillServiceDep = Annotated[SkillService, Depends(get_skill_service)]


@router.get("", response_model=list[SkillDTO], summary="技能列表")
async def list_skills(
    _admin: AdminRequired,
    service: SkillServiceDep,
    active_only: bool = False,
) -> list[SkillDTO]:
    return await service.list_skills(active_only=active_only)


@router.post("", response_model=SkillDTO, status_code=201, summary="创建技能")
async def create_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    req: CreateSkillDTO,
) -> SkillDTO:
    return await service.create_skill(req)


@router.get("/{skill_id}", response_model=SkillDTO, summary="技能详情")
async def get_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
) -> SkillDTO:
    return await service.get_skill(skill_id)


@router.put("/{skill_id}", response_model=SkillDTO, summary="更新技能")
async def update_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
    req: UpdateSkillDTO,
) -> SkillDTO:
    return await service.update_skill(skill_id, req)


@router.delete("/{skill_id}", summary="删除技能")
async def delete_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
) -> dict[str, bool]:
    await service.delete_skill(skill_id)
    return {"deleted": True}


@router.post("/{skill_id}/toggle", response_model=SkillDTO, summary="启用/停用技能")
async def toggle_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
) -> SkillDTO:
    return await service.toggle_skill(skill_id)
