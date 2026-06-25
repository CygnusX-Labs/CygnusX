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

- [x] **用户认证闭环** (docs/modules/03_api_design.md) ✅ 2026-06-25 验证通过
  - [x] auth.py 实现登录/注册/刷新令牌端点
  - [x] UserModel 完整 ORM (含 workspace ForeignKey 关联)
  - [x] UserRepositoryImpl (SQLAlchemy 实现)
  - [x] UserService/AuthService 编排登录用例
  - [x] JWT 中间件接入 main.py
  - [x] 前端登录页面 + auth store 完整逻辑
  - [x] 注册审批机制: 新用户默认 status=pending, 管理员审批后变 active 才可登录
  - [x] 用户管理 API (admin/users.py): GET 列表 | PUT /{id}/approve | PUT /{id}/reject | PUT /{id}/role
  - [x] 前端用户管理页 (AdminUserManagementView.vue): 审批/拒绝/角色切换
  - [x] 侧边栏菜单改为 computed 动态渲染 (admin 角色可见"系统管理"子菜单)
  - [x] 修复: session.py 模型未注册导致建表失败
  - [x] 修复: router/index.ts/g isLoggedIn() 误调用 computed
  - [x] 修复: DefaultLayout.vue FileText → DocumentText (ionicons5 改名)
  - [x] 修复: main.ts 未全局注册 naive-ui 导致登录页组件不渲染
  - [x] 修复: n-input-password 组件不存在 → n-input type=password (LoginView/RegisterView)
  - [x] 修复: nginx index.html 无禁缓存头导致浏览器加载旧 JS (404)
  - [x] 修复: DashboardView 健康检查路径错误 (apiClient /../health → axios /health)
  - [x] 修复: DashboardView 快速开始按钮未绑定 @click 跳转事件
  - [x] 修复: DefaultLayout 侧边栏 AI 助手菜单重复 + 管理员菜单缺失

- [x] **YAML 配置中心** (docs/modules/04_yaml_schema.md) ✅ 2026-06-25 前后端闭环
  - [x] FlowDomainService.parse_yaml 完整实现 (services.py)
  - [x] YAML → FlowConfig 转换 (entities.py 完整 Pydantic v2 模型)
  - [x] DAG 依赖图校验 (find_condition_cycle 三色 DFS 检测 condition 循环依赖)
  - [x] FlowRepositoryImpl (FileSystemFlowRepository 文件系统仓储 + 线程安全缓存)
  - [x] `/api/v1/flows/{flow_id}/schema` 返回 JSON Schema (含顶层 FlowConfig Schema)
  - [x] YAML 热重载接口 (POST /api/v1/flows/reload)
  - [x] 完整 value_objects: ParameterTypeEnum + 6 Config 子模型 + ExecutionConfig + SampleSheetConfig + FlowMeta
  - [x] 完整 entities: ConditionRule (简单+AND/OR 嵌套) + Parameter (类型校验) + FlowConfig (唯一性+条件引用校验) + FlowDefinition 聚合根
  - [x] condition.py: ConditionEvaluator (11 运算符) + ConditionalValidator (可见参数+必填校验)
  - [x] schemas/flow.py: FlowListItemDTO/FlowDetailDTO/FlowListResponse/FlowReloadResponse + JSON Schema 导出
  - [x] api/v1/flows.py: 5 端点 (GET / | GET /schema | POST /reload | GET /{id} | GET /{id}/schema)
  - [x] flows/rna_seq.yaml 示例配置 (覆盖全部参数类型+条件渲染+Group+Section)
  - [x] docker-compose 挂载 flows 目录 + config.py 新增 flow_yaml_dir
  - [x] 前端 DynamicForm 组件 (基于 Naive UI) — types/schema.ts + useConditionEvaluator + DynamicForm/FormField/RepeatableGroup/CollapsibleSection，已接入 FlowSubmitView.vue
  - [x] 修复: uvicorn 运行时 /flows 路由 404 (重启容器后路由正常，返回 401 需认证即证明路由已注册)

