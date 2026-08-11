# AgentTeams 收敛计划：从多路径并存到单窗口群聊

> 版本：1.0
> 日期：2026-08-11
> 性质：施工计划与文件改动清单
> 配套目标文档：`data/ai/update/AgentTeams_VISION_FINAL.md`

---

## 1. 目标与原则

### 1.1 目标

以 **“用户参与的单窗口多专家群聊”** 为唯一产品形态，收敛当前四条多智能体路径，保留并复用 AgentTeams 基础设施，让平台上全部已定义 Agent 都能作为群聊中的专家被招募。

### 1.2 核心原则

1. **单窗口唯一入口**：用户不跳页、不打开外链。
2. **AgentTeams 只做编排**：状态机、工单、审批、审计；不运行 LLM。
3. **平台 Agent 即专家**：全部 16 个已定义 Agent 都是可选执行者。
4. **角色映射单一来源**：Bridge/Gateway/投影器共用同一份 registry。
5. **不新造事件类型**：复用 `room_speech` / `overdrive_progress` / `ask_request` / `overdrive_approval_request` / `mode_changed`。
6. **先拆旧枝、再添新叶**：移除重复/关闭的路径，再补全剩余缺口。

---

## 2. 需要移除的内容

### 2.1 MAS 编排（orchestrator + DAG）

**原因**：默认关闭，与单窗口群聊形态冲突；和 AgentTeams 重复。

| 改动项 | 具体位置 | 操作 |
| --- | --- | --- |
| 默认启用开关 | `src/omichub/core/config.py`：`settings.mas_enabled` | 默认值保持 `False`，并在文档中标记为“deprecated，不再作为用户入口” |
| 动态追加 orchestrator | `src/omichub/infrastructure/config/agent_loader.py` | 删除 `mas_enabled` 打开时自动追加 `orchestrator` 的逻辑 |
| 计划工具挂载 | `data/ai/tools/*.yaml` 中 `mas_plan_preview` 等 | 从所有 Agent 的 Tool Pack 中移除 |
| 前端入口 | 管理台 MAS 开关、聊天中 MAS 计划卡 | 移除 UI 入口，保留后端 API 只读兼容 |
| 文档 | `data/ai/README.md` §11.4 / §12.1 / §13.1 | 改写为“历史路径，已收敛到 AgentTeams” |

### 2.2 对话内 fan-out (`parallel_subagents`) 的范围收敛

**原则**：`parallel_subagents` 作为常规 AI 助手页面的**单会话轻量并行工具**继续保留；本次收敛只限制它**不再作为一条独立的 multi-agent 路径与 AgentTeams 群聊并存**。

**原因**：在 AgentTeams 群聊目标下，复杂多专家协作应由 Case / Work Item 编排；若同时保留 chat 循环内的 fan-out，会造成两条 multi-agent 路径竞争，且 fan-out 的 `ask_user` 不冒泡、无泳道展示。

| 改动项 | 具体位置 | 操作 |
| --- | --- | --- |
| AgentTeams 工具包 | `data/ai/tools/agentteams_case.yaml` | 确保 **不挂载** `subagents` 工具；AgentTeams 内部不通过 fan-out 派生子 Agent |
| AgentTeams 场景下的 chat 循环 | `src/omichub/application/services/chat_service.py` | 当当前会话已绑定 AgentTeams Case 时，不走 `parallel_subagents` 分支；改由 Bridge 派 Work Item |
| 常规 AI 助手页面 | `SettingsView.vue` / `chat_service.py` | **保留** `subagent_fanout_enabled` 开关和 `parallel_subagents` 工具调用能力 |
| 前端事件处理 | `frontend/src/composables/useAgentChatStream.ts` | 保留 `case 'subagents'`，但仅用于常规 AI 助手页面的轻量并行展示；AgentTeams Case 事件走 `room_speech` |
| 管理端开关 | 管理端 `subagent_fanout_enabled` | **保留**，文案明确为“常规助手页面启用轻量并行子 Agent” |

### 2.3 AgentTeams Matrix/Element 外链群聊

**原因**：不是产品内原生群聊，体验割裂。

