# 系统架构总览

CygnusX 是面向生命科学的智能科研平台。它把面向用户的控制面、可扩展的计算 Worker、共享存储和 AI/知识能力分开部署，以便从单机逐步扩展到跨机器、HPC 或 Kubernetes。

> **当前定位**：平台主干、版本化 Flow、Agent/Studio/AgentTeams 执行路径、报告与项目交付机制已实现；当前源码下“数据发现 → 获取 → RNAFlow 计算 → 科学 BioReport → 独立复现”的端到端链路**尚未验收**。状态口径见[科研能力与证据边界](../research/evidence-boundaries)。

## 一页平台图

```text
浏览器 / Vue 3 / Pinia / Naive UI
        │ HTTPS · SSE · REST
        ▼
Nginx ──► FastAPI (/api/v1)
            ├─ middleware/    身份、RBAC、模块门禁、Cookie、审计、限流
            ├─ api/v1/        REST / SSE 入口
            ├─ application/   用例服务、DTO、事务编排
            ├─ domain/        限界上下文与状态机
            └─ infrastructure/ DB、缓存、队列、存储、模型、沙箱、MCP
        │
        ├─ AI Runtime：Agent 装配 → LangGraph/Legacy ReAct → Provider → Tool/MCP/Skill
        ├─ 沙箱：Chat 轻量池 / Studio 一会话一容器
        ├─ 队列：Celery Worker / 可选 RocketMQ Worker
        ├─ 计算：Snakemake / FlowFrame / 分析镜像 / AgentTeams Worker
        └─ 数据：PostgreSQL+pgvector / Redis / MinIO/S3 / 共享存储
```

## 技术栈

| 层级 | 当前实现 |
| --- | --- |
| 前端 | Vue 3、TypeScript（strict）、Vite 5、Pinia、Naive UI；图表使用 ECharts/Plotly |
| 后端 | Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2.0（asyncpg）、DDD 分层 |
| 数据与检索 | PostgreSQL + pgvector；可选只读副本、备份与指标验收 |
| 异步任务 | Celery 为默认队列；可按配置启用 RocketMQ Worker |
| 分析执行 | Snakemake、独立 Worker / 运行时镜像、共享存储 |
| AI | 自研 OpenAI-compatible Provider、SSE、MCP、Skill、Agent 配置与工作台 |
| 部署 | Docker Compose 主栈 + Worker 栈；支持跨机器与逐步扩展 |

## 分层与职责

| 层 | 目录 | 职责 |
| --- | --- | --- |
| HTTP 层 | `src/cygnusx/api/v1/` | 路由、鉴权依赖、DTO 校验、SSE 出口 |
| 应用层 | `src/cygnusx/application/` | 用例服务、事务边界、跨聚合编排 |
| 领域层 | `src/cygnusx/domain/` | 业务规则、状态机、值对象与协议 |
| 基础设施层 | `src/cygnusx/infrastructure/` | 数据库、缓存、队列、存储、模型 Provider、沙箱、MCP |
| 横切层 | `src/cygnusx/core/`、`middleware/`、`tools/` | 配置、日志、异常、中间件、生信工具注册 |

前端不直接访问数据库或 Worker；路由层只负责请求校验和授权，业务规则放在应用与领域层，外部系统通过基础设施适配层隔离。

## 四种执行形态

| 形态 | 入口 | 执行路径 | 关键边界 |
| --- | --- | --- | --- |
| 普通 Chat/Agent | `/api/v1/chat/stream` | `chat_langgraph`（默认）/ `chat_legacy`（逃生舱） | 受保护轮次、工具双通道、事件落库 |
| OmicStudio | Studio 前端 + Studio API | `studio_chat_loop` | 一会话一容器、capability 裁剪、工作区文件 |
| AgentTeams | 协作室 API/网关 | `agentteams_worker_react` / `agentteams_tool_execution`（Manager 会诊也记录为 `agentteams_worker_react`） | Manager/Worker 分离、独立子会话、禁止项 |
| Pipeline/Worker | 分析中心、任务 API | Celery `run_snakemake` | 声明式 Flow、九步提交链、reconcile-only 长任务 |

