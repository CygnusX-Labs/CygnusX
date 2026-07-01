/** 知识库相关类型 */

/** 导航列表项（来自 /docs/knowledge） */
export interface KnowledgeItem {
  id: string
  title: string
  /** 可选分类，前端按它聚合成树 */
  category?: string | null
}

/** 文档内容（来自 /docs/knowledge/:docId） */
export interface KnowledgeDoc {
  id: string
  title: string
  content: string
}

/** 树形目录节点（前端由 KnowledgeItem 按 category 聚合而成） */
export interface DocTreeNode {
  /** 叶子节点用文档 id；分类节点用 category 名 */
  key: string
  label: string
  /** 仅叶子节点有：对应文档 id */
  docId?: string
  /** 分类节点 */
  isCategory?: boolean
  children?: DocTreeNode[]
}