| 改动项 | 具体位置 | 操作 |
| --- | --- | --- |
| Element iframe 抽屉 | `frontend/src/components/agentteams/AgentTeamsChatDrawer.vue` | 删除组件，或保留为只读历史审计入口（不推荐） |
| Element 外链按钮 | `AgentTeamsCaseView.vue` / `AgentTeamsCaseCard.vue` | 删除“打开群聊室”按钮 |
| Matrix 相关配置 | `deploy/agentteams/` 中 Matrix/Element URL 配置 | 标记为 deprecated，后续移除 |

### 2.4 独立 Case 详情页作为强制入口

**原因**：复杂任务必须在聊天内闭环。

| 改动项 | 具体位置 | 操作 |
| --- | --- | --- |
| 聊天内创建 Case | `frontend/src/components/ai-chat/KimiChatInput.vue:799-805` / `StudioView.vue:604-607` | 改为直接调用 `createCase` API，并插入 `AgentTeamsCaseCard` |
| 审批跳转 | `AgentTeamsCaseCard.vue:71-74` | 在卡片内直接实现“批准/拒绝”按钮，调现有 `POST /api/v1/agent-teams/cases/{id}/submit` |
| Case 详情页定位 | `frontend/src/views/AgentTeamsCaseView.vue` | 保留，但仅作为“查看审计详情/下载 manifest”入口 |

### 2.5 旧版 AgentTeams 文档

| 改动项 | 具体位置 | 操作 |
| --- | --- | --- |
| 归档旧文档 | `data/ai/update/AgentTeams_update*.md`、`AgentTeams_codex_prompt*.md` | 移入 `data/ai/update/archive/` |
| 更新 README | `data/ai/README.md` §13 / §8.1 / §11.4 | 引用 `AgentTeams_VISION_FINAL.md` 作为唯一权威目标 |
| 更新 update_agent.md | `data/ai/update/update_agent.md` | 删除其中 AgentTeams 比赛阶段描述，改为引用 VISION_FINAL；保留赛后超频 v2 长期目标 |

---

## 3. 需要保留并复用的内容

### 3.1 AgentTeams 编排基础设施

| 组件 | 位置 | 复用方式 |
| --- | --- | --- |
| Bridge 状态机 | `integrations/agentteams/bridge/omichub_agentteams_bridge/case_store.py` | 完整保留，作为 Case/Work Item 权威状态 |
| Gateway | `integrations/agentteams/gateway/` | 完整保留，作为 Bridge → OmicHub 的受控通道 |
| Worker 集群 | `integrations/agentteams/worker/` | 完整保留，负责认领和转发 |
| 审批签名 | `integrations/agentteams/bridge/omichub_agentteams_bridge/security.py` | 完整保留 |
| 审计事件 | `integrations/agentteams/bridge/omichub_agentteams_bridge/audit.py` | 完整保留，append-only |
| MinIO 共享存储 | `src/omichub/infrastructure/storage/minio_store.py` | 完整保留，作为 agent 间产物传递 |
| 生命周期清理 | `src/omichub/infrastructure/celery_app/tasks/agentteams.py` | 完整保留 |

### 3.2 OmicHub 平台 Agent

| 组件 | 位置 | 复用方式 |
| --- | --- | --- |
| Agent YAML | `data/ai/*.yaml` | 全部保留，每个 Agent 都可以被招募 |
| Agent 装载 | `src/omichub/application/services/agent_service.py` | `assemble_context(agent_id, user_id=...)` 作为 consultation 执行基础 |
| consultation 端点 | `src/omichub/api/v1/agentteams.py` | 保留并扩展为所有专家角色的统一执行入口 |
| 只读执行内核 | `src/omichub/application/services/agent_consultation_service.py` + `ParallelSubAgentService` | 保留，`safe_only=True` 用于只读专家，`workspace_access=True` 用于执行型专家 |
| 只读数据工具 | `tool_configs/tools_schema.yaml` 中 read-only 工具 | 保留，供专家读取真实数据 |
| 硬规则 QC 门 | `src/omichub/application/services/agentteams_quality_gate_service.py` | 保留 |
| 能力注册表 | `src/omichub/application/services/agentteams_capability_registry.py` | **升级为角色映射单一来源** |

### 3.3 超频模式前端组件