五条实际发射路径的完整登记、降级语义和事件契约见 [Agent 运行时](agent-runtime)；`agentteams_manager_consultation` 为未发射的规划值。Flow 提交链见 [Flow 运行时](flow-runtime)。

## 关键数据流

- **交互请求**：浏览器 → Nginx → FastAPI → 应用服务 → PostgreSQL / 存储。
- **分析任务**：API/确认门 → `TaskService.submit()` → 队列 → Worker → Snakemake/运行时镜像 → 共享存储 → 任务与产物记录。
- **AI 对话**：浏览器 → SSE → Agent 服务 → Provider、知识库、MCP/Skill → 结构化事件与消息记录。
- **知识库更新**：Markdown 源内容 → 同步脚本 → 数据库版本 → 分块/向量索引 → `knowledge_search`。
- **科研交付**：Project/Run/Case/Artifact → Evidence/Manifest → 报告/导出 Job → 冻结 ZIP 与授权下载。

## 关键资产与注册表

| 资产 | 位置 | 作用 |
| --- | --- | --- |
| 模块注册表 | `data/MODULE_LOCKED.yaml` | 前后端共同消费的模块开关，后端启动硬校验 |
| Agent 注册表 | `data/ai/*.yaml`、`data/CygnusX.yaml` | Agent 声明、工具包、Skill、MCP 绑定与启用列表 |
| Agent 提示词 | `data/ai/prompts/` | 提示词注册表与共享片段 |
| 平台 Skill | `data/ai/skills/`、`data/ai/skill_marketplace/` | 已安装技能与内置市场 |
| 流程定义 | `flows/*.yaml` | 六段 FlowConfig，mtime 热重载 |
| 流程代码 | `pipelines/`（子模块） | RNAFlow、ATACFlow、CountsDEGFlow 等 |
| 工具配置 | `tool_configs/` | 前端卡片、LLM Schema 与各工具专属配置 |
| 镜像清单 | `deploy/image-mapping.yaml` | 运行时镜像的唯一权威源（当前 17 个，以清单与 `make validate-image-mapping` 为准） |
| 文档索引 | `ARCHITECTURE_DESIGN/README.md` | 架构权威库入口 |
| 用户帮助 | `wiki/`、`docs/knowledge/` | 操作文档与实验室知识 |

## 证据与运行边界

平台把“实现”“测试”“运行验证”“端到端验证”“生产准入”分开记录。当前需要特别区分的边界：

- 下载与 Agent 写操作：`AgentToolGateway` 源码中 `WRITE_RUNTIME_ACCEPTED=False`，`tool_gateway_read_enabled` 默认关闭；
- Dataset：`DATASET_IMPORT_WRITE`、`ANALYSIS_SUBMIT_FROM_DATASET`、`COUNTS_DEG_FLOW_ENABLED` 默认 false，Handoff `worker_paths_verified=false`；
- 科研交付：独立导出 Job 与 Manifest 已接入并有隔离验证，真实 PG/Celery/S3/浏览器验收 BLOCKED；
- 科学报告：BioReport 与平台报告适配器是两条路径；RI09.5 只证明了**项目汇总报告**交付，不等于科学分析报告。

这些门禁由代码常量、功能开关和验收流程共同构成；**不要通过改环境变量来宣称已解锁**。

## 相关页面

- [架构与数据索引](index) · [Agent 运行时](agent-runtime) · [沙箱与执行隔离](sandbox) · [MCP 体系](mcp)
- [Flow 运行时](flow-runtime) · [数据库基础设施](database) · [存储层](storage)
- [科研能力与证据边界](../research/evidence-boundaries) · [科研交付链](../research/delivery)
