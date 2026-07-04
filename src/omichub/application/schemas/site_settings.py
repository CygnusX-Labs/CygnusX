"""站点设置 DTO"""

from typing import Literal

from omichub.application.schemas.base import OmicsHubBaseSchema


TOTPPolicy = Literal["off", "optional", "required"]


class SiteSettingsDTO(OmicsHubBaseSchema):
    """站点设置（公开）"""

    registration_enabled: bool
    totp_policy: TOTPPolicy


class UpdateSiteSettingsDTO(OmicsHubBaseSchema):
    """更新站点设置（管理员）"""

    registration_enabled: bool | None = None
    totp_policy: TOTPPolicy | None = None