| 组件 | 位置 | 复用方式 |
| --- | --- | --- |
| 房间消息流 | `frontend/src/components/ai-chat/KimiMessageItem.vue` | 复用 `room_speech` / `room_speech_delta` 渲染 |
| 进度卡 | `frontend/src/components/ai-chat/OverdriveProgressCard.vue` | 复用为专家泳道/招募卡 |
| 用户询问 | `frontend/src/components/ai-chat/AskUserCard.vue` / `AskUserModal.vue` | 复用为群内决策弹窗 |
| 审批卡 | `frontend/src/components/ai-chat/OverdriveApprovalCard.vue` | 复用为群内高风险审批 |
| 流解析 | `frontend/src/composables/useAgentChatStream.ts` | 复用现有 `case 'room_speech'` 等分支 |
| Store | `frontend/src/stores/agentHub.ts` | 复用 `applyCaseRoomEvent` |

### 3.4 CaseRoomProjector

| 组件 | 位置 | 复用方式 |
| --- | --- | --- |
| 事件投影器 | `src/omichub/application/services/case_room_projector.py` | 保留并扩展 speech 模板，覆盖全部 16 个 Agent 的发言场景 |
| watch 服务 | `src/omichub/application/services/agentteams_case_watch_service.py` | 保留，但 interval 从 60s 降至 10-15s |
| 事件消费者 | `src/omichub/application/services/agentteams_case_event_consumer_service.py` | 保留 |

---

## 4. 需要新增/修改的内容

### 4.1 角色映射单一来源改造

**目标**：Bridge/Gateway/投影器共用 `AgentTeamsCapabilityRegistry`。

| 改动 | 位置 | 要点 |
| --- | --- | --- |
| 扩展 registry | `src/omichub/application/services/agentteams_capability_registry.py` | 增加 `role_agent_map()`、`role_labels()`、`agent_capabilities()`，覆盖全部 16 个 Agent |
| Bridge 消费 registry | `integrations/agentteams/bridge/omichub_agentteams_bridge/service.py` | 创建 Work Item 时调用 registry 解析 `target → agent_id`；删除本地硬编码映射 |
| Gateway 消费 registry | `integrations/agentteams/gateway/service.py` | `agent_policies` 从 registry 动态加载 |
| 投影器消费 registry | `src/omichub/application/services/case_room_projector.py` | 已接入，扩展即可 |
| 测试 | `tests/unit/test_agentteams_capability_registry.py` | 确保新增映射覆盖全部 Agent，且三处一致 |

### 4.2 全部 16 个 Agent 接入 AgentTeams

**目标**：每个 Agent 都能在群聊中被招募，并有稳定的人格/头像/名字。

| 改动 | 位置 | 要点 |
| --- | --- | --- |
| Agent YAML 加 `persona` | `data/ai/*.yaml` | 按 `update_agent.md` §3.1 增加 `features.persona`：archetype/traits/working_style/communication_style/status_lines |
| Agent YAML 加 `internal_case_role` | `data/ai/*.yaml` | 声明该 Agent 在 AgentTeams 中的默认角色名（如 `agent-rnaseq → agent-rnaseq`） |
| 补齐骨架 Agent | `data/ai/data.yaml`、`data/ai/delivery.yaml` | 挂载 skill_ids、补提示词、去掉“正在配置”文案 |
| Bridge 角色配置 | `integrations/agentteams/teams/bioops-delivery.yaml` | 补全 16 个角色定义，每个角色指向对应 Agent |
| Bridge env 令牌 | `deploy/agentteams/bridge.env.example` | 补全所有身份令牌，与 `bridge/config.py` 默认值对齐 |
| Worker profile | `integrations/agentteams/worker/production_runner.py` / `worker_runner.py` | 扩展 `_AGENT_PROFILES` 覆盖全部角色 |

### 4.3 聊天内创建 Case 与审批闭环

**目标**：用户在当前聊天窗口内触发和审批 AgentTeams 群聊。

