# OmicHub 开发进度 Todo

> 基于 `docs/` 架构设计文档，逐步完善项目骨架。
> 更新日期：2026-06-28 (Cherry Studio SSE 架构 + AI 资源管理中心)

---

## 已完成

### Cherry Studio SSE 架构切换 + AI 资源管理中心 ✅ 2026-06-28

> 端到端验证：`POST /chat/stream` SSE 逐 token 推送（12 文本 token + 61 推理 token），会话/消息持久化到 `chat_sessions`/`chat_messages`，技能 prompt 注入生效，助手 system_prompt 覆盖生效。

- [x] **Part 1：流式聊天 Provider 重构**
  - [x] `litellm_provider.py` 新增 `stream_chat_with_tools()` — 逐 token `StreamEvent` 推送 + `delta.tool_calls` 按 index 累积 + `BadRequestError` 降级非流式
  - [x] `kimi.py` 修复 `is_configured` sync→async + 新增 `stream_chat_with_tools` 降级实现
  - [x] `base.py` 新增 `StreamEvent` dataclass + Protocol `stream_chat_with_tools` 方法签名
  - [x] 修复 `_build_kwargs` 丢失 `stream=True` 导致 litellm 返回 `ModelResponse` 而非异步流的致命 bug
- [x] **Part 2：Skill 后端（技能 prompt 注入）**
  - [x] `domain/skill/` — 完整六域分层（entities / value_objects / repositories / services）
  - [x] `infrastructure/database/models/skill.py` — SkillModel ORM
  - [x] `infrastructure/database/repositories/skill_repository.py` — SqlAlchemySkillRepository
  - [x] `application/schemas/skill.py` — SkillDTO + CreateSkillDTO + UpdateSkillDTO
  - [x] `application/services/skill_service.py` — CRUD + `build_skills_prompt()` + `get_active_skills()` (MAX_ACTIVE_SKILLS=10)
  - [x] `api/v1/admin/skills.py` — AdminRequired CRUD + toggle
  - [x] `api/v1/chat.py` 新增公开 `GET /chat/skills`（仅返回启用技能，供前端插件下拉）
  - [x] Alembic 迁移 `e4f5a6b7c8d9` — skills 表 + ai_conversations.assistant_id + chat_assistants.is_default
- [x] **Part 3：Agent 后端（助手管理）**
  - [x] `ChatAssistantModel` 新增 `is_default` 列
  - [x] `ConversationModel` 新增 `assistant_id` 列
  - [x] `chat_service.py` — `list_all_assistants` / `update_assistant` (含 is_default 联动清除) / `delete_assistant` (builtin 仅停用) / `toggle_assistant` / `set_default_assistant`
  - [x] `schemas/chat.py` — `UpdateAssistantRequest` 新增 `is_default` 字段
  - [x] `api/v1/admin/assistants.py` — AdminRequired CRUD + toggle + set-default
- [x] **Part 4：MCP 管理加固**
  - [x] `api/v1/mcp.py` — ALL endpoints (GET/POST/PUT/DELETE) 改为 `AdminRequired`（防止命令/env 泄露）
  - [x] 新增 `PUT /servers/{id}` 编辑 + `POST /servers/{id}/test` 连通性测试
  - [x] `schemas/mcp.py` — `UpdateMCPServerDTO`
  - [x] `mcp_service.py` — `update_server` + `test_server` 方法
- [x] **Part 5：Cherry Studio SSE 前端（核心架构切换）**
  - [x] 移除 7 个文件的 DEPRECATED 标记（`useChatStream.ts` / `chatSession.ts` / `chatAssistant.ts` / `ChatMessageItem.vue` / `ChatSettingsDrawer.vue` / `types/chat.ts` / `openai_compatible.py`）
  - [x] `KimiLayout.vue` **重写** — 从 WebSocket stores (`useAIStore` + `useAIWebSocket`) 切换到 SSE stores (`useChatSessionStore` + `useChatAssistantStore`)，不再需要 WebSocket 连接/重连逻辑
  - [x] `chat_service.py` SSE `stream_chat()` 添加技能 prompt 注入（与 WebSocket 路径一致）
  - [x] `stores/chat.ts` — `fetchPlugins()` 从 `GET /chat/skills` 加载启用技能，替代硬编码插件列表
  - [x] `alembic/env.py` — 添加 `skill` 模型导入（供 autogenerate 使用）
