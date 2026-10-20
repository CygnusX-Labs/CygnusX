# 项目结构

CygnusX 采用前后端分离 + DDD 分层 + 配置外置的目录组织方式。后端以 Python 3.11 + FastAPI 为
主，前端为 Vue 3 + TypeScript；流程、Agent、工具和镜像分别由外置配置与子模块管理。

## 顶层目录

```text
OmicHub/
├── src/cygnusx/            # 后端 Python 包（DDD 分层）
├── frontend/               # 前端 Vue 3 + TS 项目
├── alembic/                # 数据库迁移（schema 唯一事实来源）
├── ARCHITECTURE_DESIGN/    # 唯一架构权威库（as-built / 规范 / 提案 / deprecated）
├── docs/                   # 历史档案 + 知识库源文档（docs/knowledge）
├── deploy/                 # compose、镜像构建、runtime-images/studio/sandbox、image-mapping
├── data/                   # 运行时注册与 Agent 配置（CygnusX.yaml / ai/ / MODULE_LOCKED.yaml）
├── flows/                  # 声明式分析流程 catalog（*.yaml）
├── pipelines/              # Snakemake 流程子模块（RNAFlow / ATACFlow / scrna / EBIDownload / tools）
├── Protocol/               # 生效协议（file_protocol / FlowFrame 子模块 / 镜像构建规范）
├── tool_configs/           # 生信工具双注册表与工具专属配置
├── mcp-server/             # 独立 FastMCP 外部通道
├── integrations/agentteams/# Bridge / Gateway 独立子工程与 CI
├── scripts/                # 校验、对账与 cygnusxtools CLI
├── tests/                  # 单元 / 集成 / E2E 测试
├── benchmarks/             # 基准与评估脚本
├── refdata/                # 参考数据登记（reference_genomes.yaml）
├── skills/                 # 生信技能源与安装指南
├── wiki/                   # 本 Wiki
├── evidence/               # 运行证据（不入提交）
└── logs/                   # 运行日志（不入提交）
```

## 后端结构（`src/cygnusx/`）

```text
src/cygnusx/
├── api/v1/                 # 表示层：40+ FastAPI 路由（含 admin/）
├── application/            # 应用层：用例服务 + schemas DTO（150+ 服务）
├── domain/                 # 领域层：ai / flow / mas / team / sandbox / skill / cookie / festival …
├── infrastructure/         # 基础设施适配器
│   ├── database/           # SQLAlchemy ORM + 仓储（vector 检索）
│   ├── ai_provider/        # 自研 OpenAI-compatible Provider
│   ├── celery_app/         # Celery 任务与 reconcile-only 长任务
│   ├── sandbox/            # Chat 沙箱与 Studio 运行时
│   ├── mcp/                # 内置 Preset / 外部 MCP / 工具契约
│   ├── skills/             # 技能扫描、索引与调用
│   ├── storage/            # 统一存储路径与对象存储
│   ├── web_search/         # 联网检索
│   ├── yaml/ config/       # YAML 加载与 Agent 装配
│   └── execution/          # Snakemake 执行与 GenericFlowBuilder
├── core/                   # 横切：config / security / logging / exceptions / 指标
├── middleware/             # Auth / RBAC / ModuleGate / Cookie / Audit / RateLimit
├── tools/                  # 生信工具注册、schema 编译、Celery tasks
├── task_queue/             # RocketMQ worker 等异步消费路径
└── reference_genomes/      # 参考基因组 SQLite/FTS5 模块（独立于 Alembic）
```

分层约定：

- **路由层**只做参数解析、依赖注入、认证/权限调用与 HTTP 状态码映射。
- **应用层**负责用例编排、事务边界和跨领域协作。
- **领域层**承载业务规则与状态机，不依赖 Web/ORM 细节。
- **基础设施层**实现 ORM、Redis、文件、Docker、第三方 API 等具体技术。

## 前端结构（`frontend/src/`）

```text
frontend/src/
├── api/                    # 类型化 HTTP 调用（axios 实例，baseURL /api/v1）
├── types/                  # TypeScript DTO / 领域类型
├── views/                  # 页面与路由入口
├── components/             # 可复用组件（ai-chat / admin / sandbox / knowledge / bio-tools / task）
├── composables/            # 可复用状态与副作用
├── engine/                 # 聊天渲染与领域展示引擎
├── stores/                 # Pinia 全局状态
├── router/                 # 路由配置（模块守卫）
├── layouts/                # 页面布局
├── config/ directives/     # 前端配置与指令
├── mock/                   # 开发 mock
├── styles/                 # 全局样式与 CSS 变量
└── utils/                  # 纯函数工具与图表处理器
```

前端约束：TypeScript strict、`@/*` alias、API 调用集中在 `src/api/`、DOM 测试使用
`// @vitest-environment jsdom` 头注释。前端无 eslint/prettier，风格靠 review。

## 配置与保护资产

| 路径 | 用途 | 约束 |
|---|---|---|
| `data/CygnusX.yaml` | 平台注册中心与 `agents.enabled` | 新增 Agent 必须与 YAML 两处同时登记 |
| `data/MODULE_LOCKED.yaml` | 18 模块注册唯一数据源 | 后端启动硬校验 + 前端路由守卫共同消费 |
| `data/ai/` | Agent YAML、prompts、skills、runtime_images、flows 第二注册表 | 提示词须经管理端 API 发布才写入 DB |
| `deploy/image-mapping.yaml` | 镜像清单唯一权威源（当前 17 个，以清单与 `make validate-image-mapping` 为准） | tag 变更需 6 处同步，禁用 `latest` |
| `flows/*.yaml` | 分析流程 catalog | 六段 schema，`extra="forbid"` |
| `Protocol/FlowFrame/` | Flow 架构强制规范 v2.0（子模块） | 流程契约变更必须评审 |
| `Protocol/file_protocol.md` | 用户目录协议 | 路径必须走工厂方法与目录链登记 |
| `tool_configs/tools_schema.yaml` | LLM 工具 schema | mtime 热重载 |
| `mcp-server/` | 外部 MCP 通道 | 确认契约与内置表面等价 |

## 子模块与独立工程

- `pipelines/RNAFlow`、`ATACFlow`、`scrna`、`EBIDownload`、`tools`、`Protocol/FlowFrame` 为 Git
  子模块；父仓只记录指针，内部改动须在各自仓库提交。
- `mcp-server/` 有独立 pyproject 与入口。
- `integrations/agentteams/bridge`、`gateway` 有各自 pyproject 与独立 CI job。
- `docs/app/` 是独立的 React 档案站，不是主前端。

## 相关页面

- [开发规范](index)
- [数据库架构](../architecture/database)
- [存储与目录](../architecture/storage)
- [文档治理](../architecture/documentation-governance)