| 改动 | 位置 | 要点 |
| --- | --- | --- |
| 结构化建单弹窗 | `frontend/src/components/ai-chat/KimiChatInput.vue` | 增加“创建协作 Case”按钮，弹窗收集目标/输入/领域，调 `POST /api/v1/agent-teams/cases` |
| 消息内建单 | `StudioView.vue` / 路由相关 | 同样接入 createCase |
| Case 卡片内审批 | `frontend/src/components/agentteams/AgentTeamsCaseCard.vue` | 增加“批准 / 拒绝”按钮，直接调 submit API；结果经 SSE 刷新 |
| Manager 自动建单 | `src/omichub/application/services/chat_service.py` | 当 Manager 判断需要多专家协作时，自动调用 AgentTeamsService 创建 Case，并把 Case ID 绑定到当前 session |
| 创建工具 | `data/ai/tools/agentteams_case.yaml` | 保留 `create_agentteams_case`，但降低使用门槛（默认参数由 Manager 自动填充） |

### 4.4 群聊投影增强

**目标**：Case 事件在聊天窗口里看起来像群聊。

| 改动 | 位置 | 要点 |
| --- | --- | --- |
| 扩展 speech 模板 | `src/omichub/application/services/case_room_projector.py` | 为每个专家类型定制发言文案；规划、结果回流、点评、QC、交付都有独立模板 |
| 增加 Manager 点评消息 | `case_room_projector.py` 或新服务 | 当 `manager_review_ready` 事件产生时，投影为 Manager 的 `room_speech` |
| 进度卡增强 | `OverdriveProgressCard.vue` | 显示“谁在做什么”而不是抽象的 task ID |
| 产物卡片 | 复用 `overdrive_progress` artifacts | 在群里显示最近 3 个产物缩略 + 下载 |
| 事件游标持久化 | 数据库迁移 | 新建 `agentteams_case_cursors` 表，替代 `sandbox_meta` 单字段 |

### 4.5 规划阶段标准化

**目标**：复杂任务必须先由真实领域 Agent 出 plan，用户确认后再执行。

| 改动 | 位置 | 要点 |
| --- | --- | --- |
| planning_running 状态 | `integrations/agentteams/bridge/omichub_agentteams_bridge/case_store.py` | 已存在，确保未经过 planning 且无 plan_hash 不得进入 approval_pending |
| lead planner 选择 | `src/omichub/application/services/chat_service.py` 或新服务 | Manager 按任务方向 + `capability_scope` 选 lead planner |
| plan-01 Work Item | Bridge `service.py` | 自动创建 planning 工单，target 为 lead planner |
| 计划确认卡 | 前端 + 后端 | `ask_request(kind=plan_confirmation)`，展示 plan_hash + 摘要 + 参数 |
| 计划版本 | Bridge `models.py` + `service.py` | `proposed_submission` + `plan_hash`，确认后冻结 |
| 质控决策 | plan.md / `proposed_submission` | lead planner 在计划中明确是否需要 `quality_running`；仅当分析结果确实可能涉及质量检测时才创建 `quality-01` |

### 4.6 workspace_execution 通用化

**目标**：不局限于 RNA-seq，treeplot 等通用任务也能跑通。

| 改动 | 位置 | 要点 |
| --- | --- | --- |
| execution_mode 分发 | Bridge `service.py` | `workspace_execution` 工单允许非只读，但必须绑定已确认 plan_hash |
| 产物登记 | `src/omichub/application/services/agentteams_data_tool_service.py` | 确保 `_register_workspace_artifacts` 写 `file_records`（source="agentteams"） |
| artifact_fetch 工具 | `tool_configs/tools_schema.yaml` | 保留并加入所有相关 Tool Pack |
| 输入文件只读保护 | Studio 沙箱 (`manager.py:382-391`) / `data/ai/prompts/shared/agentteams_workspace_execution.md` | 用户真实数据目录以 `mode: "ro"` 挂载到沙箱 `/data/platform`；`input/`/`ref/` 只放软链，物理上不可改 |
| 示例 flow | `data/ai/flows/treeplot.yaml` | 保留作为通用分析型标本 |

---

## 5. 分阶段实施计划

### Phase 0：止血与归档（1 周）