- [x] **Part 6：AI 资源管理中心前端**
  - [x] `types/index.ts` — Skill + ChatAssistantAdmin 接口
  - [x] `stores/mcp.ts` — createServer/updateServer/deleteServer/testServer
  - [x] `components/admin/McpResourceTab.vue` — MCP CRUD + 连通性测试
  - [x] `components/admin/SkillResourceTab.vue` — Skill CRUD
  - [x] `components/admin/AgentResourceTab.vue` — Agent CRUD + toggle + set-default
  - [x] `views/AdminAIResourceCenterView.vue` — 三标签页统一管理
  - [x] `router/index.ts` — `admin/ai-resources` 路由
  - [x] `layouts/DefaultLayout.vue` — 侧边栏入口
- [x] **验证**：后端 `ruff check` 全通过；前端 `vue-tsc --noEmit` 无错误；`npm run build` 成功；SSE 端到端测试通过（逐 token + 推理过程 + 会话持久化 + 技能注入）

### AI 助手可用性修复（输入无响应 + 界面不铺满）✅ 2026-06-27

> 端到端验证：经 nginx 真实 WebSocket 发送 `hi` → 收到 `['user_message','assistant_message','done']`，回复“您好！我是 OmicHub 智能分析助手…”；`/ai/status` 返回 `{"configured":true}`。

- [x] **问题一：输入 `hi` 没有任何回复**（多根因叠加，导致后端 AI 调用必然失败）
  - [x] **litellm 路由失败（主因）**：`LiteLLMProvider` 把裸模型名 `qwen3.7-max` 直传 litellm，自定义 OpenAI 兼容端点要求 `openai/` 前缀否则抛 `BadRequestError: LLM Provider NOT provided`。新增 `_route_model()`：配置了自定义 `api_base` 且模型名无前缀时自动补 `openai/`（实测 `openai/qwen3.7-max` 正常返回）
  - [x] **YAML Provider 同步崩溃**：`AIProviderYamlLoader` 对领域实体直接 `session.add()` 抛 `Class ... is not mapped`，aliyun 配置未入库（DB 查出 0 行）。改为统一走 `repo.save()`（实体→ORM 模型转换），并修正默认 Provider 管理（`set_default` 正确取消其他默认）
  - [x] **会话未提交**：启动初始化与 YAML 同步仅 `flush()` 未 `commit()`，数据被回滚。两处补 `await session.commit()`；并调整 lifespan 顺序——YAML（方式1，推荐）先同步，环境变量（方式2）仅在库空时兜底，符合 `.env.example` 设计
  - [x] **`${AL_API_KEY}` 解析为空**：YAML 把 key 改为 `${AL_API_KEY}` 引用，但容器环境无此变量→插值得空串→入库 key 为空→“Invalid API-key”。`.env` 新增 `AL_API_KEY`（`.env` 已 gitignore，密钥不出库），`.env.example` 补模板；compose 给 `web` 挂载 `../../data:/app/data:ro`（之前容器内 `/app/data` 不存在，YAML 同步空跑）
  - [x] **`tool_calls: null` 崩溃**：qwen/aliyun 不调工具时返回 `"tool_calls": null`，`message.get("tool_calls", [])` 拿到 `None`，`_normalize_tool_calls` 遍历 `None` 抛 `TypeError`，在 `assistant_message` 事件发出前被 `except` 吞成 error——故 LLM 已回复但前端不可见。改为 `message.get("tool_calls") or []` + `_normalize_tool_calls` 增加 `if not raw: return []` 守卫
- [x] **问题二：AI 界面下方空白、不铺满视口**
  - [x] 根因：`DefaultLayout` 用 `:native-scrollbar="false"` → Naive 渲染 `NScrollbar` 而非 `.n-layout-scroll-container`；全局 CSS 里 `:deep(.n-layout-scroll-container){flex:1}` 只匹配原生滚动容器、不命中 NScrollbar，高度链断裂 → `.kimi-layout` 的 `height:100%` 无从解析 → 聊天区只占内容高度、下方留白
  - [x] 修复：`DefaultLayout.vue` 对 `fullscreen` 路由（仅 `/ai`）改用 `:native-scrollbar="true"`，使 `.n-layout-scroll-container` 的 `flex:1` 生效，高度链贯通、聊天自动铺满视口、消息列表内部滚动
  - [x] `.session-header` / `.input-area-wrapper` 增加 `flex-shrink:0`，短屏下输入框不被挤压
