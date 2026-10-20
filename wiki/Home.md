# CygnusX BioOps Wiki

欢迎访问 CygnusX BioOps（仓库名 OmicHub）Wiki。CygnusX 是面向生命科学的智能科研平台：把数据发现、分析流程、Agent 协作、受控执行与可追溯交付组织在同一个项目上下文中，长期方向是从**可复现计算**走向**专家治理的证据驱动科研**。

> **FROM STARDUST, TO DISCOVERY.**

Wiki 面向研究者、开发者和运维人员，回答“平台现在能做什么、如何操作、边界在哪、如何维护”。涉及实现细节时，以仓库代码、配置、迁移和 [`ARCHITECTURE_DESIGN/`](../ARCHITECTURE_DESIGN/README.md) 中的 as-built 文档为准；本 Wiki 不替代架构基线，也不把规划/提案当作现状。

## 先读这一页

| 你的目标 | 推荐入口 |
| --- | --- |
| 第一次启动本地环境 | [快速开始](getting-started/quickstart) |
| 部署到单机或拆分 Worker | [Docker 部署](deployment/docker-deployment) |
| 了解平台整体架构 | [系统架构总览](architecture/overview) |
| 理解科研链路与当前证据边界 | [科研能力与证据边界](research/evidence-boundaries) |
| 了解 Agent 如何装配与执行 | [Agent 运行时](architecture/agent-runtime) |
| 使用 AI、Studio 或协作室 | [AI 助手与工作台](features/ai-chat)、[AI 多 Agent 协作](features/ai-collaboration) |
| 提交 RNA/ATAC 分析 | [分析流程](features/workflows)、[RNA-seq](features/rna-seq)、[ATAC-seq](features/atac-seq) |
| 新增模块、工具或 Flow | [开发规范](development/index)、[Flow 运行时](architecture/flow-runtime) |
| 排障与日常运维 | [常用命令](operations/common-commands)、[问题排查](operations/troubleshooting) |
| 了解文档规则 | [文档治理与证据等级](architecture/documentation-governance) |

## 平台定位

CygnusX 的工程优先级是验证一条可信的计算与交付链：

```text
研究问题 → 数据发现/导入 → 受控 Flow 提交 → 计算与 QC → 科学报告 → 证据/Manifest → 独立复现
```

当前已实现平台主干、版本化 Flow、Agent/Studio/AgentTeams 执行路径、报告与项目交付机制；**但“当前源码下从数据发现到科学分析、BioReport 与独立复现的端到端链路”尚未完成验收**。平台使用一条严格的成熟度口径：

```text
implemented ≠ isolated-tested ≠ runtime-verified ≠ end-to-end-verified ≠ production-approved
```

任何“已实现”都只表示代码存在；是否可用，取决于对应门禁与运行验收状态。详见[科研能力与证据边界](research/evidence-boundaries)。

## 四类执行形态与 L1–L4 入口

| 入口 | 适用工作 | 执行形态 |
| --- | --- | --- |
| **L1 生信工具箱** | 可重复的工具操作与轻量可视化 | 同步/异步 ToolBridge 作业 |
| **L2 星尘 AI 助手** | 需求澄清、检索、轻量调用 | Chat Runtime（LangGraph / Legacy ReAct） |
| **L3 OmicStudio** | 交互式深度分析、代码与文件 | 一会话一容器的 Studio 沙箱 |
| **L4 多 Agent 协作室** | 规划、分工、复核与交付 | AgentTeams Room / Case / Worker |

> L1–L4 是 CygnusX 的**产品交互层级**，不是 Agentic Science 文献中的科研自主性分级；产品 L4 不等于自主科学发现。

## 文档地图

### 入门、部署与运维

- [快速开始](getting-started/index)：环境要求、本地开发、Docker 最短路径。
- [首次部署与管理员注册](getting-started/first-time-setup)：`/setup` 初始化与必要密钥。
- [部署与运维](deployment/index)：主栈、Worker、AgentTeams、生产检查与回滚。
- [常用命令](operations/common-commands)、[问题排查](operations/troubleshooting)。

### 架构

- [系统架构总览](architecture/overview)：分层、四类执行路径与核心数据流。
- [Agent 运行时](architecture/agent-runtime) · [沙箱与执行隔离](architecture/sandbox) · [MCP 体系](architecture/mcp) · [Skill 体系](architecture/skills)
- [记忆与知识库](architecture/memory-knowledge) · [Flow 运行时](architecture/flow-runtime) · [数据库基础设施](architecture/database) · [存储层](architecture/storage)
- [模型路由与 Token 计费](architecture/model-routing-billing) · [安全模型](architecture/security-model) · [可观测性](architecture/observability) · [日志架构](architecture/logging)
- [数据目录结构](architecture/data-directory) · [文档治理与证据等级](architecture/documentation-governance)

### 科研链路

- [科研能力与证据边界](research/evidence-boundaries)：M1/M2/M3、RC04、RI09.5 与门禁含义。
- [数据发现与获取](research/data-discovery) · [Dataset 与 Handoff](research/dataset)
- [科研交付链](research/delivery) · [报告体系](research/reports) · [科研计划与科研闭环](research/plan-and-loop)

### 功能特性

- [功能特性索引](features/index)：AI、工具箱、Flow、下载、知识库、沙盒、参考数据与分析。
- [L1 生信工具箱](features/toolbox) · [分析流程](features/workflows) · [数据下载](features/downloads)
- [RNA-seq](features/rna-seq) · [ATAC-seq](features/atac-seq) · [流程监控](features/workflow-monitor)

### 开发、安全与文档维护

- [开发规范](development/index)：API、前端、迁移、Flow 与工具接入。
- [安全索引](security/index)：安全模型、加固清单与环境变量。
- [Wiki 维护与知识库同步](documentation-maintenance)：内容来源、同步与更新规则。

## 权威来源

1. 当前代码、配置、Alembic 迁移和部署文件；
2. [`ARCHITECTURE_DESIGN/README.md`](../ARCHITECTURE_DESIGN/README.md) 索引下的 as-built 文档；
3. 根目录 [`README.md`](../README.md) 的能力边界与路线图；
4. 本 Wiki（操作说明，随实现更新）。

`docs/` 下的历史方案、`ARCHITECTURE_DESIGN/deprecated/`、提案与 vision 文档**不作为现状依据**。
