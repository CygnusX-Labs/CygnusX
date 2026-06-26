"""AI Provider 配置管理 — 管理端路由"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from omichub.api.deps import DbSession
from omichub.api.v1.admin.users import AdminRequired
from omichub.application.schemas.ai_provider import (
    AIProviderConfigCreateDTO,
    AIProviderConfigDTO,
    AIProviderConfigTestRequest,
    AIProviderConfigTestResponse,
    AIProviderConfigUpdateDTO,
)
from omichub.application.services.ai_provider_service import AIProviderConfigService

router = APIRouter()


def get_service(db: DbSession) -> AIProviderConfigService:
    return AIProviderConfigService(db)


ServiceDep = Annotated[AIProviderConfigService, Depends(get_service)]


@router.get("", response_model=list[AIProviderConfigDTO], summary="AI Provider 配置列表")
async def list_configs(
    _admin: AdminRequired,
    service: ServiceDep,
) -> list[AIProviderConfigDTO]:
    return await service.list_configs()


@router.post(
    "",
    response_model=AIProviderConfigDTO,
    status_code=201,
    summary="创建 AI Provider 配置",
)
async def create_config(
    _admin: AdminRequired,
    service: ServiceDep,
    req: AIProviderConfigCreateDTO,
) -> AIProviderConfigDTO:
    return await service.create_config(req)


@router.get("/{config_id}", response_model=AIProviderConfigDTO, summary="AI Provider 配置详情")
async def get_config(
    _admin: AdminRequired,
    service: ServiceDep,
    config_id: UUID,
) -> AIProviderConfigDTO:
    return await service.get_config(config_id)


@router.put("/{config_id}", response_model=AIProviderConfigDTO, summary="更新 AI Provider 配置")
async def update_config(
    _admin: AdminRequired,
    service: ServiceDep,
    config_id: UUID,
    req: AIProviderConfigUpdateDTO,
) -> AIProviderConfigDTO:
    return await service.update_config(config_id, req)


@router.delete("/{config_id}", summary="删除 AI Provider 配置")
async def delete_config(
    _admin: AdminRequired,
    service: ServiceDep,
    config_id: UUID,
) -> dict[str, bool]:
    ok = await service.delete_config(config_id)
    return {"deleted": ok}


@router.post(
    "/{config_id}/set-default",
    response_model=AIProviderConfigDTO,
    summary="设为默认 AI Provider",
)
async def set_default_config(
    _admin: AdminRequired,
    service: ServiceDep,
    config_id: UUID,
) -> AIProviderConfigDTO:
    return await service.set_default(config_id)


@router.post(
    "/{config_id}/test",
    response_model=AIProviderConfigTestResponse,
    summary="测试 AI Provider 连接",
)
async def test_config(
    _admin: AdminRequired,
    service: ServiceDep,
    config_id: UUID,
    req: AIProviderConfigTestRequest | None = None,
) -> AIProviderConfigTestResponse:
    return await service.test_config(config_id, req.message if req else "")