- [x] **验证**：前端 `npm run build` 通过（nginx 已服务新产物 `index-BQzk0j96.css`）；后端真实 WebSocket 走 nginx 端到端返回正常回复；DB 默认 Provider = aliyun(qwen3.7-max)，key 已加密落库

### 测试报告 v1.1 问题修复 ✅ 2026-06-26
- [x] **认证与路由**
  - [x] 登录成功后 `router.push('/')` + `window.location.href` 双重兜底跳转
  - [x] 路由守卫以 `localStorage.access_token` 为准，未登录访问受保护路由带 `redirect` 参数
  - [x] 登出后清除状态并 `window.location.reload()` 彻底重置
  - [x] 增加跨标签页 `storage` 监听，token 被清除时自动登出
  - [x] 登录/注册失败显示表单内红色文案 + Toast 提示
- [x] **核心页面**
  - [x] `TasksView.vue` 修复导入、增加错误处理，解决白屏
  - [x] `FilesView.vue` 从占位改为真实文件列表（调用 `/api/v1/files`）
  - [x] 后端新增 `/api/v1/files` 列表接口 + `FileService.list_files`
  - [x] `FlowsView.vue` 空状态提示优化
  - [x] `KnowledgeView.vue` 空文档提示
  - [x] `SandboxView.vue` 建设中占位，避免 404 外观
- [x] **AI 助手交互**
  - [x] `KimiLayout.vue` / `ai.ts` 修复新建会话后 UI 切换、消息即时渲染
  - [x] 历史会话点击切换加载
  - [x] `KimiChatInput.vue` 去除 Tooltip 嵌套，修复 Agent/插件/模型下拉无响应
  - [x] 快捷提示卡片点击自动发送
  - [x] WebSocket 连接失败时显示错误横幅与重连按钮
  - [x] 后端新增 `GET /api/v1/ai/status` 配置检测接口
  - [x] `LiteLLMProvider` / `KimiProvider` 新增 `is_configured()` 检查
  - [x] AI 未配置时返回明确错误并前端显示黄色警告条
- [x] **系统设置**
  - [x] `SettingsView.vue` 平台设置页签确保管理员可见
  - [x] 注册开关保存失败回滚并提示错误
  - [x] `RegisterView.vue` 关闭注册时隐藏表单并显示提示
  - [x] 后端 `auth.py` 注册接口校验 `site_settings.registration_enabled`
- [x] **UI/UX**
  - [x] `DashboardView.vue` banner 关闭状态持久化到 localStorage
  - [x] `global.css` 提升下拉菜单 z-index，避免与侧边栏重叠
- [x] **AI Provider 外置 YAML 配置**
  - [x] `config.py` 新增 `AI_PROVIDER_CONFIG_YAML`
  - [x] 新增 `AIProviderYamlLoader` 服务，支持 `${ENV_VAR}` 插值与多 Provider 同步
  - [x] `main.py` 启动时自动同步 YAML 到数据库
  - [x] 新增 `data/ai_providers.yaml` + `data/ai_providers.yaml.example`
  - [x] `.env.example` 增加 YAML 配置说明
- [x] **构建验证**：前端 `type-check` / `build` 通过，后端 `make test` 6 passed

### 本次前端体验修复 ✅ 2026-06-26
- [x] **AI 聊天框可用性修复**
  - [x] 修复 `useAIWebSocket.ts` 发送时序 bug：连接未 `OPEN` 时消息入队，连接成功后按序发送
  - [x] `AIChat.vue` 增加连接错误提示，未配置 AI Provider 时显示具体原因
  - [x] 前端 type-check / build 通过
- [x] **管理员菜单图标区分与折叠**
  - [x] `DefaultLayout.vue` 中“系统管理”改为可折叠分组，默认收起
  - [x] 用户管理 `PersonOutline`、饼干账户管理 `WalletOutline`、饼干定价管理 `PricetagOutline`、AI 模型配置 `SparklesOutline`
  - [x] 移动端抽屉同步展示管理入口，修复 `<renderUserAvatar />` 引用错误
