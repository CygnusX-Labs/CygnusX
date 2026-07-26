/**
 * Agent Skills（SKILL.md 标准）相关类型 —— 导入预览 / 市场 / 更新检查
 */

export interface SkillFileEntry {
  path: string
  size: number
  /** skill_md | script | reference | asset | other */
  kind: string
  content?: string | null
}

/** 四入口统一解析产出：确认后才入库 */
export interface SkillImportPreview {
  skill_id: string
  name: string
  description: string
  body: string
  frontmatter: Record<string, unknown>
  icon: string
  category: string
  version: string
  author: string
  /** market | github | zip | json */
  source_type: string
  source_ref: string
  source_commit: string
  has_scripts: boolean
  warnings: string[]
  files: SkillFileEntry[]
}

export interface SkillMarketplaceItem {
  skill_id: string
  name: string
  description: string
  icon: string
  category: string
  version: string
  author: string
  has_scripts: boolean
  installed: boolean
}

export interface SkillUpdateCheck {
  has_update: boolean
  current_version: string
  current_commit: string
  latest_commit: string
  source_ref: string
  message: string
}
