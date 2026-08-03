"""管理员维护 AgentTeams Bridge 的运行配置。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from omichub.api.deps import AdminRequired, DbSession, require_admin_totp
from omichub.application.schemas.agentteams_bridge import (
    AgentTeamsBridgeConfigDTO,
    AgentTeamsBridgeConfigUpdateDTO,
)
from omichub.application.services.agentteams_bridge_settings_service import (
    AgentTeamsBridgeSettingsService,
)
from omichub.application.services.agentteams_service import AgentTeamsService
from omichub.core.config import get_settings

router = APIRouter()


async def get_bridge_service(db: DbSession) -> AgentTeamsBridgeSettingsService:
    return AgentTeamsBridgeSettingsService(db, get_settings())


BridgeServiceDep = Annotated[AgentTeamsBridgeSettingsService, Depends(get_bridge_service)]


async def _with_connection_state(
    service: AgentTeamsBridgeSettingsService,
) -> AgentTeamsBridgeConfigDTO:
    config = await service.get_public_config()
    runtime = await service.get_runtime_config()
    config.connected = await AgentTeamsService(get_settings(), runtime).is_connected()
    return config


@router.get("/agentteams-bridge", response_model=AgentTeamsBridgeConfigDTO)
async def get_agentteams_bridge_config(
    _admin: AdminRequired,
    service: BridgeServiceDep,
) -> AgentTeamsBridgeConfigDTO:
    return await _with_connection_state(service)


@router.get("/agentteams-bridge/health", summary="检查 Bridge、身份令牌与外部 Worker 健康状态")
async def get_agentteams_bridge_health(
    _admin: AdminRequired,
    service: BridgeServiceDep,
) -> dict:
    runtime = await service.get_runtime_config()
    return await AgentTeamsService(get_settings(), runtime).health_check()


@router.put("/agentteams-bridge", response_model=AgentTeamsBridgeConfigDTO)
async def update_agentteams_bridge_config(
    request: AgentTeamsBridgeConfigUpdateDTO,
    db: DbSession,
    _admin_id: AdminRequired,
    x_totp_code: Annotated[str | None, Header(alias="X-TOTP-Code")] = None,
) -> AgentTeamsBridgeConfigDTO:
    await require_admin_totp(_admin_id, db, x_totp_code)
    service = AgentTeamsBridgeSettingsService(db, get_settings())
    await service.update_config(request)
    return await _with_connection_state(service)
