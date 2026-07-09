"""站点设置 DTO"""

from typing import Literal

from pydantic import Field, field_validator

from omichub.application.schemas.base import OmicsHubBaseSchema

TOTPPolicy = Literal["off", "optional", "required"]
QuickEntryColor = Literal["blue", "purple", "cyan", "green", "orange", "teal", "gray"]


class HomeQuickEntryDTO(OmicsHubBaseSchema):
    """首页快捷入口配置"""

    key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=24)
    desc: str = Field(default="", max_length=80)
    to: str = Field(min_length=1, max_length=200)
    icon: str = Field(default="DocumentTextOutline", max_length=64)
    icon_bg: QuickEntryColor = "blue"

    @field_validator("to")
    @classmethod
    def validate_internal_route(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("快捷入口路由必须是站内绝对路径")
        return value

    @field_validator("icon")
    @classmethod
    def validate_icon_key(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("图标 key 只能包含字母、数字、下划线或短横线")
        return value


class SiteSettingsDTO(OmicsHubBaseSchema):
    """站点设置（公开）"""

    registration_enabled: bool
    totp_policy: TOTPPolicy
    home_quick_entries: list[HomeQuickEntryDTO]


class UpdateSiteSettingsDTO(OmicsHubBaseSchema):
    """更新站点设置（管理员）"""

    registration_enabled: bool | None = None
    totp_policy: TOTPPolicy | None = None
    home_quick_entries: list[HomeQuickEntryDTO] | None = Field(
        default=None,
        min_length=1,
        max_length=8,
    )