- [x] **任务执行闭环** (docs/modules/01_architecture_overview.md §4.4) ✅ 2026-06-25 端到端验证通过
  - [x] TaskRepositoryImpl (get_by_id/list_by_user/save/delete/append_log + 模型转换)
  - [x] TaskService 提交任务用例 (参数快照锁定 + RNAFlow builder + Celery 投递 + 状态推进)
  - [x] Celery analysis 任务接入 LocalSnakemakeExecutor (状态流转 + stdout/stderr 日志记录)
  - [x] Redis Pub/Sub → WebSocket 实时日志推送 (pubsub.py + tasks.py WebSocket 端点)
  - [x] 前端任务详情页 + 实时日志流 (TaskDetailView.vue + WebSocket 连接)
  - [x] Snakemake DAG 可视化 (generate_dag SVG/DOT + 前端渲染)
  - [x] 修复: TaskService.submit 重复调用 flow_config_to_detail 导致 500
  - [x] 修复: Celery worker session 未 commit 导致状态/日志丢失 (ROLLBACK)
  - [x] 修复: _update_model 覆盖 append_log 写入的日志 (logs 不再由 save 覆盖)
  - [x] 修复: append_log 未存 timestamp 导致 _to_entity 转换报错

### 优先级 P1 — 饼干积分系统（🍪 Cookie）✅ 2026-06-25 端到端验证通过

> 文档: docs/modules/12_cookie_backend.md + 13_cookie_frontend.md + 14_cookie_integration.md
> 架构适配: 设计文档用 ORM 贫血模型，本项目适配为 DDD 模式 (Pydantic 实体 + 仓储接口 + Python 端统计维护替代 SQL 触发器)

#### 后端 — 领域层 (domain/cookie/)
- [x] CookieAccount 聚合根 + CookieTransaction/CookiePricing/ConsumptionLog/LedgerEntry 实体
- [x] TransactionType/AccountStatus/PricingType/PricingUnit/BillingItem 值对象 (earn/spend/adjust/refund/freeze/unfreeze)
- [x] ICookieAccountRepository / ICookieTransactionRepository / ICookiePricingRepository / IConsumptionLogRepository / ILedgerRepository 仓储接口
- [x] CookieAccount.apply_transaction() — Python 端维护统计 (替代 SQL 触发器 fn_update_account_stats)

#### 后端 — 基础设施层 (infrastructure/database/)
- [x] 5 张表 ORM 模型: cookie_accounts / cookie_transactions / cookie_pricing / cookie_consumption_logs / cookie_ledger
- [x] 索引设计 (idx_txn_user_created 覆盖索引、idx_pricing_query 部分索引、idx_txn_source 等)
- [x] Python 端统计维护 (apply_transaction 替代 SQL 触发器) + 注册建户 (get_or_create_account 替代 fn_create_cookie_account_on_signup)
- [x] SqlAlchemyAccountRepository / SqlAlchemyTransactionRepository / SqlAlchemyPricingRepository / SqlAlchemyConsumptionLogRepository / SqlAlchemyLedgerRepository 仓储实现
- [ ] Alembic 迁移脚本 (当前用 create_all 自动建表，生产环境需迁移)

#### 后端 — 应用层 (application/)
- [x] CookieService 核心服务: check_balance / pre_deduct / settle (多退少补) / refund / freeze / unfreeze / suspend / adjust
- [x] PricingEngine 定价计算引擎: 按 flow_category + resource_type + priority 匹配 + 时段生效判断
- [x] Pydantic DTO: CookieAccountDTO / CookieTransactionDTO / CookiePricingDTO / CostEstimateDTO / CookieStatsDTO
- [x] TaskCookieConsumer 结算服务 (Celery 回调中调用 on_complete/on_cancel)

