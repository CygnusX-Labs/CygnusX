"""站点设置 DTO"""

from omichub.application.schemas.base import OmicsHubBaseSchema


class SiteSettingsDTO(OmicsHubBaseSchema):
    """站点设置（公开）"""

    registration_enabled: bool


class UpdateSiteSettingsDTO(OmicsHubBaseSchema):
    """更新站点设置（管理员）"""

    registration_enabled: bool
