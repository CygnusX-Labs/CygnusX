# CygnusX Wiki 总览

本目录是 CygnusX 面向用户、开发者和运维人员的操作文档集合。它回答“现在如何使用和维护平台”，不替代代码、配置、迁移和架构基线。涉及实现边界时，以仓库当前代码和 [`ARCHITECTURE_DESIN/README.md`](../ARCHITECTURE_DESIN/README.md) 指向的 as-built 文档为准。

## 先看哪一页

| 你的目标 | 推荐入口 |
| --- | --- |
| 第一次启动本地环境 | [快速开始](getting-started/quickstart) |
| 部署到单机或拆分 Worker | [Docker 部署](deployment/docker-deployment) |
| 日常更新、迁移和排障 | [常用命令](operations/common-commands)、[问题排查](operations/troubleshooting) |
| 了解平台如何分层 | [系统架构总览](architecture/overview) |
| 使用 AI、Studio 或协作室 | [AI 助手与工作台](features/ai-chat)、[多 Agent 协作](features/ai-collaboration) |
| 提交 RNA/ATAC 分析 | [分析流程](features/workflows)、[RNA-seq](features/rna-seq)、[ATAC-seq](features/atac-seq) |
| 新增模块、工具或 Flow | [开发规范](development/index)、[模块设计](development/module-design)、[流程扩展](development/flow-extension) |

## 内容地图

### 入门与部署

- [快速开始](getting-started/index)：环境要求、本地开发、Docker 最短路径。
- [首次部署与管理员注册](getting-started/first-time-setup)：`/setup` 初始化和必要密钥。
- [部署与运维](deployment/index)：主栈、Worker、AgentTeams、生产检查和回滚。

### 架构与数据

- [系统架构总览](architecture/overview)：Vue/FastAPI、Agent、Flow、Worker 和存储的数据流。
- [数据目录结构](architecture/data-directory)：配置驱动的数据根、用户区和平台区。
- [日志架构](architecture/logging)：应用、任务、Nginx 和审计日志。

### 开发

- [开发规范](development/index)：API、前端、迁移、Flow 和工具的修改入口。
- [项目结构](development/project-structure)：后端分层、前端目录和配置注册表。
- [模块设计与接入](development/module-design)：新模块的设计和验收清单。

### 功能

- [功能特性](features/index)：AI、知识库、沙盒、下载、参考数据库和分析流程总览。
- [流程监控](features/workflow-monitor)：任务状态、事件和监控 API。

### 运维与安全

- [常用命令](operations/common-commands)：以 `make help` 为准的命令速查。
- [问题排查](operations/troubleshooting)：健康检查、日志、权限和队列问题。
- [安全加固清单](security/hardening-checklist)：生产发布前检查。
- [环境变量与密钥](security/env-variables)：`.env.example` 的配置分组和密钥原则。

## 全部页面索引

下面列出 `wiki/` 中除导航文件外的每一篇正文，新增页面时同步补充本表。

| 页面 | 说明 |
| --- | --- |
| [Home](Home) | Wiki 首页和权威来源入口 |
| [Wiki 维护与知识库同步](documentation-maintenance) | 内容来源、同步和更新规则 |
| [快速开始](getting-started/quickstart) | 本地开发和 Docker 最短路径 |
| [首次部署与管理员注册](getting-started/first-time-setup) | `/setup` 初始化流程 |
| [快速开始索引](getting-started/index) | 入门页面导航和环境要求 |
| [系统架构总览](architecture/overview) | 技术栈、分层和关键数据流 |
| [数据目录结构](architecture/data-directory) | 存储根和备份目录 |
| [日志架构](architecture/logging) | 日志目录、容量保护和排障 |
| [架构与数据索引](architecture/index) | 架构章节导航和阅读边界 |
| [Docker 部署](deployment/docker-deployment) | 主栈、Worker 和生产部署 |
| [部署与运维索引](deployment/index) | 部署模式和常用入口 |
| [代码更新与回滚](deployment/update-rollback) | 刷新、重建和回滚 |
| [生产环境检查清单](deployment/production-checklist) | 发布前检查和 401 排障 |
| [开启 Multi-Agent 与 AgentTeams](deployment/agentteams-enablement) | 协作能力灰度启用 |
| [API 设计约定](development/api-design) | 路由、DTO、错误和分页约定 |
| [生信工具接入指南](development/bio-tool-guide) | 工具注册和图形工具闭环 |
| [数据库迁移](development/database-migrations) | Alembic 命令和多 head 处理 |
| [分析流程扩展](development/flow-extension) | Flow YAML、映射和热重载 |
| [前端规范](development/frontend-conventions) | Vue、Naive UI 和工具页约定 |
| [开发规范索引](development/index) | 开发入口和最低验证 |
| [模块设计与接入](development/module-design) | 新模块设计模板和评审问题 |
| [项目结构](development/project-structure) | 后端、前端和配置目录 |
| [AI 助手与工作台](features/ai-chat) | SSE 对话、Agent、工具和工作台 |
| [AI 多 Agent 协作](features/ai-collaboration) | 多专家、子 Agent 和 AgentTeams |
| [ATAC-seq 分析](features/atac-seq) | ATACFlow 分析步骤和参数 |
| [数据下载](features/downloads) | EBI/NCBI 和云存储下载 |
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
| [安全索引](security/index) | 安全原则和必填变量 |

## 文档边界

- Wiki 页面描述稳定用法和当前可验证的能力，不复制临时施工记录、内部提示词或未实施提案。
- `ARCHITECTURE_DESIN/` 记录系统边界、数据流和修改门禁；`docs/knowledge/` 记录实验室 SOP 与方法知识。
- 页面中的命令默认从仓库根目录执行。端口、路径和开关以当前 `.env`、Compose 文件和 Makefile 为准。
- Wiki 正文会被知识库集合自动发现；`_Sidebar.md` 仅用于导航，不进入检索正文。

## 更新与同步

修改 Wiki 后，在可用的 Web/数据库环境中运行：

```bash
make sync-knowledge
```

只重建已发布文档的分块和向量时运行 `make knowledge-reindex`。详细规则见[Wiki 维护与知识库同步](documentation-maintenance)。

最后核对链接、命令和配置名，并在变更说明中写明适用环境（本地、Docker 或生产）。