- [x] **通知提醒系统闭环**
  - [x] 后端新增 `NotificationModel` + Repository + Service + API（列表/发布/已读/删除）
  - [x] 注册路由 `/api/v1/notifications` 与 `/api/v1/admin/notifications`
  - [x] Alembic 迁移脚本 `c72c373d1ee2_add_notification_table.py`
  - [x] 前端新增 `NotificationDrawer.vue` + `stores/notification.ts` + TS 类型
  - [x] `DefaultLayout.vue` 顶部通知图标显示未读数，点击打开抽屉
  - [x] 管理员可在抽屉内发布通知（标题/内容/级别/全员或指定用户/过期时间）
  - [x] 后端 `make test` 通过、前端 `npm run build` 通过

### 历史已完成

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
  - [x] flows/atac_seq.yaml ATAC-seq 流程配置 (Bowtie2/Chromap + MACS2 + TOBIAS)
  - [x] ATACFlow Builder (`atacflow_builder.py`) 生成 analysis.yaml / samples.csv / contrasts.csv
  - [x] TaskService 支持 atac_seq 提交与 DAG 生成
  - [x] ExecutionConfig 增加 `config_file_param` 以支持不同流程的配置文件参数名
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
- [x] Alembic 迁移脚本 (alembic/env.py 修复模型导入 + 08ab25316cc1_initial_schema 覆盖全部 7 表+索引+约束，upgrade/无 drift 验证通过)

#### 后端 — 应用层 (application/)
- [x] CookieService 核心服务: check_balance / pre_deduct / settle (多退少补) / refund / freeze / unfreeze / suspend / adjust
- [x] PricingEngine 定价计算引擎: 按 flow_category + resource_type + priority 匹配 + 时段生效判断
- [x] Pydantic DTO: CookieAccountDTO / CookieTransactionDTO / CookiePricingDTO / CostEstimateDTO / CookieStatsDTO
- [x] TaskCookieConsumer 结算服务 (Celery 回调中调用 on_complete/on_cancel)

#### 后端 — API 路由 (api/v1/)
- [x] 用户端 cookies.py: GET /cookies/account | /transactions | /pricing | /estimate | /balance-check
- [x] 管理端 admin/cookies.py: GET /admin/cookies/accounts (JOIN users 返回用户名/邮箱) | POST /adjust | PUT /accounts/{id}/freeze|unfreeze|suspend | GET /transactions | /stats | /pricing (CRUD)
- [x] 管理端 admin/users.py: GET /admin/users 用户列表 | PUT /{id}/approve 审批 | PUT /{id}/reject 拒绝 | PUT /{id}/role 角色切换
- [x] CookieRequiredMiddleware 消费拦截中间件 (middleware/cookie.py — 消费类路由 HTTP 层守卫，冻结→402/停用→403，已注册 main.py)
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
- [x] composables/useCookieWebSocket.ts — 实时余额变更推送 (Redis Pub/Sub + WebSocket /cookies/ws + 自动重连指数退避，已接入 CookieBalanceBadge)
- [x] components/CookieBalanceBadge.vue — 全局余额徽章 (顶栏，已接入 DefaultLayout)
- [x] views/CookieAccountView.vue — 用户账户页 (余额统计/流水列表)
- [x] views/AdminCookieManagementView.vue — 管理后台账户管理 (列表显示用户名+邮箱/调整/冻结/解冻)
- [x] views/AdminCookiePricingView.vue — 定价策略管理 (CRUD + Modal)
- [x] views/AdminUserManagementView.vue — 用户管理 (审批通过/拒绝/角色切换)
- [x] views/AdminCookieTransactionsView.vue — 全局交易流水审计 (独立页面 + 多维度过滤 user/txn_type/source_type/日期 + 分页 + JOIN 用户名/邮箱)
- [x] TaskSubmitView.vue 集成饼干预估 (防抖 500ms 调 /estimate + 余额不足禁用提交按钮 + 费用/余额展示卡片)
- [x] 路由配置: /cookies (用户) + /admin/users + /admin/cookies/accounts + /admin/cookies/transactions + /admin/cookies/pricing (管理员)
- [x] DefaultLayout 侧边栏: computed 动态菜单, admin 角色可见"系统管理"子菜单组 (用户管理/饼干账户管理/交易流水审计/饼干定价管理)

