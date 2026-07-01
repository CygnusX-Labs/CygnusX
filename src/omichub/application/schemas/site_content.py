"""站点首页文案 DTO（外置 YAML 驱动）"""

from omichub.application.schemas.base import OmicsHubBaseSchema


class HeroContent(OmicsHubBaseSchema):
    """Hero 欢迎区文案"""

    title: str
    description: str


class QuickEntryContent(OmicsHubBaseSchema):
    """快捷入口文案。

    key 用于前端与硬编码的图标/路由做合并，title/desc 为可配置文案。
    """

    key: str
    title: str
    desc: str


class GuideStepContent(OmicsHubBaseSchema):
    """使用引导步骤文案"""

    title: str
    desc: str


class RegistrationContent(OmicsHubBaseSchema):
    """注册策略提示文案（公开读取）。

    真正的注册开关由后台 site-settings（DB）控制并在 /auth/register 强制校验；
    这里只提供“关闭注册时告诉用户联系谁”的文案，由 data/OmicHub.yaml 驱动。
    """

    disabled_message: str
    admin_contact: str


class SiteContentDTO(OmicsHubBaseSchema):
    """首页文案（公开读取）"""

    hero: HeroContent
    quick_entries: list[QuickEntryContent]
    guide_steps: list[GuideStepContent]
    registration: RegistrationContent