1. 把旧版 AgentTeams 文档移入 `archive/`。
2. 关闭 MAS 编排的动态启用逻辑；从 Agent Tool Pack 中移除 `mas_plan_preview`。
3. 在 AgentTeams 场景下不再通过 `parallel_subagents` 派生子 Agent；确保 `agentteams_case` Tool Pack 不挂载 `subagents`，`chat_service.py` 在已绑定 Case 的会话中走 Bridge Work Item 而非 fan-out。
4. 移除 Element 外链入口和 iframe 抽屉。
5. 把 `AgentTeamsCaseView.vue` 的审批按钮直接暴露到 `AgentTeamsCaseCard.vue`。

**验收**：
- 旧文档不再出现在 `data/ai/update/` 根目录。
- 简单问答不再触发 MAS/fan-out/AgentTeams。
- 聊天内可对 Case 卡片做批准/拒绝。

### Phase 1：统一角色映射（1 周）

1. 扩展 `AgentTeamsCapabilityRegistry` 覆盖全部 16 个 Agent。
2. Bridge/Gateway/投影器统一消费 registry。
3. 为每个 Agent YAML 增加 `features.persona` 和 `internal_case_role`。
4. 补齐 `agent-data`、`agent-delivery` 的 skill_ids 和提示词。
5. 更新 `bioops-delivery.yaml` 和 `bridge.env.example`。

**验收**：
- `test_agentteams_capability_registry.py` 全绿，验证 16 个 Agent 映射三处一致。
- 触发一个 Case，聊天气泡显示正确专家名字和头像。

### Phase 2：聊天内闭环（1-2 周）

1. Manager 自动判断何时创建 AgentTeams Case。
2. 实现“创建协作 Case”结构化弹窗。
3. 实现 plan_confirmation 弹窗（确认/修改/取消）。
4. `ask_request` 和 `overdrive_approval_request` 在聊天内闭环。
5. 事件游标迁移到独立表。

**验收**：
- 用户从发任务到确认计划，全程不跳页。
- 刷新页面后群聊状态可重建。

### Phase 3：群聊体验打磨（1-2 周）

1. 扩展 `CaseRoomProjector` speech 模板，让专家发言更像人。
2. Manager 对每条结果的验收点评投影为 room_speech。
3. 进度卡显示“谁在做什么”。
4. 产物在群里直接展示最近 3 项。
5. watch 间隔降到 10-15s。

**验收**：
- 3 个以上专家参与的 Case，在窗口内按完成顺序逐个发言。
- 产物可点击下载。

### Phase 4：端到端验收（1 周）

1. RNA-seq 复合任务端到端。
2. 通用 treeplot 任务端到端。
3. 计划修改、取消、失败重试、断线恢复、用户终止场景。
4. 全量回归测试。

**验收**：
- 通过 `AgentTeams_VISION_FINAL.md` §8 全部验收标准。

---

## 6. 文件改动清单

### 6.1 后端

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `src/omichub/core/config.py` | 修改 | `mas_enabled` 默认 False，标记 deprecated |
| `src/omichub/infrastructure/config/agent_loader.py` | 修改 | 移除 mas_enabled 追加 orchestrator 逻辑 |
| `src/omichub/application/services/agentteams_capability_registry.py` | 扩展 | 覆盖 16 个 Agent 的角色映射与标签 |
| `src/omichub/application/services/case_room_projector.py` | 扩展 | 增加 Manager 点评和全部专家发言模板 |
| `src/omichub/application/services/agentteams_case_watch_service.py` | 修改 | interval 降 10-15s；游标迁移 |
| `src/omichub/application/services/chat_service.py` | 修改 | Manager 自动建 Case；在已绑定 Case 的会话中不走 `parallel_subagents`，改由 Bridge 派 Work Item |
| `src/omichub/api/v1/agentteams.py` | 修改 | 保留并扩展 consultation 端点 |
| `tool_configs/tools_schema.yaml` | 修改 | 移除 mas 工具；保留 read_only / artifact_fetch |
| `data/ai/tools/agentteams_case.yaml` | 修改 | 确保不挂载 `subagents`；保留 `create_agentteams_case` 等 |
| `data/ai/tools/*.yaml` | 修改 | 移除 `mas_plan_preview` 等包；常规 Agent 的 `subagents` 包保留 |
| `data/ai/*.yaml` | 修改 | 增加 persona 和 internal_case_role |
| `data/ai/data.yaml`、`delivery.yaml` | 修改 | 补齐 skill_ids 和提示词 |
| `data/OmicHub.yaml` | 修改 | 移除 orchestrator 自动启用描述（如存在） |
| alembic 迁移 | 新增 | `agentteams_case_cursors` 表 |

