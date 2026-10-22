# CygnusX 架构文档覆盖审计（2026-10-21）

> **用途**：对 `ARCHITECTURE_DESIGN/` 与当前代码做一次全覆盖对账：哪些模块有 as-built 文档、哪些只有零散引用、哪些完全没有汇总；记录本轮新增的 9 份平台经营面文档、1 份异步任务队列补充文档、核实并纠正的事实、以及仍然存在的文档缺口。
> **类型**：审计快照 + 文档索引（2026-10-21 代码基线）。
> **适用范围**：`src/cygnusx/api/v1/` 49 个路由模块、`application/services/` 196 个服务文件、`frontend/src` 的页面/Store/API 模块。
> **不适用范围**：具体业务契约以各领域 as-built 文档为准；本文只回答"有没有、在哪、是否过期"。

## 这个文档如何发挥作用

架构库此前以"执行链/Agent/Flow/沙箱/记忆"为主线，覆盖面偏向 AI 与科研链路；用户、饼干、节日、通知、项目文件、目标、管理控制台、调度运维等"平台经营面"长期没有入口。本次审计把代码中的路由、服务、前端入口逐项映射到文档，新增 9 份 as-built 文档；随后补充 1 份异步任务队列文档，补齐跨域的 Celery/RocketMQ 执行基础设施。仍无法归入现有文档的遗留模块列为"残余缺口"，避免读者误以为架构库已经 100% 覆盖。

判定口径：

- **深度覆盖**：有独立 as-built 文档，含架构图、数据模型/接口、边界与验证。
- **部分覆盖**：在他人文档中有章节或零散引用，但缺少完整契约。
- **未覆盖**：架构库检索不到有效引用，或仅有提案/历史文档提及。

## 1. 覆盖矩阵

### 1.1 平台经营面（本轮补齐）

| 领域 | 路由/服务/前端入口 | 覆盖 | 承接文档 |
|---|---|---|---|
| 认证/用户/角色/模块门禁 | `api/v1/{auth,users,modules}.py`、`middleware/{auth,rbac,module_gate}.py` | 深度 | [CygnusX_identity_access_architecture.md](CygnusX_identity_access_architecture.md) |
| 管理控制台 | `api/v1/admin/*`（18 个路由模块）、`/admin/*` 17 视图 | 深度 | [CygnusX_admin_console_architecture.md](CygnusX_admin_console_architecture.md) |
| 饼干经济 | `api/v1/cookies.py`、`admin/admin_cookies.py`、`CookieService`、WS 推送 | 深度 | [CygnusX_cookie_economy_architecture.md](CygnusX_cookie_economy_architecture.md) |
| 节日彩蛋 | `api/v1/festival.py`、`admin/festival.py`、`data/festival_config.yaml`、首页弹窗 | 深度 | [CygnusX_festival_architecture.md](CygnusX_festival_architecture.md) |
| 通知/公告/提醒/站点内容 | `api/v1/{notification,announcements,site_content,site_settings,reminders}.py`、提醒投递任务 | 深度 | [CygnusX_notification_engagement_architecture.md](CygnusX_notification_engagement_architecture.md) |
| 项目/文件/团队/归档 | `api/v1/{projects,files,teams}.py`、`file_service`、`upload_session`、`workspace_archive` | 深度 | [CygnusX_project_workspace_architecture.md](CygnusX_project_workspace_architecture.md) |
| 目标运行时 | `api/v1/goals.py`、`agent_goals` 模型、goal engine/evaluator、Celery 续跑 | 深度 | [CygnusX_goal_architecture.md](CygnusX_goal_architecture.md) |
| Skill/MCP 接入面 | `admin/skills.py`、`skill_route`、五入口导入、`user_agent_capabilities`、资源中心 | 深度 | [CygnusX_skill_mcp_integration_architecture.md](CygnusX_skill_mcp_integration_architecture.md) |
| 调度与分析运维 | `api/v1/{schedules,workflow_monitor,runs,stats,plot_stats}.py`、workflow ingest、平台运行记录 | 深度 | [CygnusX_analysis_operations_architecture.md](CygnusX_analysis_operations_architecture.md) |

### 1.2 AI 与执行链（既有文档）

