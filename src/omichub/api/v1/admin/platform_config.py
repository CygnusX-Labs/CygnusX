"""平台配置管理路由 — 管理员更新"""

from fastapi import APIRouter

from omichub.api.deps import AdminTotpRequired, DbSession
from omichub.application.schemas.site_settings import SiteSettingsDTO, UpdateSiteSettingsDTO
from omichub.application.services.site_settings_service import SiteSettingsService

router = APIRouter()


@router.patch("/platform-config", response_model=SiteSettingsDTO, summary="更新平台全局配置（管理员+TOTP）")
async def update_platform_config(
    req: UpdateSiteSettingsDTO,
    _totp: AdminTotpRequired,
    db: DbSession,
) -> SiteSettingsDTO:
    """管理员更新平台全局配置；请求头须附带 X-TOTP-Code 二次验证码。"""
    return await SiteSettingsService(db).update_settings(req)
