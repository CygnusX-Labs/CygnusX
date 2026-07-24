/**
 * aiIntents — 工作台模式自动切换的意图匹配关键词
 *
 * 当用户消息同时命中「动词」和「名词」时，自动建议切换到工作台模式。
 * 关键词列表集中维护，便于后续扩展或接入更精确的意图分类。
 */

/** 触发工作台模式的动词列表 */
export const WORKBENCH_VERBS: string[] = [
  '生成',
  '创建',
  '编写',
  '制作',
  '输出',
  '分析',
  '构建',
  '撰写',
  '设计',
  '整理',
]

/** 触发工作台模式的名词列表 */
export const WORKBENCH_NOUNS: string[] = [
  '文档',
  '模板',
  '脚本',
  '报告',
  '文件',
  '流程',
  '方案',
  '计划',
  '图表',
  '代码',
  '笔记',
  '总结',
]

/**
 * 检测用户消息是否匹配工作台模式意图
 * 规则：消息中同时包含至少一个动词和一个名词
 */
export function matchWorkbenchIntent(text: string): boolean {
  const hasVerb = WORKBENCH_VERBS.some((v) => text.includes(v))
  const hasNoun = WORKBENCH_NOUNS.some((n) => text.includes(n))
  return hasVerb && hasNoun
}
