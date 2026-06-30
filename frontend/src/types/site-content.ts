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

export interface SiteContent {
  hero: HeroContent
  quick_entries: QuickEntryContent[]
  guide_steps: GuideStepContent[]
}
