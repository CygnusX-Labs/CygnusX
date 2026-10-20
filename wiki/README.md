# CygnusX Wiki 总览

本目录是 CygnusX BioOps 面向研究者、开发者和运维人员的操作文档集合。它回答“现在如何使用、如何开发、如何维护平台”，不复制架构规范。涉及实现边界时，以仓库当前代码和 [`ARCHITECTURE_DESIGN/README.md`](../ARCHITECTURE_DESIGN/README.md) 指向的 as-built 文档为准。

## 阅读路径

| 你的角色/目标 | 推荐顺序 |
| --- | --- |
| 第一次接触平台 | [Home](Home) → [快速开始](getting-started/quickstart) → [系统架构总览](architecture/overview) |
| 关注科研能力与验收状态 | [科研能力与证据边界](research/evidence-boundaries) → [科研交付链](research/delivery) → [报告体系](research/reports) |
| 开发者 | [开发规范](development/index) → [项目结构](development/project-structure) → 对应[架构子系统](architecture/index) |
| 运维/部署 | [Docker 部署](deployment/docker-deployment) → [生产检查清单](deployment/production-checklist) → [问题排查](operations/troubleshooting) |
| 安全审查 | [安全模型](architecture/security-model) → [安全加固清单](security/hardening-checklist) → [环境变量与密钥](security/env-variables) |
| 文档维护者 | [文档治理与证据等级](architecture/documentation-governance) → [Wiki 维护与知识库同步](documentation-maintenance) |

## 证据边界（全 Wiki 通用）

平台统一使用以下成熟度口径，任何页面都不应把相邻等级混为一谈：

```text
implemented ≠ isolated-tested ≠ runtime-verified ≠ end-to-end-verified ≠ production-approved
```

- **已实现**：源码、配置或迁移存在；
- **已隔离测试**：单元/集成测试通过，但不代表真实 PostgreSQL、Redis、Worker 或浏览器环境可用；
- **已运行验证**：在指定 Run ID、提交、镜像摘要和环境中有证据，不代表当前工作树仍通过；
- **端到端验证**：完整业务链在冻结源码与批准环境中通过；
- **生产准入**：完成部署、安全与运维验收。

当前关键事实：

- 下载、Agent 写操作、Dataset 执行与科研交付仍受源码门禁保护（如 `WRITE_RUNTIME_ACCEPTED=False`、`worker_paths_verified=false`），**环境变量不能解除**；
- RC04 审计（2026-10-18）中 Core 为 **PARTIAL / NOT ACCEPTED**；
- RI09.5 的历史运行证据只覆盖**项目汇总报告**的 HTML/PDF、ZIP、完整性校验与 JWT 下载，**不等于 RNAFlow → 科学 BioReport → 独立复现**；
- Agentic scientific discovery（假设生成、多轮证据驱动发现）仍是研究目标，不是已验证能力。

详见[科研能力与证据边界](research/evidence-boundaries)。

## 内容地图

### 入门与部署

- [快速开始索引](getting-started/index)：环境要求、本地开发、Docker 最短路径。
- [首次部署与管理员注册](getting-started/first-time-setup)：`/setup` 初始化和必要密钥。
- [部署与运维索引](deployment/index)：主栈、Worker、AgentTeams、生产检查与回滚。

### 架构

- [架构与数据索引](architecture/index)：子系统划分、阅读边界和权威文档映射。
- [系统架构总览](architecture/overview)：分层、四类执行形态、关键数据流。
- 执行面：[Agent 运行时](architecture/agent-runtime)、[沙箱与执行隔离](architecture/sandbox)、[MCP 体系](architecture/mcp)、[Skill 体系](architecture/skills)。
- 数据面：[记忆与知识库](architecture/memory-knowledge)、[数据库基础设施](architecture/database)、[存储层](architecture/storage)、[数据目录结构](architecture/data-directory)。
- 计算面：[Flow 运行时](architecture/flow-runtime)、[模型路由与 Token 计费](architecture/model-routing-billing)。
- 治理面：[安全模型](architecture/security-model)、[可观测性](architecture/observability)、[日志架构](architecture/logging)、[文档治理与证据等级](architecture/documentation-governance)。

### 科研链路

