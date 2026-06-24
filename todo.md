# OmicHub 开发进度 Todo

> 基于 `docs/` 架构设计文档，逐步完善项目骨架。
> 更新日期：2026-06-25

---

## 已完成

### 1. 项目骨架搭建
- [x] Python 项目结构 (src layout + uv + pyproject.toml)
- [x] 前端 Vue 3 骨架 (Vite + TypeScript + Naive UI + Pinia)
- [x] DDD 六域分层目录结构
- [x] Docker Compose 部署配置 (7 个服务全部 healthy)
- [x] Alembic 数据库迁移配置
- [x] pytest 测试骨架
- [x] Makefile 常用命令 (uv run 前缀)
- [x] .env.example 环境变量模板
- [x] CLAUDE.md 项目指南
- [x] README.md 项目说明

### 2. 后端核心 (src/omichub/)
- [x] **core/** — config (Pydantic Settings), security (JWT+bcrypt), exceptions, logging (loguru)
- [x] **main.py** — FastAPI 应用工厂 + lifespan + 全局异常处理 + `/health` 端点
- [x] **api/v1/** — 7 个路由占位 (auth/users/flows/tasks/files/ai/mcp) + router 聚合 + deps 依赖注入
- [x] **middleware/** — auth (JWT 校验), rbac (角色装饰器), rate_limit (占位)
- [x] **application/** — services/ (7 个应用服务占位) + schemas/ (7 个 DTO 占位)

### 3. 领域层六域 (domain/)
- [x] **user/** — User 聚合根 + Workspace + Role/UserStatus 值对象 + 仓储接口 + 域服务
- [x] **flow/** — FlowDefinition 聚合根 + FlowParameter/FlowStep + ParamType/UIControl + YAML 解析服务
- [x] **task/** — Task 聚合根 + TaskLog + TaskStatus 状态机 + VALID_TRANSITIONS + 域服务
- [x] **file/** — Sample 聚合根 + DataFile + ResultArchive + FileType + 校验和计算
- [x] **ai/** — Conversation 聚合根 + Message + ContextWindow + RoleType + 上下文压缩服务
- [x] **mcp/** — MCPServer 聚合根 + MCPToolRegistry + Transport/ServerStatus + 工具路由服务

### 4. 基础设施层 (infrastructure/)
- [x] **database/** — SQLAlchemy DeclarativeBase + TimestampMixin + 异步 session + UserModel 示例
- [x] **cache/** — Redis 异步客户端 (单例)
- [x] **celery_app/** — Celery 实例 + 配置 + analysis 任务 (snakemake 执行 + 定时清理)
- [x] **ai_provider/** — LLMProvider 抽象接口 + KimiProvider 适配器 (流式 SSE)
- [x] **execution/** — LocalSnakemakeExecutor (subprocess) + RemoteSnakemakeExecutor (HTTP)

### 5. Docker 部署 (deploy/docker/)
- [x] Dockerfile (后端多阶段构建 + uv)
- [x] Dockerfile.frontend (前端构建 + Nginx)
- [x] docker-compose.yml (7 服务: nginx/web/worker/beat/flower/db/cache)
- [x] docker-compose.prod.yml (生产 override)
- [x] nginx.conf (API 代理 + WebSocket + Flower 代理)
- [x] 端口冲突修复 (nginx → 8888)
- [x] 容器健康检查 (各服务自定义 healthcheck)
- [x] 开发环境 src 热重载挂载

### 6. 前端骨架 (frontend/)
- [x] package.json + vite.config.ts + tsconfig
- [x] main.ts + App.vue (NConfigProvider 全局配置)
- [x] router/index.ts (5 个路由: dashboard/flows/tasks/files/ai)
- [x] layouts/DefaultLayout.vue (NLayout 侧边栏布局)
- [x] api/client.ts (axios 实例 + JWT 拦截器)
- [x] stores/auth.ts (Pinia 认证状态)
- [x] composables/useApi.ts (通用请求封装)
- [x] types/index.ts (API 类型定义)
- [x] views/ 5 个页面占位

---

## 待完善

### 优先级 P0 — 核心功能闭环

- [ ] **用户认证闭环** (docs/modules/03_api_design.md)
  - [ ] auth.py 实现登录/注册/刷新令牌端点
  - [ ] UserModel 完整 ORM (含 workspace 关联)
  - [ ] UserRepositoryImpl (SQLAlchemy 实现)
  - [ ] UserService 编排登录用例
  - [ ] JWT 中间件接入 main.py
  - [ ] 前端登录页面 + auth store 完整逻辑

- [ ] **YAML 配置中心** (docs/modules/04_yaml_schema.md)
  - [ ] FlowDomainService.parse_yaml 完整实现
  - [ ] YAML → FlowDefinition 转换
  - [ ] DAG 依赖图校验 (拓扑排序检测环)
  - [ ] FlowRepositoryImpl
  - [ ] `/api/v1/flows/{id}/schema` 返回 JSON Schema
  - [ ] 前端 DynamicForm 组件 (基于 Naive UI)
  - [ ] YAML 热重载接口

- [ ] **任务执行闭环** (docs/modules/01_architecture_overview.md §4.4)
  - [ ] TaskRepositoryImpl
  - [ ] TaskService 提交任务用例 (参数快照锁定)
  - [ ] Celery analysis 任务接入 LocalSnakemakeExecutor
  - [ ] Redis Pub/Sub → WebSocket 实时日志推送
  - [ ] 前端任务详情页 + 实时日志流
  - [ ] Snakemake DAG 可视化

### 优先级 P1 — AI Copilot 与沙盒

- [ ] **AI 对话 WebSocket** (docs/modules/09_sandbox_architecture.md)
  - [ ] ai.py WebSocket 端点完整实现 (非 echo)
  - [ ] ConversationRepositoryImpl
  - [ ] AIService 编排对话 + 上下文管理
  - [ ] KimiProvider 流式响应接入
  - [ ] 前端 AIChat 组件 (Markdown 渲染 + 流式打字机)
  - [ ] Tool Use 协议 (submit_task/query_status/list_samples)

- [ ] **代码执行沙盒** (docs/modules/08_tech_selection.md)
  - [ ] Docker 预热容器池管理器
  - [ ] 沙盒镜像 Dockerfile (Bioconda + scanpy/seurat)
  - [ ] WebSocket 代码执行协议
  - [ ] 前端 CodeMirror 6 编辑器组件
  - [ ] ECharts GL 图表渲染 (UMAP/热图)
  - [ ] 会话亲和性 + 30min 超时回收

- [ ] **MCP 集成** (docs/modules/11_integration_fusion.md)
  - [ ] MCPServerRepositoryImpl
  - [ ] MCP Client (Python MCP SDK) 生命周期管理
  - [ ] 四大预设 MCP 服务 (文献/基因组/代码/知识库)
  - [ ] 工具发现 + 调用路由 + 错误隔离
  - [ ] `/api/v1/mcp/servers` CRUD 端点

### 优先级 P2 — 生产化

- [ ] **数据库迁移** (docs/modules/02_database_schema.md)
  - [ ] 完整建表 SQL (六域所有表)
  - [ ] JSONB 字段标注
  - [ ] 索引设计
  - [ ] Alembic 初始迁移

- [ ] **安全加固** (docs/modules/01_architecture_overview.md §4.5)
  - [ ] RBAC 中间件完整实现 (数据库查角色)
  - [ ] RateLimitMiddleware 接入 Redis 滑动窗口
  - [ ] 工作空间数据隔离 (user_id 自动过滤)
  - [ ] 敏感信息脱敏 (AI 对话中的品种名)
  - [ ] 审计日志表 + 中间件

- [ ] **文件管理** (docs/modules/03_api_design.md)
  - [ ] 文件上传 (分块 + 断点续传)
  - [ ] SampleRepositoryImpl
  - [ ] 结果归档过期清理 (Celery Beat 定时任务)
  - [ ] 前端文件管理页 + 上传组件

- [ ] **远程执行模式** (docs/modules/01_architecture_overview.md §4.4)
  - [ ] 远程 Snakemake Executor 服务 (集群头节点 FastAPI 副进程)
  - [ ] Slurm/SGE 作业翻译
  - [ ] 结果回传 (rsync/HTTP)

### 优先级 P3 — 优化与运维

- [ ] **监控可观测性**
  - [ ] Prometheus 指标暴露
  - [ ] Grafana 仪表盘模板
  - [ ] 结构化日志 + Loki 聚合
  - [ ] API 请求追踪 (OpenTelemetry)

- [ ] **前端完善**
  - [ ] 各域页面完整实现 (Flows/Tasks/Files/AI)
  - [ ] 全局错误处理 + 加载态
  - [ ] 响应式布局适配
  - [ ] 暗色模式

- [ ] **测试覆盖**
  - [ ] 六域单元测试
  - [ ] API 集成测试
  - [ ] E2E 测试 (Playwright)
  - [ ] CI/CD 流水线

- [ ] **文档与交付**
  - [ ] API 文档自动生成 (OpenAPI)
  - [ ] 部署手册
  - [ ] 运维 runbook
  - [ ] 用户使用手册

---

## 技术决策记录

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 包管理 | uv | 极快，2024-2025 社区主流 |
| 2 | Python 版本 | 3.11 | pyproject.toml 约束，Docker 镜像一致 |
| 3 | 项目结构 | src layout | PEP 621 标准，避免 import 冲突 |
| 4 | Nginx 端口 | 8888 | 宿主机 80 被 ipsa 占用 |
| 5 | 开发模式 src 挂载 | web/worker/beat | 热重载，无需 rebuild 镜像 |
| 6 | Beat schedule | crontab 对象 | 不能用字符串，Celery 要求 crontab 实例 |
| 7 | 健康检查 | 各服务自定义 | slim 镜像无 pgrep/curl，需 CMD-SHELL |
