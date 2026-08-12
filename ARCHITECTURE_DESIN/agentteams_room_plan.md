# AgentTeams 团队协作室实施方案

> 日期：2026-08-12
> 状态：待实施
> 前提：超频模式（overdrive）保留不动，仅维持现状可用——用户计划后续对超频模式单独重构，本方案不为超频侧新增投入；与超频共用的组件（ParallelSubAgentService）只做向后兼容的增量改动。
> 本方案为 AgentTeams（Bridge Case 体系）新增独立聊天室入口，并让房间内的 agent 可调用平台已有的沙箱 / MCP / Skill。

## 1. 目标

1. 侧边栏新增「团队协作室」入口，页面内可发起 Case、实时观看多 agent 轮流发言（复用现有 room_speech 渲染观感）。
2. 房间内的 agent 执行过程可见：工具调用（沙箱 / MCP / Skill）逐步投影到房间事件流，而不是只见一头一尾。
3. 专业 agent（rnaseq/atacseq/scrna 等）在 Case 中可按 YAML 声明使用 `workspace_execution`（沙箱 + 9 个 workspace 工具），解除目前仅 agent-code/agent-viz 的硬编码限制。
4. 顺带修复治理缺陷：Case 状态自动收敛、Case GC、心跳面板别名聚合、Case 与会话关联展示。

## 2. 现状关键事实（已核实，实施时不必重查）

### 2.1 执行链路（沙箱/MCP/Skill 已天然在线）

```
worker 容器(空壳轮询) → bridge POST .../execute-readonly → gateway(白名单/限额)
  → 主后端 POST /api/v1/agent-teams/consultations/scientific-interpretation
  → AgentConsultationService.run_consultation
  → ParallelSubAgentService.run（超频同款子 agent 运行时）
      ├─ 沙箱：sandbox_execute 等 9 个 workspace 工具（execution_mode=workspace_execution 时）
      ├─ MCP：按 agent YAML 绑定的 mcp_servers 注入（_prepare_child_tools 保留 MCP 工具）
      └─ Skill：use_skill / read_skill_resource
```

- 会诊请求已携带 `case_id` + `work_item_id` + `execution_mode`（`src/omichub/api/v1/agentteams.py:97-119`）。
- `ParallelSubAgentService.run` 已支持 `on_event` 回调并发出 `worker_started / worker_tool_call / worker_finished / worker_heartbeat` 事件（`parallel_subagent_service.py:190,490,566,644`）——**会诊路径目前没有传 on_event**，这就是工具过程不可见的原因。
- Bridge 已有证据事件入口 `POST /v1/cases/{id}/evidence`（`bridge/.../app.py:549`），event_type 自由字符串（pattern `^[a-z0-9_.-]+$`），证据事件会进 audit 流，`GET /v1/cases/{id}/events/stream` SSE 可推到前端。
- 主后端 → bridge 的客户端 `AgentTeamsService`（`agentteams_service.py`）**尚无 evidence 方法**，需新增。
- 产物链路已通：会诊 artifacts 落盘 + MinIO 上传（`agent_consultation_service.py:270`），读取走 `GET /agent-teams/cases/{cid}/artifacts/{path}`（`api/v1/agentteams.py:377`）。

### 2.2 能力声明已在 YAML 里

- 多数 agent（rnaseq、scrna×3、cloud_ops、mcp_builder、data、general 等）已在 `data/ai/*.yaml` 声明 `features.agentteams.execution_modes: [readonly_consultation, workspace_execution]`。
- capability registry 已把 `execution_modes` 暴露进 `/capabilities` 快照的 `agent_capabilities`（`agentteams_capability_registry.py:80-106`）。
- 但 worker 端硬编码拦截：`integrations/agentteams/worker/production_runner.py:194-199` 只允许 `agent-code`/`agent-viz` 跑 workspace_execution——与 YAML 声明矛盾，是本方案要解除的核心限制。
- 安全边界保留：workspace_execution 的 workdir 禁锢在 `/data/omichub/output/agentteams/{case}/{work_item}`（`agent_consultation_service.py:121-124`），不可移除。

### 2.3 前端资产

- 房间发言渲染：`KimiMessageItem.vue` 只要消息挂 `senderAgent{name,avatar,color,role,round}` 即渲染 manager 气泡 / worker 折叠卡片。
- Case SSE 消费样板：`AgentTeamsCaseView.vue:startEventStream`（:311-355，cursor 续传 + 指数退避 + 轮询降级）。
- API 封装：`frontend/src/api/agentTeams.ts`（listCases/createCase/confirm/revise/reject/retry/getEvents 等齐全）。
- 侧边栏：`frontend/src/layouts/DefaultLayout.vue:230-258`（navItems，无 i18n，硬编码中文）；路由 `frontend/src/router/index.ts`。
- agent 显示元数据：registry 的 `role_labels()`（name/avatar/color/role，`agentteams_capability_registry.py:163-176`），但 `/capabilities` 是 integration token 鉴权，前端用户态拿不到，需新增用户态端点。

