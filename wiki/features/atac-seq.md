# ATAC-seq 分析

平台当前通过 `flows/atac_seq.yaml`（v0.1.0）接入 ATACFlow，用于 bulk ATAC-seq 染色质可及性分析。页面中的参数、物种和模块以该 YAML 及已部署的 ATACFlow reference 配置为准；实验建议不等同于平台硬校验。

## 实验设计

### 样本准备

- 建议使用新鲜或冷冻细胞/组织
- 细胞数、建库量和测序深度应按样本类型与实验方案确定；页面不将 50,000 个细胞设为统一硬门槛。
- 避免过度交联或核酸降解

### 测序策略

- 双端测序（PE150）
- 每个样本 20M ~ 50M reads
- 生物学重复 ≥ 3

## CygnusX ATAC-seq 流程

基于 ATACFlow，主要步骤：

1. 质量控制：按 ATACFlow 配置执行
2. 序列比对：Bowtie2 或 Chromap（由 `mapping_tools` 参数选择）
3. Peak calling：按流程配置执行
4. 可视化与报告：由 ATACFlow 产出
5. 差异开放区域：启用 `diff_peaks` 和比较组后执行

## 参数说明

| 参数 | 说明 | 推荐值 |
|---|---|---|
| `Genome_Version` | 参考基因组版本 | `hg38`、`GRCm39`、`ITAG4.1`、Lsat 系列等，以 Flow 选项为准 |
| `mapping_tools` | 比对工具 | 由 ATACFlow 支持的 `bowtie2` / `chromap` 选项决定 |
| `diff_peaks` | 是否执行差异开放分析 | 需要有效的 `comparisons` |

## 结果目录

| 目录 | 内容 |
|---|---|
| `peaks/` | 检测到的开放区域 |
| `bigwig/` | 可视化文件 |
| `differential/` | 差异可及性区域 |
| `report/` | HTML 分析报告 |

## 提交与证据边界

- 表单和 AI 助手共用 `TaskService.submit()`；AI 提交需人类确认，确认一次性并绑定参数哈希。
- `diff_peaks` 依赖有效比较组；缺少比较组时不会自动推断分组。
- 任务完成与报告生成属于运行证据，不等于科学结论已验证；整体验收状态见
  [科研证据边界](../research/evidence-boundaries)。

## 相关页面

- [分析流程与工作流](workflows)
- [流程运行时](../architecture/flow-runtime)
- [分析流程扩展](../development/flow-extension)
