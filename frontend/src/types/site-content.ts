/** 首页文案（来自 /site-content） */

export interface HeroContent {
  title: string
  description: string
}

/** 快捷入口文案：key 与前端硬编码的图标/路由映射 */
export interface QuickEntryContent {
  key: string
  title: string
  desc: string
}

export interface GuideStepContent {
  title: string
  desc: string
}

/** 注册策略提示文案：开关由后台 site-settings 控制，这里仅提供关闭时的提示文案与管理员联系方式 */
export interface RegistrationContent {
  /** 注册关闭时的提示文案 */
  disabled_message: string
  /** 暂停注册时提示联系的管理员（可空） */
  admin_contact: string
}

export interface SiteContent {
  hero: HeroContent
  quick_entries: QuickEntryContent[]
  guide_steps: GuideStepContent[]
  /** 注册策略提示文案（可选：后端未返回时不阻断 HomeView 默认文案） */
  registration?: RegistrationContent
}