### 2.4 只读数据访问现状（"看到用户数据但仅读取"已是体系默认姿态）

- `readonly_consultation` 模式下子 agent 走 `safe_only=True` 只读工具白名单，本身就不能写。
- 已有 6 个用户态只读证据工具（`tool_configs/tools_schema.yaml:127+`，全部 `readOnlyHint: true` + `user_scoped: true`，`AgentTeamsDataToolService`）：
  - `task_result_summary`：读用户任务状态/参数快照/产物清单/QC metrics/失败摘录
  - `task_file_preview`：预览任务目录内文本产物头部（禁路径穿越/符号链接）
  - `workspace_file_preview`：按 requester_ref 隔离预览用户 workspace 文件
  - `artifact_fetch` / `task_compare_metrics` / `rule_threshold_lookup`
- 扩展读能力**不需要新代码**：在 agent YAML 绑定只读 MCP 工具包（builtin presets：omichub-tools / omichub-platform）即可，`parallel_subagent_service._prepare_child_tools` 会保留 MCP 工具。
- 即：房间 agent 默认"能看用户的任务、文件、产物、指标，但不能改"；要写只有 `workspace_execution` 模式且禁锢在 case 专属 workdir。

### 2.5 治理缺陷现状

- Case 不自动收敛：work item 更新只写 work_item 状态；`reconcile_case`（`bridge/.../service.py:259`）存在但只能手动/管理端触发。线上 2 个僵尸 received case 即此因。
- 无 GC：10 个 7/31-8/11 测试残留 case 永久留存的根因。
- 心跳面板误报：`_ROLE_ALIASES`（data-steward→agent-data 等 3 个，`agentteams_capability_registry.py:20-24`）在统计"缺心跳 worker"时未聚合；agent-router、shania 的 YAML 有 `internal_case_role` 但无 worker 部署。

## 3. 里程碑与改动清单

### M1：团队协作室 MVP（前端为主，后端 2 个小端点）

**目标**：侧边栏入口 + 房间页面，能发起 Case、实时看事件投影的多 agent 发言、做审批动作。

后端：

1. **新增用户态 role-labels 端点**：`src/omichub/api/v1/agentteams.py`
   - `GET /api/v1/agent-teams/role-labels`（用户 JWT），返回 `get_agentteams_capability_registry().snapshot()` 的 `role_labels` + `role_agent_map` 子集，供房间渲染发言人名/头像/颜色。
2. **Case 列表带会话关联**（可选，M1 简化版可跳过）：`list_cases` 响应补充 `session_id`——聊天侧绑定存在 `ChatSessionModel.sandbox_meta.agentteams_case_ids`（`agentteams_case_tool_service.py:296-327`），反向索引即可。M1 先按 requester_ref 全部列出。

前端：

3. **路由 + 导航**：
   - `frontend/src/router/index.ts`：新增 `{ path: 'agent-teams/room', name: 'agent-teams-room', component: () => import('@/views/AgentTeamsRoomView.vue'), meta: { title: '团队协作室', requiresAuth: true } }`。
   - `frontend/src/layouts/DefaultLayout.vue` navItems 在「AI 工作台」后加 `{ key: 'agent-teams-room', label: '团队协作室', to: '/agent-teams/room', icon: ... }`；如需前缀高亮在 `isActive`(:280-307) 加分支。
4. **事件→房间消息投影工具** `frontend/src/utils/agentTeamsRoom.ts`（新文件，纯函数，好测）：
   - 输入：case event `{event_id, recorded_at, case_id, actor, event_type, payload}` + role_labels。
   - 输出：`RoomMessage{ id, sender{name,avatar,color,role}, kind: 'speech'|'progress'|'action'|'system', content, round?, collapsed? }`。
   - 投影规则表：

     | event_type | 投影 |
     |---|---|
     | `case.created` / `planning.frozen` | manager 发言（计划摘要，payload 取 plan 描述） |
     | `work_item.assigned` | system 行「Manager 将任务分派给 {role_label}」 |
     | `work_item.claimed` / `work_item.running` | worker 卡片起始（streaming 态） |
     | `agent.tool_call`（M2 新增证据事件） | worker 卡片内 progress 行「正在调用 {tool}」 |
     | `agent.tool_result`（M2） | progress 行完成态（耗时/成败） |
     | `skill.finished` | worker 终态发言（payload.conclusion/summary） |
     | `skill.failed` / `skill.manual_review` | worker 发言（错误态样式） |
     | `quality.decision` / `quality.hard_gate` | agent-qc 发言 |
     | `case.cancelled` / `case.state_changed` | system 行 |
     | `omic_task.*` | 折叠 system 行（默认收起） |
     | 其他 | 丢弃（不进房间） |