- [科研能力与证据边界](research/evidence-boundaries)：路线图 M1–M3、验收口径与当前门禁。
- [数据发现与获取](research/data-discovery)：寻宝鼠、下载三来源与 Dataset 发现。
- [Dataset 与 Handoff](research/dataset)：七表模型、版本冻结与执行交接。
- [科研交付链](research/delivery)：Project/Run/Case/Artifact/Evidence/Manifest/Export。
- [报告体系](research/reports)：科学报告、可复现性报告与交付包。
- [科研计划与科研闭环](research/plan-and-loop)：PLAN_ONLY 计划、工作区归档、执行历史与 Notebook 导出。

### 功能

- [功能特性索引](features/index)：AI、工具箱、Flow、下载、知识库、沙盒、参考数据与分析。
- [L1 生信工具箱](features/toolbox)：工具注册、任务模型与 ToolBridge 调用模式。
- [AI 助手与工作台](features/ai-chat)、[AI 多 Agent 协作](features/ai-collaboration)。
- [分析流程与工作流](features/workflows)、[流程监控](features/workflow-monitor)、[RNA-seq](features/rna-seq)、[ATAC-seq](features/atac-seq)。
- [数据下载](features/downloads)、[实验室知识库](features/knowledge-base)、[云端沙盒终端](features/sandbox-terminal)、[参考基因组与数据库](features/reference-database)、[系统发育树](features/phylogenetic-tree)。

### 开发

- [开发规范索引](development/index)：最低验证命令与修改入口。
- [项目结构](development/project-structure)：后端分层、前端目录和配置注册表。
- [模块设计与接入](development/module-design)、[API 设计约定](development/api-design)、[前端规范](development/frontend-conventions)。
- [数据库迁移](development/database-migrations)、[分析流程扩展](development/flow-extension)、[生信工具接入](development/bio-tool-guide)。

### 运维与安全

- [常用命令](operations/common-commands)、[问题排查](operations/troubleshooting)、[运维索引](operations/index)。
- [安全索引](security/index)、[安全加固清单](security/hardening-checklist)、[环境变量与密钥](security/env-variables)。

## 全部页面索引