#### 部署与运维
- [x] config.py 新增 cookie 相关配置项 + enable_cookie_system 开关
- [x] scripts/init_cookies.py — 初始化默认定价策略脚本
- [x] cookie 系统开关 ENABLE_COOKIE_SYSTEM=false 时全链路跳过 (TaskCookieConsumer 检查)
- [x] 监控: CookieMonitorService 余额异常告警 + 流水对账 (cookie_ledger 日终快照 + Celery Beat 每日 2:30 自动对账 + 异常检测: 负余额/大额调整/高频消费/冻结账户活动 + 管理端 API: POST /reconcile, GET /anomalies, GET /ledger)

### 优先级 P2 — AI Copilot 与沙盒

- [x] **AI 对话 SSE 流式（Cherry Studio 架构）** (docs/OmicHub_CherryStudio_整合实施文档.md) ✅ 2026-06-28 Cherry Studio SSE 架构完成
  - [x] `chat_service.py` SSE `stream_chat()` — 流式输出 + 实时数据库更新 + 会话/消息持久化
  - [x] `openai_compatible.py` `OpenAICompatibleProvider` + `ProviderManager` — httpx 直连 OpenAI SSE，支持 DeepSeek reasoning_content
  - [x] `api/v1/chat.py` — `POST /chat/stream` SSE 端点 + 会话/助手/模型管理 REST API
  - [x] `useChatStream.ts` — fetch + ReadableStream 解析 SSE，AbortController 停止生成
  - [x] `chatSession.ts` — 会话/消息/流式状态管理（Cherry Studio Optimistic Update 模式）
  - [x] `chatAssistant.ts` — 内置助手 + 自定义助手管理（分类分组）
  - [x] `ChatMessageItem.vue` + `MarkdownRenderer.vue` — Markdown 渲染 + DOMPurify XSS 防护 + highlight.js 代码高亮 + 复制按钮
  - [x] `KimiLayout.vue` 接入 SSE stores（不再依赖 WebSocket）
  - [x] Tool Use 协议 (submit_task/query_status/list_samples) — WebSocket 路径保留（ai_service.py）
  - [x] ⚠️ 2026-06-27 修复多重隐性 bug 使其真正可用：litellm 路由前缀 / YAML 同步 `not mapped` 崩溃 + 未 commit / `${AL_API_KEY}` 解析为空 / `tool_calls:null` 崩溃（详见顶部「AI 助手可用性修复」节）
  - [x] ⚠️ 2026-06-28 修复 `_build_kwargs` 丢失 `stream=True` 导致 SSE 返回 ModelResponse 的致命 bug
  - [x] ⚠️ 2026-06-28 技能 prompt 注入 + 助手 system_prompt 覆盖 + 资源管理中心（Skill/Agent/MCP 三标签页）

- [x] **代码执行沙盒** (docs/modules/08_tech_selection.md) ✅ 2026-06-27
  - [x] Docker 预热容器池管理器
  - [x] 沙盒镜像 Dockerfile (Bioconda + scanpy/seurat) — 改为 `condaforge/mambaforge` 基础，bioconda 渠道预装 scanpy/anndata/squidpy/scvi-tools + R/Seurat/IRkernel；新增 `sitecustomize.py` 注入 sc/np/pd + `show_echarts`/`show_image` 回传协议
  - [x] WebSocket 代码执行协议
  - [x] 前端 CodeMirror 6 编辑器组件 — `components/sandbox/CodeEditor.vue`（Python lang + one-dark + 行号/历史/高亮）
  - [x] ECharts GL 图表渲染 (UMAP/热图) — `components/sandbox/echartsSetup.ts` 注册 scatterGL/heatmap/dataZoom/visualMap/brush
  - [x] 会话亲和性 + 30min 超时回收
  - [x] `SandboxView.vue` 完整页面：会话列表/创建/销毁 + 编辑器 + 运行/停止 + 结果三标签页（输出/图表/图片）+ 示例代码（UMAP scatterGL / 表达热图 / matplotlib 图片）

- [x] **MCP 集成** (docs/modules/11_integration_fusion.md) ✅ 2026-06-26 后端实现完成
  - [x] MCPServerRepositoryImpl
  - [x] MCP Client (Python MCP SDK) 生命周期管理
  - [x] 四大预设 MCP 服务 (文献/基因组/代码/知识库)
  - [x] 工具发现 + 调用路由 + 错误隔离
  - [x] `/api/v1/mcp/servers` CRUD 端点