5. **房间页面** `frontend/src/views/AgentTeamsRoomView.vue`（约 300-400 行）：
   - 左栏：Case 列表（`agentTeamsApi.listCases`，状态 badge，按 updated_at 倒序）+「发起团队任务」按钮。
   - 发起对话框：intent + project/flow 选择（复用 `AgentTeamsCaseView` 的表单件或 `AgentTeamsCaseCard` 逻辑）→ `POST /cases`。
   - 右栏：选中 Case → SSE 消费 `GET /api/v1/agent-teams/cases/{id}/events/stream?cursor=`，模式照抄 `AgentTeamsCaseView.vue:startEventStream`（cursor 续传、1s→30s 指数退避、断流转 20s 轮询 `getEvents`）；事件经 `agentTeamsRoom.ts` 投影成 RoomMessage 列表渲染。
   - 渲染：speech 消息直接用 `KimiMessageItem.vue`（构造带 `senderAgent` 的 ChatMessage）；progress 行用简化气泡；底部动作条按 case 状态渲染 确认/修计划/驳回/重试（调现有 agentTeamsApi，复用 `AgentTeamsCaseView` 的弹窗组件）。
   - M1 不做自由文字输入（Bridge 无用户发消息 API），输入框位留占位 disabled + tooltip「自由对话二期开放」。

**验收**：发起一个通用 Case → 房间左侧出现 → 右侧逐步出现 manager 计划、任务分派、worker 起止、qc、交付发言 → 审批动作可用。

### M2：工具调用投影（让房间"活起来"）

后端：

6. **`AgentTeamsService` 新增 `post_case_evidence`**：`src/omichub/application/services/agentteams_service.py`
   - `POST /v1/cases/{case_id}/evidence`（bridge app.py:549，用 manager 身份 token），body `{event_type, payload, actor}`。
7. **会诊路径接 on_event 投影**：`src/omichub/application/services/agent_consultation_service.py` `run_consultation`(:81)
   - 构造 `on_event` 回调传给 `ParallelSubAgentService.run`（:190 参数已存在）。
   - 映射：`worker_started` → evidence `agent.started`；`worker_tool_call` → `agent.tool_call`（payload: `{tool, args_summary(截断200字符), work_item_id, agent_id}`）；`worker_finished` → `agent.finished`（payload: `{status, tool_call_count, duration_ms}`）。
   - 工具执行成功后补 `agent.tool_result`（若 run 的事件流不区分结果，在 M2 内给 `ParallelSubAgentService` 的工具执行完成处（:763 附近）加发 `worker_tool_result` 事件，同样转发）。
   - 容错：evidence POST 失败仅 log warning，**不得影响会诊主流程**（fire-and-forget + try/except）。
   - 限流保护：同一 work item 的 tool_call 事件上限 200 条，超出计数合并为一条 `agent.tool_call_truncated`。

前端：

8. `agentTeamsRoom.ts` 投影表加入 `agent.tool_call / agent.tool_result / agent.started / agent.finished`（见 M1 表），房间视图在 worker 卡片内渲染进度行（样式参考超频 `assistant_tool_call` 的进度 label）。

**验收**：跑一个 workspace_execution work item，房间内实时看到「RNA-seq 助手 正在调用 sandbox_execute」「正在调用 pipeline_query」等进度，随后出现终态发言与产物。

### M3：能力放开 + 治理修复

9. **workspace_execution 白名单配置化**：
   - `integrations/agentteams/worker/production_runner.py:194-199`：删除 `agent-code/agent-viz` 硬编码，改为读 `/capabilities` 快照的 `agent_capabilities[identity].execution_modes`（`load_worker_profile` 已请求该端点，扩展取 execution_modes 一并校验）；YAML 未声明 `workspace_execution` 的 identity 才拒绝。
   - gateway `agent_policies`（`gateway/.../service.py:92-149`）：确认各 agent policy 的 capability 白名单包含 `workspace_execution`（配置文件同步改）。
   - 检查 bridge 侧 work item 创建时 `execution_mode` 的赋值点，确保与 registry 声明一致校验（不一致则降级 readonly 并记 `planning.validation_failed`）。
10. **Case 状态自动收敛**：`bridge/.../service.py`
    - 在 work item 状态更新为终态（completed/failed）的处理路径（app.py:298 → service 内 update 方法）末尾调用内部 `_auto_reconcile(case_id)`：复用 `reconcile_case`(:259) 的判定逻辑，全部 work item 终态且无进行中 omic_task 时推进 case 状态（保持现有状态机，不新增状态）。
    - 幂等：已终态 case 直接返回。
