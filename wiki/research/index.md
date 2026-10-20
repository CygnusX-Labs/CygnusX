# 科研链路

CygnusX 的长期目标是支撑“问题 → 假设 → 方法 → 计算 → 证据 → 新问题”的科研循环。当前工程重点是先把**可信计算与交付链**打通；本 chapter 按链路阶段说明已实现内容、运行门禁和未验收部分。

> **先读**：[科研能力与证据边界](evidence-boundaries)。本 chapter 的所有页面都不构成“生产可用”或“自主科学发现”的声明。

## 链路与页面

```text
公共数据/文献发现          数据获取/导入            分析与 QC
   data-discovery      →    dataset              →   flow-runtime / rna-seq / atac-seq
        │                        │                         │
        └───────────────► 科研交付 ◄──────────────────────┘
                          delivery
                             │
                       reports（科学报告 / 可复现性报告 / 交付包）
                             │
                       plan-and-loop（计划、工作区、执行历史、复现）
```

| 阶段 | 页面 | 当前状态摘要 |
| --- | --- | --- |
| 能力边界与路线图 | [科研能力与证据边界](evidence-boundaries) | 统一成熟度口径；M1 未完成；M2 2027 年启动研究 |
| 数据发现与获取 | [数据发现与获取](data-discovery) | 寻宝鼠与下载模块已实现；写路径受源码门禁 |
| 资产与交接 | [Dataset 与 Handoff](dataset) | 七表、版本冻结与 Handoff 已实现；`worker_paths_verified=false` |
| 交付与证据 | [科研交付链](delivery) | 报告/Manifest/Export Job 已接入；真实环境验收 BLOCKED |
| 报告 | [报告体系](reports) | BioReport 是独立引擎；平台报告与 RI09.5 原型边界需区分 |
| 计划与复现 | [科研计划与科研闭环](plan-and-loop) | 计划 PLAN_ONLY；工作区归档/执行历史/Notebook 已实现 |

## 共同纪律

1. **项目是上下文，不是装饰。** Task、文件、报告、证据必须通过明确关联进入项目，不能按目录名或时间猜测归属。
2. **人类保留方法与结论责任。** 计划、审批、报告解释和科研结论由研究者负责；AI 只做调度、检索、解释与辅助。
3. **冻结与重验。** 计划、Dataset 版本、Handoff、报告快照和导出 Manifest 都冻结内容摘要；执行/下载前重新校验，不静默替换。
4. **运行证据有范围。** 历史 PASS 只对记录的 Run ID、提交、镜像和环境成立。
5. **不把报告当分析。** 项目汇总报告不等于科学分析报告；`reproduction_status=NOT_RUN` 不表示已复现。

## 相关入口

- [系统架构总览](../architecture/overview) · [Flow 运行时](../architecture/flow-runtime)
- [分析流程](../features/workflows) · [RNA-seq](../features/rna-seq) · [ATAC-seq](../features/atac-seq)
- 根 [README](../../README.md) 的路线图与证据表