| 页面 | 说明 |
| --- | --- |
| [Home](Home) | Wiki 首页与角色导航 |
| [Wiki 维护与知识库同步](documentation-maintenance) | 内容来源、同步和更新规则 |
| [快速开始](getting-started/quickstart) | 本地开发和 Docker 最短路径 |
| [首次部署与管理员注册](getting-started/first-time-setup) | `/setup` 初始化流程 |
| [快速开始索引](getting-started/index) | 入门页面导航和环境要求 |
| [系统架构总览](architecture/overview) | 技术栈、分层、执行形态和关键数据流 |
| [Agent 运行时](architecture/agent-runtime) | Agent 装配、执行路径、上下文与事件 |
| [沙箱与执行隔离](architecture/sandbox) | Chat/Studio 沙箱、capability、镜像和安全基线 |
| [MCP 体系](architecture/mcp) | 三层 MCP、Preset、固定 Flow 工具与 Builder |
| [Skill 体系](architecture/skills) | 两套 Skill 系统、渐进披露与调用审计 |
| [记忆与知识库](architecture/memory-knowledge) | pgvector 记忆、Studio 文件记忆与知识库 |
| [Flow 运行时](architecture/flow-runtime) | 六段 YAML、热重载、确认门与九步提交链 |
| [数据库基础设施](architecture/database) | 116 表、连接池、仓储、迁移与对账 |
| [存储层](architecture/storage) | 单存储根、路径工厂、sync 与防复发门禁 |
| [模型路由与 Token 计费](architecture/model-routing-billing) | Router/ModelSelector、usage 归一化与饼干扣费 |
| [安全模型](architecture/security-model) | 身份、模块门禁、确认凭证、写入门禁与网络边界 |
| [可观测性](architecture/observability) | 事件、审计、日志、trace 与运行证据 |
| [日志架构](architecture/logging) | 五域日志目录、容量保护和排障 |
| [数据目录结构](architecture/data-directory) | 存储根、用户区/平台区和备份 |
| [文档治理与证据等级](architecture/documentation-governance) | 文档类型、命名规则和事实来源优先级 |
| [架构与数据索引](architecture/index) | 架构章节导航和子域入口 |
| [科研能力与证据边界](research/evidence-boundaries) | 成熟度口径、M1–M3 与门禁状态 |
| [数据发现与获取](research/data-discovery) | 寻宝鼠、下载三来源与只读证据 |
| [Dataset 与 Handoff](research/dataset) | Dataset 七表、版本冻结和 Flow 交接 |
| [科研交付链](research/delivery) | 项目成果、证据、Manifest 与导出 |
| [报告体系](research/reports) | 科学报告、可复现性报告和交付包 |
| [科研计划与科研闭环](research/plan-and-loop) | PLAN_ONLY 计划、工作区归档与 Notebook |
| [科研链路索引](research/index) | 科研页面导航 |
| [Docker 部署](deployment/docker-deployment) | 主栈、Worker 和生产部署 |
| [部署与运维索引](deployment/index) | 部署模式和常用入口 |
| [代码更新与回滚](deployment/update-rollback) | 刷新、重建和回滚 |
| [生产环境检查清单](deployment/production-checklist) | 发布前检查和 401 排障 |
| [开启 Multi-Agent 与 AgentTeams](deployment/agentteams-enablement) | 协作能力灰度启用 |
| [API 设计约定](development/api-design) | 路由、DTO、错误和分页约定 |
| [生信工具接入指南](development/bio-tool-guide) | 工具注册和图形工具闭环 |
| [数据库迁移](development/database-migrations) | Alembic 命令、多 head 与漂移检查 |
| [分析流程扩展](development/flow-extension) | Flow YAML、映射、热重载与固定工具 |
| [前端规范](development/frontend-conventions) | Vue、Naive UI 和工具页约定 |
| [开发规范索引](development/index) | 开发入口和最低验证 |
| [模块设计与接入](development/module-design) | 新模块设计模板和评审问题 |
| [项目结构](development/project-structure) | 后端、前端和配置目录 |
| [AI 助手与工作台](features/ai-chat) | SSE 对话、Agent、工具和工作台 |
| [AI 多 Agent 协作](features/ai-collaboration) | 四种协作形态与 AgentTeams |
| [L1 生信工具箱](features/toolbox) | 工具注册表、配置与 ToolBridge |
| [ATAC-seq 分析](features/atac-seq) | ATACFlow 分析步骤和参数 |
| [数据下载](features/downloads) | 三来源下载、FileRecord 与运行门禁 |
| [功能特性索引](features/index) | 面向用户的功能导航 |
| [实验室知识库](features/knowledge-base) | Markdown 同步、版本和检索 |
| [系统发育树构建](features/phylogenetic-tree) | MSA、建树和任务 API |
| [参考基因组与数据库](features/reference-database) | 参考数据离线构建和注册 |
| [RNA-seq 分析](features/rna-seq) | 样本设计、QC 和差异分析提示 |
| [云端沙盒终端](features/sandbox-terminal) | 终端会话、镜像和隔离边界 |
| [流程监控面板](features/workflow-monitor) | 模板、API 和实时事件 |
| [分析流程与工作流](features/workflows) | 声明式 Flow 和提交链路 |
| [常用命令](operations/common-commands) | Makefile 命令速查 |
| [运维操作索引](operations/index) | 数据目录和日志入口 |
| [问题排查](operations/troubleshooting) | 登录、任务、Worker、AI 排障 |
| [环境变量与密钥](security/env-variables) | 密钥和配置分组 |
| [安全加固清单](security/hardening-checklist) | 生产安全检查 |
| [安全索引](security/index) | 安全原则和必读页面 |

## 文档边界

- Wiki 描述稳定用法和当前可验证的能力，不复制临时施工记录、内部提示词或未实施提案。
- `ARCHITECTURE_DESIGN/` 记录系统边界、数据流和修改门禁；`docs/knowledge/` 记录实验室 SOP 与方法知识；`docs/` 其他目录是历史档案。
- 页面中的命令默认从仓库根目录执行。端口、路径和开关以当前 `.env`、Compose 文件和 Makefile 为准。
- Wiki 正文会被知识库集合自动发现；`_Sidebar.md` 仅用于导航，不进入检索正文。

## 更新与同步

修改 Wiki 后，在可用的 Web/数据库环境中运行：

```bash
make sync-knowledge
```

只重建已发布文档的分块和向量时运行 `make knowledge-reindex`。详细规则见[Wiki 维护与知识库同步](documentation-maintenance)。
