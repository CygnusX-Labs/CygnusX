"""平台配置管理路由 — 管理员更新。

TOTP 二次校验仅对高敏感字段（注册开关 / TOTP 策略 / 首页快捷入口）强制；
功能灰度开关（如 subagent_fanout_enabled）等非敏感项免验，避免未开 2FA 的
管理员被无法填写的验证码弹窗挡死。
"""

from typing import Annotated

from fastapi import APIRouter, Header

from omichub.api.deps import AdminRequired, DbSession, require_admin_totp
from omichub.application.schemas.site_settings import SiteSettingsDTO, UpdateSiteSettingsDTO
from omichub.application.services.site_settings_service import SiteSettingsService

router = APIRouter()

# 免 TOTP 的非敏感字段：仅这些字段被改动时无需二次校验
_NON_SENSITIVE_PLATFORM_KEYS = frozenset(
    {"subagent_fanout_enabled", "agentteams_chat_entry_enabled"}
)


@router.patch(
    "/platform-config",
    response_model=SiteSettingsDTO,
    summary="更新平台全局配置（管理员；敏感项需 TOTP）",
)
async def update_platform_config(
    req: UpdateSiteSettingsDTO,
    admin_id: AdminRequired,
    db: DbSession,
    x_totp_code: Annotated[str | None, Header(alias="X-TOTP-Code")] = None,
) -> SiteSettingsDTO:
    """管理员更新平台全局配置。

    本次改动若触及高敏感字段（注册开关 / TOTP 策略 / 首页快捷入口等），
    请求头须附带 X-TOTP-Code；若仅改动功能灰度开关等非敏感项则免验。
    """
    touched = req.model_fields_set
    if touched - _NON_SENSITIVE_PLATFORM_KEYS:
        # 复用既有敏感操作校验：管理员 + 已开 2FA + 验证码正确
        await require_admin_totp(admin_id, db, x_totp_code)
    return await SiteSettingsService(db).update_settings(req)