> ⚠️ P2 后续待补齐：
> 1. 补 alembic 迁移：`ai_conversations` / `ai_messages` / `mcp_servers` / `sandbox_sessions` 四张表未在现有迁移中。
> 2. ~~沙盒前端页面：`SandboxView.vue` + 路由 `/sandbox` + CodeMirror 6 + ECharts GL UMAP/热图渲染。~~ ✅ 2026-06-27 已完成
> 3. ~~沙盒镜像 Dockerfile 按文档要求改为 Bioconda 并启用 R+Seurat。~~ ✅ 2026-06-27 已完成

### 优先级 P3 — 生产化

- [x] **首次部署初始化**
  - [x] Web 首次配置引导页 (`/setup`)：无管理员时自动跳转，创建 root 管理员并登录
  - [x] 后端 API: `GET /auth/setup-required` + `POST /auth/setup`
  - [x] 路由守卫自动检测并跳转 setup 页面
  - [x] 修复 `AuthMiddleware` 未放行 `/auth/setup-required` 和 `/auth/setup`
  - [x] 修复 `main.py` 重复注册 7 次 `CookieRequiredMiddleware` 导致请求异常
  - [x] 修复 `UserStatus` 枚举缺少 `pending` 状态导致含待审批用户时转换失败
  - [x] `scripts/init_admin.py` 命令行初始化脚本（幂等、生产环境强制设置密码）
  - [x] `.env.example` 增加 `OMICHBUB_INIT_ADMIN_*` 配置项
  - [x] `Makefile` 增加 `make init-admin` / `make init-cookies` 命令

- [x] **数据库迁移** (docs/modules/02_database_schema.md) ✅ 2026-06-25
  - [x] 完整建表 SQL (六域所有表 — 通过 Alembic autogenerate 生成)
  - [x] JSONB 字段标注 (parameters/logs/preferences 等)
  - [x] 索引设计 (覆盖索引 + 部分索引 + 复合索引)
  - [x] Alembic 初始迁移 (08ab25316cc1_initial_schema.py — 7 表 + 全部索引/约束/FK，upgrade 验证通过)

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

### 本次美化/文档待收尾（2026-06-26 继续）

- [ ] **知识库与文档中心**
  - [x] 创建 `docs/knowledge/` 与 `docs/docs/` 目录及 YAML/Markdown 示例文件
  - [x] 后端 `docs_service.py` + `api/v1/docs.py` 路由实现
  - [x] 后端 `api/v1/router.py` 注册 `/docs` 路由
  - [x] 前端 `MarkdownReader.vue` 轻量 Markdown 渲染组件
  - [x] 前端 `KnowledgeView.vue` 知识库页面（待验证路由参数默认值）
  - [ ] 前端 `DocsView.vue` 文档中心页面
  - [ ] 前端 `router/index.ts` 注册 `/knowledge/:docId?` 与 `/docs/:docId?` 路由
  - [ ] `DefaultLayout.vue` 更新顶部导航链接：实验室知识库 → `/knowledge`，文档 → `/docs`
  - [ ] 前后端类型检查与构建验证

- [ ] **首页流星效果优化**
  - [ ] `AboutView.vue` 流星出现位置与飞行方向完全随机化
  - [ ] 降低流星频率（数量、延迟、持续时间）
  - [ ] 流星尾巴方向随飞行角度同步

### 优先级 P4 — 优化与运维

- [ ] **监控可观测性**
  - [ ] Prometheus 指标暴露
  - [ ] Grafana 仪表盘模板
  - [ ] 结构化日志 + Loki 聚合
  - [ ] API 请求追踪 (OpenTelemetry)

- [ ] **前端完善**
  - [x] About 页面 (Milky Way 背景 + star-stuff 文案) ✅ 2026-06-25
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

## 前端动画/美化仓库调研

> 针对当前前端技术栈 **Vue 3 + Vite + TypeScript + Naive UI** 的可选动画/美化库清单（仅调研，未引入代码）。

### 通用动画库（Vue 3 原生支持或友好）