| 领域 | 覆盖 | 承接文档 |
|---|---|---|
| 平台总览/架构图 | 深度 | `CygnusX_platform_architecture.md`、`CygnusX_platform_architecture_maps.md` |
| Chat 执行分层/事件 | 深度 | `CygnusX_chat_execution_layers.md`、`CygnusX_agent_execution_framework.md` |
| 单 Agent 构成与装配 | 深度 | `CygnusX_agent_architecture.md`、`CygnusX_agent_framework_baseline.md` |
| 多 Agent 协作/AgentTeams | 深度 | `CygnusX_agent_execution_framework.md`、`CygnusX_multi_agent_fanout.md` |
| MAS/A2A 蓝图 | 提案 | `CygnusX_mas_a2a_plan.md`（Phase 0–4 已落地部分以执行框架为准） |
| 模型路由/Provider | 深度 | `CygnusX_model_routing_architecture.md`、`CygnusX_token_billing_architecture.md` |
| MCP 体系/构建师 | 深度 | `CygnusX_mcp_architecture.md` |
| Skill 体系 | 深度 | `CygnusX_skill_architecture.md` + 本轮接入文档 |
| 记忆/知识库 | 深度 | `CygnusX_memory_architecture.md`、`CygnusX_knowledge_architecture.md` |
| 联网搜索 | 深度 | `CygnusX_web_search.md` |
| OpenAI4S 融合/上下文 | 深度 | `CygnusX_chat_openai4s_integration_architecture.md` |

### 1.3 执行环境、数据与科研链（既有文档）

| 领域 | 覆盖 | 承接文档 |
|---|---|---|
| 沙箱/Studio/终端 | 深度 | `CygnusX_sandbox_architecture.md`、`CygnusX_studio_handover.md`（历史）、`CygnusX_research_loop_architecture.md` |
| 存储/目录协议 | 深度 | `CygnusX_storage_architecture.md`、`CygnusX_storage_workspace_gap_audit.md`（快照） |
| 数据库/迁移/参考基因组 | 深度 | `CygnusX_database_architecture.md` |
| 日志/审计 | 深度 | `CygnusX_log_architecture.md` |
| 异步任务队列/Celery/RocketMQ | 深度（2026-10-21 补充） | [CygnusX_async_task_queue_architecture.md](CygnusX_async_task_queue_architecture.md) |
| 网络/egress | 深度 | `CygnusX_network_architecture.md` |
| Flow/管线/报告/工具箱 | 深度 | `CygnusX_flow_architecture.md`、`CygnusX_report_architecture.md`、`CygnusX_toolbox_architecture.md` |
| Dataset/下载 | 深度 | `CygnusX_dataset_architecture.md`、`CygnusX_download_architecture.md` |
| 科研寻宝鼠/交付/计划 | 深度（运行门禁 BLOCKED） | `CygnusX_treasure_mouse_architecture.md`、`CygnusX_research_delivery_architecture.md`、`CygnusX_research_plan_architecture.md` |
| 前端总体规范 | 深度 | `CygnusX_frontend.md`（36 章） |

## 2. 本轮新增文档