#### 后端 — API 路由 (api/v1/)
- [x] 用户端 cookies.py: GET /cookies/account | /transactions | /pricing | /estimate | /balance-check
- [x] 管理端 admin/cookies.py: GET /admin/cookies/accounts (JOIN users 返回用户名/邮箱) | POST /adjust | PUT /accounts/{id}/freeze|unfreeze|suspend | GET /transactions | /stats | /pricing (CRUD)
- [x] 管理端 admin/users.py: GET /admin/users 用户列表 | PUT /{id}/approve 审批 | PUT /{id}/reject 拒绝 | PUT /{id}/role 角色切换
- [ ] CookieRequiredMiddleware 消费拦截中间件 (当前通过 TaskCookieConsumer 在服务层集成，未用独立中间件)
- [x] TaskCookieConsumer — 任务提交前预估+预扣，完成时结算，取消时退还
- [ ] SandboxCookieConsumer — 沙盒启动前检查，运行中按分钟计费 (依赖 P2 沙盒)
- [x] config.py 新增: enable_cookie_system / initial_cookie_balance / cookie_sandbox_base_cost

#### 集成点 (依赖任务闭环 P0 + 沙盒 P2)
- [x] 集成点#1: 用户注册自动建户 + 赠送 INITIAL_COOKIE_BALANCE (100🍪) — auth.py register 端点
- [x] 集成点#2: 任务提交注入 Cookie 检查 + 预扣 (余额不足返回 400 BusinessError) — task_service.submit
- [x] 集成点#3: Celery 任务完成回调结算 (多退少补) — analysis.py _execute_snakemake
- [x] 集成点#4: 任务取消退还预扣饼干 — task_service.cancel_task
- [ ] 集成点#5: 沙盒启动前余额检查 + 预扣基础费用 (依赖 P2 沙盒)
- [ ] 集成点#6: 沙盒关闭结算最终费用 (依赖 P2 沙盒)
- [ ] 集成点#7: Celery Beat 每分钟沙盒扣费，余额不足自动停止 (依赖 P2 沙盒)
- [ ] 集成点#8: AI Agent 提交任务前检查余额 (依赖 P2 AI)

#### 前端 (frontend/src/)
- [x] types/index.ts — TS 类型定义 (CookieAccount/Transaction/Pricing/CostEstimate/CookieStats)
- [x] stores/cookie.ts — Pinia store (余额/流水/预估)
- [ ] composables/useCookieWebSocket.ts — 实时余额变更推送 (store 中预留 updateBalanceFromWebSocket)
- [x] components/CookieBalanceBadge.vue — 全局余额徽章 (顶栏，已接入 DefaultLayout)
- [x] views/CookieAccountView.vue — 用户账户页 (余额统计/流水列表)
- [x] views/AdminCookieManagementView.vue — 管理后台账户管理 (列表显示用户名+邮箱/调整/冻结/解冻)
- [x] views/AdminCookiePricingView.vue — 定价策略管理 (CRUD + Modal)
- [x] views/AdminUserManagementView.vue — 用户管理 (审批通过/拒绝/角色切换)
- [ ] views/AdminCookieTransactionsView.vue — 全局交易流水审计 (当前在管理页内嵌)
- [ ] TaskSubmitView.vue 集成饼干预估 (防抖 500ms 调 /estimate)
- [x] 路由配置: /cookies (用户) + /admin/users + /admin/cookies/accounts + /admin/cookies/pricing (管理员)
- [x] DefaultLayout 侧边栏: computed 动态菜单, admin 角色可见"系统管理"子菜单组 (用户管理/饼干账户管理/饼干定价管理)

#### 部署与运维
- [x] config.py 新增 cookie 相关配置项 + enable_cookie_system 开关
- [x] scripts/init_cookies.py — 初始化默认定价策略脚本
- [x] cookie 系统开关 ENABLE_COOKIE_SYSTEM=false 时全链路跳过 (TaskCookieConsumer 检查)
- [ ] 监控: 余额异常告警 + 流水对账 (cookie_ledger 日终快照)

### 优先级 P2 — AI Copilot 与沙盒

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

### 优先级 P3 — 生产化

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

### 优先级 P4 — 优化与运维

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
