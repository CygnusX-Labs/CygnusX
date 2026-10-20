# RNA-seq 分析

平台当前通过 `flows/rna_seq.yaml`（v2.3.0）接入 RNAFlow，默认描述的是 bulk RNA-seq 差异表达流程。页面参数、可选物种和执行方式以该 YAML 及已部署的 RNAFlow reference 配置为准；下面的实验建议不是平台强制校验。

## 样本设计

- 每个处理组至少 3 个生物学重复
- 尽量控制批次效应
- 记录样本处理方式、测序批次等元信息

## 参考基因组

| 物种 | 版本 |
|---|---|
| 人类 | `hg38` / `GRCm39` 等，以 Flow 下拉选项为准 |
| 小鼠 | `GRCm39` |
| 拟南芥 | `TAIR10.1` |
| 其他已登记物种 | 番茄 `ITAG4.1`、生菜 `Lsat_Salinas_v11` 等 |

## 流程覆盖的分析模块

| 工具 | 适用场景 |
|---|---|
| QC | FastQC、汇总报告和可选质量模块 |
| 比对/定量 | STAR、RSEM（由 RNAFlow 执行） |
| 差异表达 | DESeq2 |
| 可选模块 | 融合、可变剪接、变异和新转录本等，以 Flow 参数为准 |

## 质量控制

1. 检查 FastQC 报告中的 per-base quality
2. 关注 rRNA 残留比例
3. 将比对率、rRNA 比例和样本相关性结合实验设计判断；`>70%` 仅为经验参考，不是平台统一硬阈值。

## 结果解读

差异表达结果关键列：

| 列名 | 含义 |
|---|---|
| `gene_id` | 基因 ID |
| `baseMean` | 平均表达量 |
| `log2FoldChange` | 差异倍数 |
| `padj` | 校正后的 p 值 |

常见筛选示例为 `padj < 0.05` 且 `|log2FoldChange| > 1`，实际阈值应由研究设计、重复数和领域标准确定。

## 提交与证据边界

- 网页表单和 AI 助手走同一条 `TaskService.submit()` 任务链；AI 提交前必须由人类确认参数，
  确认记录一次性并绑定参数哈希。
- Flow 定义和参数会随 Task 冻结，之后修改 YAML 不影响已提交任务。
- 任务成功只代表流程执行完成；报告是证据快照，不等于科学结论已验证，也不自动触发重跑。
- 运行状态、日志和产物路径以任务中心和 Worker 记录为准；当前科研链路的整体验收状态见
  [科研证据边界](../research/evidence-boundaries)。

## 相关页面

- [分析流程与工作流](workflows)
- [流程运行时](../architecture/flow-runtime)
- [分析流程扩展](../development/flow-extension)
- [RNA 报告与交付](../research/reports)