| # | 文档 | 主要回答的问题 | 关键边界/校正 |
|---|---|---|---|
| 1 | `CygnusX_identity_access_architecture.md` | 登录、JWT/刷新、2FA、API Key、RBAC、模块门禁、管理端用户管理如何工作 | 记录中间件实际入站顺序与 `CookieRequiredMiddleware` 空转；`UserStatus` 枚举缺 `rejected`；19 模块/17 可锁定 |
| 2 | `CygnusX_admin_console_architecture.md` | 系统管理 12 菜单、18 个 admin 路由模块、五套管理员依赖、TOTP 覆盖面 | 前端 `/admin/*` 无角色守卫；BLAST 管理端在 `/blast/admin/*`；会话日志依赖本地文件 |
| 3 | `CygnusX_cookie_economy_architecture.md` | 账户、账本、定价、折扣、任务冻结/结算/退款、AI 扣费、WS 推送、对账 | 与 token 计费分界；`cookie_consumption_logs` 休眠；任务级扣费幂等缺口 |
| 4 | `CygnusX_festival_architecture.md` | 37 个节日定义、公历/农历/节气解析、领取与 EARN 奖励、节日管理 | YAML 唯一真相源；容器 `/app/data` 只读与 UTC 时区风险 |
| 5 | `CygnusX_notification_engagement_architecture.md` | 通知、公告、提醒投递、欢迎语、站点设置/内容、首页快捷入口 | 无 SSE（60s 轮询）；可见性校验缺口；生产 worker 未消费 `schedules` 队列 |
| 6 | `CygnusX_project_workspace_architecture.md` | 单属主项目、概览、文件记录/分块上传/目录解析、团队 ACL、工作区归档 | 无项目成员表；受管引用 `upload://`/`file://` 等；归档生命周期回指科研闭环 |
| 7 | `CygnusX_goal_architecture.md` | 目标生命周期、状态机、评估器、终态工具、续跑/恢复、API/SSE、前端 | 默认关闭；Redis 租约与 DB 租约不一致；死状态与前端恢复口径偏差 |
| 8 | `CygnusX_skill_mcp_integration_architecture.md` | `skill_route` 算法、五入口导入、管理面、用户级覆盖、Agent 装配 | 纠正旧文档的 10 技能上限、YAML 覆盖、`UserAgentCapabilityModel`、`features` ORM/迁移漂移等 |
| 9 | `CygnusX_analysis_operations_architecture.md` | 定时任务、提醒调度、工作流监控 ingest、平台运行记录、统计/绘图统计、AI 指标告警 | `schedules` worker 缺口、ingest HMAC 可选；AI 指标告警已由 Beat `ai-metrics-alert-check` 每 5 分钟触发（原“无告警 beat”记录已纠正） |
| 10 | `CygnusX_async_task_queue_architecture.md`（补充） | Celery 应用配置、逻辑队列、25 条路由、34 条 Beat、Worker/Beat/Flower 部署矩阵、ack/重试/超时、RocketMQ 传输、日志与追踪 | `schedules` 无消费者；GSEA 未在 include/route 中；RocketMQ 不覆盖直接派发且忽略 `task_routes`；Beat 单实例 |

## 3. 本轮核实并纠正的架构事实

以下事实在代码中核实，与部分旧文档或口头认知不一致，后续以新文档为准：

1. **中间件入站顺序**：`add_middleware` 后注册者先执行，实际为 `TraceContext → RateLimit → Audit → CookieRequired → Auth → ModuleGate → CORS → routes`；`CookieRequired` 与 `ModuleGate` 读取 `request.state.user_id` 时 Auth 尚未注入，前者实际空转，后者依赖 fail-open（详见身份文档）。
2. **管理员依赖不是一套**：`middleware/rbac.py`、`api/deps.py`、`notification.py`、`announcements.py`、`site_settings.py` 各自定义 `require_admin`，共五个函数对象；只有 `users.py` 把 rbac 版本 re-export 给其他 admin 路由。
3. **前端管理页没有角色守卫**：`/admin/*` 仅 `requiresAuth`，菜单显隐靠 `isAdmin`；安全边界完全在后端。
4. **TOTP 只覆盖三处**：删除用户、`PUT /site-settings`、`PATCH /admin/platform-config` 的敏感字段；改角色、发 Worker Token、改 Provider 密钥等均未二次校验。
5. **节日是纯 YAML 驱动**：37 个定义、无 DB 活动表、无定时任务；激活只由"当前日期 + 前端拉取"决定。
6. **模块注册为 19 个、17 个可锁定**：管理员默认全开通，`disabled_modules` 只对普通用户生效。
7. **通知没有实时通道**：前端 60 秒轮询；公告按时间窗与 `localStorage` 去重。
8. **目标运行时默认关闭**：`goal_runtime_enabled=False`，仅 chat + 安全模式可用；续跑依赖 Redis 租约 + DB 租约双写，二者不一致已记录为风险。
9. **BLAST 管理端点不在 `/admin` 前缀**：位于 `tools/blast/api.py` 的 `/blast/admin/*`，由工具路由自动发现挂载。
10. **旧版 AI 对话 API 仍在使用**：`/ai/conversations` 由 `stores/ai.ts`、全局 AI 助手侧边栏和 `AIChat.vue` 消费，而 `AIChatView.vue` 已改为挂载 `AgentWorkspace`；两条前端表面并存（见第 4 节）。

Skill/MCP 相关的十项旧文档纠偏（10 技能上限、YAML 覆盖、`UserAgentCapabilityModel`、`features` ORM/迁移漂移、legacy assistants 等）已集中列在 `CygnusX_skill_mcp_integration_architecture.md` 的"对旧文档的校正"表，本文不重复。

## 4. 残余缺口（尚未形成完整文档）