- [@vueuse/motion](https://github.com/vueuse/motion) — Vue 官方生态 motion 库，指令式 `v-motion`，零配置入场/出场动画
- [AutoAnimate](https://github.com/formkit/auto-animate) — DOM 变化自动动画，适合列表/弹窗/下拉菜单
- [vue-kinesis](https://github.com/amineyarman/vue-kinesis) — 鼠标/滚动/陀螺仪驱动的视差交互动画
- [AnimXYZ](https://github.com/ingram-projects/animxyz) — CSS 变量驱动的组合动画框架，原生支持 Vue
- [Animate.css](https://github.com/animate-css/animate.css) — 经典 CSS 动画库，直接加 class 使用
- [GSAP](https://github.com/greensock/GSAP) + [vue-gsap](https://github.com/derickdaniel/vue-gsap) — 专业级时间轴动画
- [Motion One](https://github.com/motiondivision/motionone) + [vue-motion-one](https://github.com/wobsoriano/vue-motion-one) — 轻量高性能硬件加速动画

### 页面背景 / 粒子特效

- [tsParticles](https://github.com/matteobruni/tsparticles) — 粒子效果库，有 `@tsparticles/vue3`，支持雪花/连线/星空/星云
- [particles.js](https://github.com/VincentGarreau/particles.js) — 经典轻量粒子背景（维护较慢，更推荐 tsParticles）
- [Inspira UI](https://github.com/unovue/inspira-ui) — Vue 版 Aceternity/Magic UI，含 Aurora、粒子漩涡、雪花、光束、流星等 70+ 特效组件
- [Vanta.js](https://github.com/tengbao/vanta) — 3D 动态背景（飞鸟/海浪/云雾/拓扑），基于 three.js/p5
- [three.js](https://github.com/mrdoob/three.js) — 3D 场景终极方案
- [granim.js](https://github.com/sarcadass/granim.js) — 动态渐变背景，登录页常用

### 滚动 / 视差 / 交互增强

- [AOS](https://github.com/michalsnik/aos) — 滚动触发入场动画
- [ScrollReveal](https://github.com/jlmakes/scrollreveal) — 滚动显示动画
- [rellax](https://github.com/dixonandmoe/rellax) — 轻量视差滚动
- [tilt.js](https://github.com/gijsroge/tilt.js) — 卡片 3D 倾斜悬浮效果
- [locomotive-scroll](https://github.com/locomotivemtl/locomotive-scroll) — 平滑滚动 + 视差

### 加载动画 / 微交互

- [LDRS](https://github.com/loading-io/ldrs) — 精致加载动画
- [Whirl](https://github.com/jh3y/whirl) — 纯 CSS loading 动画合集
- [vue3-lottie](https://github.com/megasanjay/vue3-lottie) — Vue 3 播放 Lottie/AE 动画
- [dotLottie](https://github.com/LottieFiles/dotlottie-web) — LottieFiles 官方新版轻量播放器
- [Hover.css](https://github.com/IanLunn/Hover.css) — 鼠标悬浮效果合集
- [CSShake](https://github.com/elrumordelaluz/csshake) — 抖动动画，表单错误提示可用

### UI 美化 / 主题增强

- [Naive UI 官方主题](https://github.com/tusen-ai/naive-ui) — 通过 `n-config-provider` + `theme-overrides` 做动态换肤、暗黑模式
- [@vueuse/core](https://github.com/vueuse/vueuse) — `useColorMode` / `useCycleList` 快速做主题切换
- [Tailwind CSS](https://github.com/tailwindlabs/tailwind.css) — 原子化 CSS，配合 Naive UI 做自定义布局
- [UnoCSS](https://github.com/unocss/unocss) — 按需原子 CSS，可与 Naive UI 主题变量联动

### 针对当前项目的建议组合

考虑到是 **生信分析平台**，建议优先走"简洁专业 + 适度动效"路线：

1. **入场/过渡**：`@vueuse/motion` 或 `AutoAnimate`
2. **列表/表格动画**：`AutoAnimate`
3. **登录页/首页背景**：`tsParticles` 或 `Inspira UI` 的 Aurora/粒子组件
4. **加载状态**：`LDRS` 或 `vue3-lottie`
5. **主题美化**：Naive UI `theme-overrides` + `@vueuse/core` 的 `useColorMode` 做暗黑模式
6. **滚动展示**：`AOS` 做文档/结果页滚动动画

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