### 6.2 AgentTeams Bridge/Gateway/Worker

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `integrations/agentteams/teams/bioops-delivery.yaml` | 扩展 | 补全 16 个角色 |
| `integrations/agentteams/bridge/omichub_agentteams_bridge/service.py` | 修改 | 消费 registry；删除本地硬编码映射 |
| `integrations/agentteams/bridge/omichub_agentteams_bridge/config.py` | 修改 | 角色默认配置与 registry 对齐 |
| `deploy/agentteams/bridge.env.example` | 修改 | 补全 11+ 身份令牌 |
| `deploy/agentteams/docker-compose.agentteams.yml` | 扩展 | 为新增角色补 Worker 服务 |
| `integrations/agentteams/worker/production_runner.py` | 扩展 | 覆盖全部角色 profile |
| `integrations/agentteams/gateway/service.py` | 修改 | agent_policies 从 registry 加载 |

### 6.3 前端

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `frontend/src/components/ai-chat/KimiChatInput.vue` | 修改 | 增加“创建协作 Case”结构化弹窗 |
| `frontend/src/components/agentteams/AgentTeamsCaseCard.vue` | 修改 | 增加批准/拒绝按钮 |
| `frontend/src/components/agentteams/AgentTeamsChatDrawer.vue` | 删除或降级 | 移除 Element iframe |
| `frontend/src/components/agentteams/AgentTeamsCaseView.vue` | 修改 | 移除“打开群聊室”按钮；保留审计详情 |
| `frontend/src/components/ai-chat/OverdriveProgressCard.vue` | 扩展 | 显示专家名字与任务 |
| `frontend/src/composables/useAgentChatStream.ts` | 修改 | 保留 `subagents` 分支供常规助手页面使用；确保 AgentTeams Case 的 `room_speech` / `overdrive_progress` 事件被消费 |
| `frontend/src/stores/agentHub.ts` | 修改 | 复用 applyCaseRoomEvent |

### 6.4 文档

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `data/ai/update/AgentTeams_VISION_FINAL.md` | 新增 | 本计划配套目标文档 |
| `data/ai/update/AgentTeams_CONVERGENCE_PLAN.md` | 新增 | 本计划 |
| `data/ai/update/archive/*.md` | 归档 | 旧版 v1/v2/v2.1/v2.2/codex 文档 |
| `data/ai/README.md` | 修改 | §13 等章节引用 VISION_FINAL |
| `data/ai/update/update_agent.md` | 修改 | 删除 AgentTeams 比赛阶段描述，引用 VISION_FINAL |

---

## 7. 风险与回退

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 收敛 fan-out 范围时误伤常规助手页面 | 中 | 明确只限制 AgentTeams 场景；常规 AI 助手页面保留 `subagent_fanout_enabled` 开关和 `parallel_subagents` 工具 |
| 关闭 MAS 影响已启用用户 | 低 | MAS 默认关闭，影响面小；保留后端 API 只读兼容 |
| Bridge 角色映射改造引入回归 | 中 | 增加契约测试，确保三处一致；灰度放量 |
| 全部 Agent 接入增加调试面 | 中 | 分 Phase 2 逐个验证；骨架 Agent 优先补齐 |
| 事件游标迁移丢事件 | 高 | 双写一段时间，确认稳定后再读新表 |
| 用户不适应“自动建 Case” | 低 | 保留用户手动触发入口；复杂任务才自动建 |

---

## 8. 完成检查清单

- [ ] Phase 0 完成：旧文档归档，MAS 入口移除，AgentTeams 场景下不再走 fan-out，Element 入口移除。
- [ ] Phase 1 完成：16 个 Agent 角色映射三处一致。
- [ ] Phase 2 完成：聊天内可创建、确认、审批 Case。
- [ ] Phase 3 完成：专家按完成顺序在群内发言，产物可下载。
- [ ] Phase 4 完成：端到端验收通过，回归测试全绿。
- [ ] `AgentTeams_VISION_FINAL.md` §8 验收标准全部打勾。