| # | 缺口 | 证据 | 现状判断 | 建议 |
|---|---|---|---|---|
| 1 | 旧版 AI 对话 / 全局助手侧边栏 | `api/v1/ai.py`（WebSocket + 会话 CRUD + 外部工具确认）、`frontend/src/stores/ai.ts`、`GlobalAiAssistantSidebar.vue`、`AIChat.vue` | `AIChatView` 已切 AgentWorkspace，但浮动侧边栏仍走 `/ai/conversations`；架构库无专门章节 | 在 `CygnusX_chat_openai4s_integration_architecture.md` 增加"Legacy AI 会话与浮动助手"小节，或单列一份 legacy 文档；先确认是否仍有产品入口 |
| 2 | MAS 房间（生信部门）阶段 1 骨架 | `api/v1/mas_rooms.py`、`application/services/mas/mas_room_service.py`、`mas_worker_executor.py` | POST 发言只落库并广播，不启动 MAS run；SSE 约定对齐 goals；仅愿景文档提及 | 并入 goal/agentteams 文档的"未接入路径"说明，暂不必单独成文 |
| 3 | 科研 Claim/Evidence API 面 | `api/v1/research_claims.py`（claims 评估、artifact-cells） | 领域语义在 `CygnusX_research_delivery_architecture.md`，但端点清单未列全 | 在交付架构文档补一节 endpoint 表 |
| 4 | `research_data.py` provider 端点 | `api/v1/research_data.py`、`research_data_service.py` | MCP 文档说明其作为固定 provider 适配，寻宝鼠文档覆盖领域链路；API 面未单独枚举 | 维持现状，在 MCP/寻宝鼠文档交叉引用即可 |
| 5 | Prompt 管理路由 | `api/v1/prompts.py`（`GET /user-templates/bio`） | 极小；Prompt Registry 机制已在 Agent 基线与执行框架文档说明 | 无需单独文档，补一行端点说明即可 |
| 6 | 管理端 AgentTeams 桥接 UI | `admin/agentteams_bridge.py`、`AgentTeamsBridgeTab.vue` | 已在本轮管理控制台文档覆盖；桥接内部协议仍以 AgentTeams 执行文档/桥接代码为准 | 已完成，保留交叉引用 |
| 7 | `research_claims`/`research_provenance` 前端 | `frontend/src/api/claimProvenance.ts` | 与缺口 3 同源 | 随交付文档补充 |

说明：`api/v1/docs.py`（知识库文档）由 `CygnusX_knowledge_architecture.md` 覆盖；`site_content.py`/`site_settings.py` 由通知文档覆盖；`modules.py` 由身份文档覆盖；`plot_stats.py` 由分析运维文档覆盖；`biothings.py` 由 MCP 文档覆盖；文献检索服务（arXiv/生物医学）由寻宝鼠文档覆盖。上述不单列为缺口。

## 5. 文档治理待办

1. **README 索引登记**：本轮 9 份平台经营面文档与 1 份异步任务队列补充文档必须登记到 `ARCHITECTURE_DESIGN/README.md`，标注类型（as-built）、日期与一句话摘要；本文作为覆盖审计入口同步登记。
2. **交叉引用**：在 `CygnusX_skill_architecture.md`、`CygnusX_mcp_architecture.md`、`CygnusX_memory_architecture.md`、`CygnusX_token_billing_architecture.md`、`CygnusX_research_loop_architecture.md`、`CygnusX_agent_execution_framework.md` 顶部补充回指，避免读者仍只看到旧边界。
3. **命名与快照**：本文带日期性（覆盖审计），文件名不带日期符合现行规范；后续覆盖变化时更新本文而非另建快照，历史可查 git。
4. **不要当运行时注册表**：本文与各架构文档都不会被 Agent 自动加载；修改代码仍以代码、配置、迁移为准。

## 6. 验证方式

- 路由清单：`src/cygnusx/api/v1/router.py` 的 `include_router` 与 `src/cygnusx/tools/*/api.py` 自动发现。
- 前端入口：`frontend/src/router/index.ts`、`layouts/DefaultLayout.vue`、`layouts/navigationRegistry.ts`、`src/api/**`、`src/stores/**`。
- 覆盖判定：对每个领域关键词在 `ARCHITECTURE_DESIGN/*.md` 做检索，并人工阅读候选文档，排除提案/历史快照/`deprecated/` 的误命中。
- 新文档自查：每份均含"用途/类型/适用范围"头、架构图、实现图（适用时）、数据/接口表、风险表、关键文件索引与验证清单。