11. **Case GC**：`bridge/.../app.py` + `service.py`
    - 新增 `POST /v1/maintenance/case-gc`（manager 身份）：删除 `status ∈ {cancelled, failed, closed}` 且 `updated_at` 早于 N 天前的 case 及其 audit 事件；N 由 env `BRIDGE_CASE_GC_DAYS`（默认 7，0=禁用）。
    - 仅在 `BRIDGE_ENVIRONMENT != production` 默认启用启动时+每日定时执行；生产只提供手动端点。
12. **心跳面板别名聚合**：`src/omichub/application/services/agentteams_service.py` `admin_resource_snapshot`(:100)
    - 统计缺心跳 worker 前，先用 registry 的 `role_alias_map()` 把别名 identity 归并到 canonical role（data-steward→agent-data 等），消除误报。
13. **worker 部署缺口收口**（配置决策，二选一）：
    - 方案 a：给 `agent-router`、`shania` 补 professional-pool identity（`deploy/agentteams/docker-compose.agentteams.yml:137-157` 的 `AGENTTEAMS_WORKER_IDENTITIES` + token env）。
    - 方案 b（推荐）：这两个是路由/人设型 agent，不参与 Case 执行——从其 YAML 删除 `internal_case_role`，告警自然消失。
14. **（可选）Case-会话关联展示**：房间左栏按 session 分组显示 case（依赖 M1 第 2 条的反向索引）。
15. **只读数据工具盘点暴露**：房间「发起团队任务」对话框提示 agent 可读的数据范围（任务/文件/产物/指标），前端文案即可；若某 agent 需要更多读能力，在其 YAML 绑定只读 MCP 包，不改代码。

## 4. 配置与部署变更

- `deploy/agentteams/worker.env.example`：无新增 token；`production_runner` 改动纯代码。
- bridge env 新增：`BRIDGE_CASE_GC_DAYS=7`（compose `docker-compose.agentteams.yml` bridge 服务环境块补充）。
- 全栈重启验证：`make docker-reload`（步骤 9 会重建 agentteams worker 镜像，worker 代码改动必须走它生效）；只改主后端/前端时 `make docker-dev-refresh` 即可。

## 5. 测试计划

后端（pytest）：
- `tests/unit/test_agent_consultation_service.py`（或新建）：on_event 投影——mock `AgentTeamsService.post_case_evidence`，断言 tool_call/tool_result/started/finished 事件各按规则发出、evidence 失败不影响会诊结果、200 条截断生效。
- `tests/unit/test_agentteams_capability_registry.py`：execution_modes 校验逻辑。
- `integrations/agentteams/bridge/tests/`：auto-reconcile（全终态→状态推进、幂等）、case-gc（按天数过滤、audit 清理）、evidence 端点契约（已有 `test_bridge_contract.py` 可扩展）。

前端（vitest）：
- `frontend/src/utils/__tests__/agentTeamsRoom.spec.ts`：投影表全分支。
- 房间视图组件测试：mock SSE 事件序列 → 断言发言/进度/动作条渲染。

端到端冒烟（手动）：
1. `make docker-reload` 后起全栈。
2. 房间发起 RNA-seq 通用 Case → 观察 M1 全链路发言。
3. 确认计划 → 观察 worker 工具调用进度（M2）与产物下载。
4. 构造全终态 case 验证自动收敛；调 `POST /v1/maintenance/case-gc` 验证残留清理。

## 6. 风险与边界

- **安全边界不可后退**：readonly_consultation 的 `safe_only=True` 保留；workspace_execution 的 workdir 禁锢保留；evidence 投影失败不得阻断会诊。
- **投影事件量**：tool_call 高频，务必做 200 条截断 + args 摘要截断，避免 audit 流膨胀（Redis Stream 记得在 GC 中一并 trim）。
- **房间内不能自由对话**是 M1 已知限制；二期（Matrix 房间接线，`agentteams_room_gateway_service.py` 已写好待启用）再开。
- 超频模式与团队协作室共用 `ParallelSubAgentService`，M2 给它加 `worker_tool_result` 事件时注意不影响超频现有事件消费方（`chat_service.py` / `agentteams_case_watch_service.py`）——新增事件类型、不改既有事件语义即可。

## 7. 工作量估算

| 里程碑 | 内容 | 预估 |
|---|---|---|
| M1 | 房间入口+投影+页面（后端 2 小端点） | 1.5 天 |
| M2 | 工具调用投影（前后端） | 1 天 |
| M3 | 白名单配置化+自动收敛+GC+心跳聚合 | 1 天 |
| 合计 | | ~3.5 天 |
