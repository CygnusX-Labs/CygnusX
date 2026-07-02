import type { BioPromptTemplate } from './types'

/**
 * 生信分析提示词模板
 *
 * 供 PromptSidebar 展示，点击后内容填入输入框，{{param}} 占位符由用户替换。
 */
export const BIO_PROMPTS: BioPromptTemplate[] = [
  {
    id: 'deg',
    title: '差异表达分析',
    description: '解读 RNA-seq 差异基因列表，给出上调/下调趋势与候选标志物。',
    category: '转录组',
    content:
      '请帮我分析以下差异表达基因列表：\n\n{{gene_list}}\n\n实验分组：{{sample_group}}（对照 vs 处理），阈值 |log2FC| > 1，padj < 0.05。\n请：\n1. 按上调/下调分组归纳；\n2. 挑选 10 个最显著的候选标志物并说明理由；\n3. 给出后续 GO/KEGG 富集建议。',
  },
  {
    id: 'go',
    title: 'GO 富集分析',
    description: '对基因列表做 GO 三大类富集解读，识别显著生物学过程。',
    category: '功能富集',
    content:
      '请对以下基因列表进行 GO 富集分析解读：\n\n{{gene_list}}\n\n请分别从 Biological Process、Molecular Function、Cellular Component 三个本体出发，列出最显著的 Top10 条目（含 GO ID、描述、p-value），并解读可能的核心生物学过程。',
  },
  {
    id: 'kegg',
    title: 'KEGG 通路分析',
    description: '识别显著富集的 KEGG 通路并绘制通路关键节点。',
    category: '功能富集',
    content:
      '请基于以下基因列表做 KEGG 通路富集解读：\n\n{{gene_list}}\n\n请列出 Top15 显著通路（含 pathway ID、名称、p-value、富集基因数），并重点解读与 {{disease_or_phenotype}} 相关的通路及其关键节点基因。',
  },
  {
    id: 'atac',
    title: 'ATAC-seq Peak 注释',
    description: '注释 Peak邻近基因与基序，推断潜在调控转录因子。',
    category: '表观组',
    content:
      '请帮我注释以下 ATAC-seq Peak 列表：\n\n{{peak_list}}\n\n请：\n1. 注释 Peak 在基因组功能区的分布（启动子/增强子/基因间区）；\n2. 推断邻近靶基因；\n3. 做 Motif 分析，给出排名前 10 的候选调控转录因子及结合位点 motif。',
  },
]
