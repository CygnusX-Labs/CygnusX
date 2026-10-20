# 科研能力与证据边界

CygnusX 把“能运行”拆成五个等级。任何页面、发布说明或演示都必须说明证据处于哪一级；这是平台科研可信度的基础。

```text
implemented ≠ isolated-tested ≠ runtime-verified ≠ end-to-end-verified ≠ production-approved
```

| 等级 | 含义 | 典型证据 |
| --- | --- | --- |
| implemented | 源码/配置/迁移存在 | 代码路径、迁移、开关 |
| isolated-tested | 单元/集成测试通过 | pytest、隔离 doubles |
| runtime-verified | 在真实组件中运行通过 | 隔离 Docker/PG/Redis/浏览器 + Run 记录 |
| end-to-end-verified | 完整业务链在冻结源码与批准环境通过 | E2E 验收报告、数据与产物 |
| production-approved | 完成部署、安全、运维与回滚验收 | 生产发布审批 |

相邻等级不能互相替代；“代码存在”不能证明“功能可用”，“测试通过”不能证明“生产安全”。

## 当前能力状态（工程快照）

| 领域 | 已存在/已证明 | 证据边界与下一道门 |
| --- | --- | --- |
| 平台基础 | Vue 3 + FastAPI + 项目/任务/迁移/队列/部署配置 | 需在冻结源码与一次性环境重跑全栈集成 |
| Agent/Skill/MCP | 声明式 Agent、Skill 组织、工具接入、隔离/契约测试 | 真实 Agent → 审批 → 执行 → 产物闭环未作为当前源码 E2E 验收 |
| 数据发现与获取 | 寻宝鼠、下载服务契约、Dataset/FileRegistry、Polariseq | 下载与 Agent 写路径受源码门禁；真实 Worker 需单独验收 |
| 版本化流程 | FlowFrame 约定、RNAFlow/ATACFlow 实现 | 平台准入到科学结果与独立复现的集成运行待证据 |
| 受控执行 | Approval、Admission、Budget、撤销/epoch、受限执行 | 活跃基线仍有源码写门禁与部署验收要求；隔离测试不等于运行强制 |
| 科学报告 | BioReport 独立 Python/Quarto 引擎；平台报告适配器 | RI09.5 只生成过**项目汇总** HTML/PDF，不等于 RNAFlow → 科学 BioReport |
| 可验证交付 | Project/Run、FileRegistry、Evidence/Manifest、ExportSelectionV2 | RI09.5 历史链路有 HTML/PDF → M1 → ZIP → JWT 下载；RC04 Core 仍为 PARTIAL |
| Agentic 科学发现 | 规划、证据、审阅与后续探索的架构概念 | 结构化假设评估与多轮证据驱动发现仍是**研究目标** |

## 关键验收记录

### RI09.5（历史隔离运行）

Run 标识：`ri095-authorized-20261017-attempt1`（记录于 `docs/audits/RI095-Authorized-Runtime-Acceptance-Results.md`）。

已证明：

- 项目汇总报告 HTML/PDF 生成；
- V2 ZIP 导出；
- 完整性校验；
- JWT 授权下载。

**未证明**：

- 完整 RNAFlow → 科学 BioReport 工作流；
- 非空科研 corpus 下的真实科研记录/ZIP；
- 独立复现；
- 当前源码与当前镜像仍通过。

### RC04（2026-10-18 审计）

- Core：**PARTIAL / NOT ACCEPTED**；
- 历史浏览器断言：31/34；
- 缺当前源码/镜像冻结证明；
- 缺新的 FI01–FI06 故障注入验收；
- 缺独立证据/安全评审。

详细门禁矩阵见 `docs/audits/RI095-RC04-Completion-Gate-Matrix.md`。

## 源码门禁（不能被环境变量解除）

| 门禁 | 位置/语义 |
| --- | --- |
| `WRITE_RUNTIME_ACCEPTED = False` | Agent 工具网关：写操作执行前拒绝 |
| `tool_gateway_read_enabled = false` | Agent 工具读取默认关闭 |
| `worker_paths_verified = false` | Dataset Handoff 的 Worker 路径未验收 |
| `DATASET_IMPORT_WRITE` / `ANALYSIS_SUBMIT_FROM_DATASET` / `COUNTS_DEG_FLOW_ENABLED` | 默认 false |
| `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED = False` | 下载传输运行验收未通过 |
| `LEGACY_PIPELINE_TOOLS` | 旧 Flow 工具兼容；默认 true |

这些是**代码常量**。发布说明必须如实标注“门禁仍关闭”，不能用改 `.env` 或打开业务 flag 代替验收。

## 路线图 M1–M3

| 里程碑 | 内容 | 当前状态 |
| --- | --- | --- |
| **M1** | 可复现多组学基础设施：发现/导入 → 冻结 FlowFrame 计划 → RNAFlow/领域 Flow → QC → 科学 BioReport → Evidence/Manifest/Delivery → 独立复现 | 组件存在；当前源码集成科学工作流与多项受保护运行时门禁未关闭 |
| **M2** | 专家治理、可追溯的迭代科学发现；Scientific Discovery Core：Scientific Reasoning / Scientific Validation / Research Evolution | **2027-01-01 正式启动**研究阶段，不是现有能力 |
| **M3** | 跨领域通用 Agentic 科学计算 | 长期假设，需独立验证 |

L1–L4 是产品交互层级，不是科研自主性分级；产品 L4 不等于自主科学发现。

## 报告与复现的红线

1. 项目汇总报告 ≠ 科学分析报告；不得把 RI09.5 的项目报告当作 RNAFlow 科学结论。
2. Manifest/证据包 ≠ 科研可复现；`reproduction_status=NOT_RUN` 必须保留。
3. Claim 引用存在 ≠ 科学事实已验证；VERIFIED_VALUE / SUPPORTED_CLAIM / AI_INTERPRETATION / NOT_VERIFIED 必须区分。
4. 历史证据不能自动适用于当前工作树；发布前重新冻结源码、镜像和环境。

## 相关页面

- [科研链路索引](index) · [数据发现与获取](data-discovery) · [Dataset 与 Handoff](dataset)
- [科研交付链](delivery) · [报告体系](reports) · [科研计划与科研闭环](plan-and-loop)
- [安全模型](../architecture/security-model) · [可观测性](../architecture/observability)
- 根 [README](../../README.md) · [ARCHITECTURE_DESIGN 索引](../../ARCHITECTURE_DESIGN/README.md)
