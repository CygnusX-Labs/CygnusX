/**
 * KEGG / GO 富集分析相关类型定义
 */

/** 物种下拉选项 */
export interface SpeciesOption {
  /** 物种唯一 ID */
  id: string
  /** 展示名称 */
  label: string
  /** KEGG 物种代码，如 hsa、ath */
  kegg_code: string
  /** OrgDB 包名，如 org.Hs.eg.db */
  org_db: string
  /** 基因 ID 类型，如 SYMBOL、TAIR */
  id_type: string
}

/** 单条富集结果 */
export interface EnrichmentRow {
  /** 通路 ID */
  id: string
  /** 通路描述 */
  description: string
  /** GeneRatio */
  gene_ratio: string
  /** pvalue */
  pvalue: number
  /** p.adjust */
  p_adjust: number
  /** 富集基因数 */
  count: number
}

/** 富集分析接口返回 */
export interface EnrichmentResult {
  /** 任务 ID */
  task_id: string
  /** 供 Plotly.js 渲染的图表 JSON */
  plotly_json?: Record<string, unknown>
  /** 结果表格 */
  table_data: EnrichmentRow[]
}
