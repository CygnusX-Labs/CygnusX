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


class ActivationContent(OmicsHubBaseSchema):
    """账户未激活提示文案（公开读取）。

    用户登录未激活账户时（auth_service 抛“账户未激活”），前端弹出友好提示，
    引导用户联系管理员激活。文案由 data/OmicHub.yaml 的 activation 段驱动，改文件即生效。
    admin_contact 缺省时回退到 registration.admin_contact，避免重复配置。
    """

    message: str
    admin_contact: str = ""


class EasterEggContent(OmicsHubBaseSchema):
    """关于页彩蛋文案（公开读取）。

    在「关于」页点击蓝色星球触发的隐藏弹窗，文案由 data/OmicHub.yaml 的
    easter_egg 段驱动，改文件即生效。
    """

    message: str = "🎉 恭喜你发现了 OmicHub 的隐藏星际守护者！"
    button_text: str = "🐾 召唤星际猫咪"
    toast: str = "🎉 星际守护者已响应召唤！快看看屏幕上留下的足迹吧～ ✨"


class SiteContentDTO(OmicsHubBaseSchema):
    """首页文案（公开读取）"""

    hero: HeroContent
    quick_entries: list[QuickEntryContent]
    guide_steps: list[GuideStepContent]
    registration: RegistrationContent
    activation: ActivationContent = ActivationContent(
        message="你的账号尚未激活，暂无法登录。请联系管理员为你开通激活，开通后即可正常使用平台～",
        admin_contact="",
    )
    easter_egg: EasterEggContent = EasterEggContent()
