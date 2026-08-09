# 多智能体协作升级方案：对齐「Kimi 式 Agent Swarm」工作流

> 创建日期：2026-08-09
> 参考素材：`docs/26.8.9/multi-agent/` 下 7 张 Kimi OK Computer 式多智能体协作截图
> 现状依据：`data/ai/README.md` §13（可运行性核查）、§14（统一超频协作架构蓝图）、§15（实现进度），
> 以及 `parallel_subagent_service.py` / `chat_service.py` 实际代码核对结果。
> 本文档为评估 + 施工方案，不含代码改动。

---

## 1. 背景与目标

`docs/26.8.9/multi-agent/` 中的截图展示了一个成熟的「agent swarm」多智能体产品形态
（Kimi OK Computer 风格）：主 Agent 接到复杂任务后制定计划、动态招募一批**有名有姓的
临时助手**并行工作，助手结果逐个回流，主 Agent 边收边评、再发起下一波招募，最终交付
统一产物。

OmicHub 目前已有四条多智能体路径（见 `data/ai/README.md` §13）：

| 路径 | 形态 | 默认开关 | 与目标形态的关系 |
| --- | --- | --- | --- |
| 对话内 fan-out（`parallel_subagents`） | 一次工具调用并行派生子专家跑受限工具循环 | 管理端 `subagent_fanout_enabled` | **与截图形态最接近，是本次升级的主体** |
| 超频模式（overdrive room） | Manager + 多 worker 分头像发言 | 前端 `OverdriveToggle` | 群聊 UI 三件套（气泡/泳道/决策卡）可复用 |
| MAS 编排（orchestrator + DAG） | 可确认计划 → Celery 执行 DAG | `mas_enabled`（默认关） | 重型执行后端，与本次体验升级正交 |
| AgentTeams Case | 跨角色工作流状态机 + 人工审批 | 默认全关 | §14 阶段 C 另行收敛，不在本文范围 |

**目标**：把对话内 fan-out 升级为截图所示的「招募 → 并行 → 逐个回流 → 多波次 → 统一交付」
完整体验，同时补上「遇决策问用户」的缺口。MAS / AgentTeams 的执行边界不变。

---

## 2. 目标形态拆解（截图工作流的 6 个关键特征）

从 7 张截图还原出的完整工作流：

1. **计划先行**：主 Agent 收到复合任务后，先创建 `plan.md` 作为工作记忆，再开始执行
   （截图 1：「制定分析计划并读取文件」+ 创建 `plan.md`）。
2. **主 Agent 先独立完成串行前置工作**：解析上传文件（PDF/PPTX/PNG）、加载 SKILL.md、
   跑终端命令、联网/图片搜索（截图 1–3 的折叠工具链时间线）。
3. **动态招募**：`助手招募 | 已招募 8 个助手`——子 Agent 是**临时人格**（柯恩 / 费立群 /
   卡尔 / 萨特 / 科斯 / 苏郁 / 时毅 / 艾伦），每个有名字、头像、分工任务和一条拟人状态
   （"正在充电" / "闲着也是闲着" / "泡了杯茶"）（截图 3–5）。
4. **真异步并行**：招募完成后主 Agent **继续干自己的活**（Phase F 文件分析存档），
   助手们在后台并行跑（截图 6：「8 个调研 Agent 正在并行工作，我现在等待它们的结果返回」）。
5. **逐个消息回流 + 主 Agent 点评**：`等待助手消息` → `助手消息 | 来自 费立群`，
   结果一个个回来，主 Agent 边收边评估（「dim02 完成，质量很高——已定位关键机制证据链」），
   继续等其余的（截图 7）。
6. **多波次编排 + 统一交付**：第一波 8 个调研完成后汇总，**第二波再招募 3 个写手**
   （姜校长 / 纳什 / 唐墨，各写一章），终态显示「已下班」；底部出现 `全部文件`
   产物面板，可预览/下载（截图 8）。

---

## 3. OmicHub 现状盘点（代码已核对）

### 3.1 已就位的地基

- **执行内核同构**：`ParallelSubAgentService.run()`
  （`src/omichub/application/services/parallel_subagent_service.py:154`）已具备：
  `asyncio.gather` 并行 + `Semaphore` 限流（`:211/220`）、单子任务失败隔离
  （`return_exceptions=True`，`:245`）、超时与重试（`:452/491`）、统一信封
  `{success, llm_payload, ui_payload}` 返回。
- **per-child 事件钩子已存在**：服务层在子任务开始/结束时回调
  `on_event({"type": "worker_started" ...})` / `{"type": "worker_finished" ...}`
  （`:445/510`），具备逐帧推送的底层能力。
- **子 Agent 输出契约**：`SUBAGENT_SYSTEM_SUFFIX` 强制子任务产出自包含结论 +
  `## 执行摘要`（`:138-148`），天然适合做「助手消息」折叠卡片的内容源。
- **SSE 骨架已通**：后端在 fan-out 开始/结束时发 `type="subagents"` chunk
  （`chat_service.py:5685` started / `:5729` aggregated）。
- **前端泳道卡已点亮**（§15.2 阶段 A 已完成）：`useAgentChatStream.ts` 有
  `case 'subagents'`，`agentHub.ts` 有 `onSubagentFanout`，复用
  `OverdriveProgressCard.vue` 渲染 tasks[] 泳道（readonly 模式）。
- **群聊三件套可复用**（§14.2）：`senderAgent` 气泡皮肤 + `OverdriveProgressCard.vue`
  泳道 + `AskUserCard.vue` 决策弹窗。
- **多波次的工具循环已支持**：fan-out 是普通工具调用，每轮限 1 次
  （`subagent_max_children_per_message`），但工具循环可多轮 → 顺序多波天然可行。

### 3.2 确认的差距（含代码位置）

| # | 差距 | 现状代码事实 |
| --- | --- | --- |
| G1 | **阻塞式等待**：父 Agent 在 fan-out 期间干等，无法"趁助手工作时做自己的活" | `chat_service.py:5716` 处 `await` 整个 `run_parallel_subagents`；服务层 `asyncio.gather`（`:220`）等全部子任务结束后才返回 |
| G2 | **per-child 事件被丢弃**：招募后只有 started/aggregated 两帧，中间过程黑盒 | `chat_service.py:5716` 调用 `run_parallel_subagents` 时**未传 `on_event`**，服务层的 `worker_started`/`worker_finished` 事件无人接收 |
| G3 | **无人格层**：子 Agent 只能是已注册专家，无名字/头像/拟人状态 | `tasks[]` 每项必须指定 `agent_id`，且要求该 Agent 有 `features.subagents_spawnable: true`（`:192-196`）；schema 无 `display_name` 字段 |
| G4 | **无逐人结果气泡**：子任务结论只以汇总文本回灌给父模型，前端看不到"助手消息 来自 X" | aggregated chunk 只带 `summary` + `progress[]`（`chat_service.py:5729-5739`） |
| G5 | **ask_user 不冒泡**：子专家遇决策无法弹窗问用户 | `parallel_subagent_service.py:496` 标 `awaiting_input` + `needs_user_input`，但聚合路径只发 `subagents` chunk（§15.3 阶段 B 待做） |
| G6 | **无"团队存续"概念**：多波次只能靠提示词驱动顺序调用，无跨波名册 | 每轮限 1 次 fan-out（`subagent_max_children_per_message`），无 wave/team 状态 |
| G7 | **无聊天侧产物面板**：截图的「全部文件」缺失 | 工作区文件能力（`workspace` 工具包）有，但聊天页无统一产物面板 |
| G8 | **并行上限偏小** | `subagent_max_parallel` 默认 ≤4（§13），截图用了 8 个 |
| G9 | **计划先行（plan.md）无提示词约束** | 各 Agent 提示词未要求"复杂任务先写计划文件再执行" |

### 3.3 与目标形态的总差异结论

**执行内核与截图里的引擎是同构的**——并行调度、失败隔离、事件钩子、汇总信封、输出契约
都已就位；真正缺的是三层"皮"：

1. **事件层**：per-child 事件接进 SSE（G2）+ ask_user 冒泡（G5）；
2. **人格层**：临时名字/头像/拟人状态 + 逐人气泡（G3/G4）；
3. **异步层**（最深）：招募后主 Agent 不阻塞、消息逐个回流（G1）。

第 1、2 层是低成本高性价比改动；第 3 层涉及会话流生命周期，属于重型改造。

---

## 4. 实现方案

分两层施工。**第一层**不改执行模型，用现有阻塞式 fan-out 复刻约 80% 的截图观感；
**第二层**做真异步消息回流，完全对齐 Kimi 内核。第一层全部落地并验证后再评估第二层。

### 第一层：Kimi 体验最小闭环（阻塞式 fan-out + 全事件流 + 人格化）

#### 改动 1：接通 per-child 事件流（后端，解决 G2）

**现状**：`ParallelSubAgentService.run(..., on_event=None)` 支持事件回调，但
`chat_service.py:5716` 的调用点没传。

**做法**：

1. 在 `chat_service.py` 的 fan-out 特判分支（`:5716` 附近）构造一个 `on_event` 异步回调，
   把服务层事件转成 SSE chunk：
   - `worker_started` → `ChatChunk(type="subagents", metadata={"phase": "progress",
     "tool_call_id": ..., "index": ..., "agent_id": ..., "display_name": ..., "status": "running"})`
   - `worker_finished` → 同 type，`status` 为 `succeeded`/`failed`/`awaiting_input`，
     并带上该子任务的 `## 执行摘要` 截取（供前端「助手消息」气泡直接渲染）。
2. **技术难点**：`run_parallel_subagents` 是 `await` 调用，回调在 `await` 内部触发，
   而 SSE generator 需要 `yield`。用 `asyncio.Queue` 桥接：回调里 `queue.put_nowait(event)`，
   外层 generator 用 `asyncio.wait` 同时等 fan-out task 和 queue，有事件就 yield。
3. **双路径约束**：legacy 循环（`chat_service.py` ~5600）与 LangGraph 路径（~6549）
   都要改（遵守 [[langgraph-vs-legacy-dual-path]]，见 `data/ai/README.md` §11.1）。
4. 前端 `useAgentChatStream.ts` 的 `case 'subagents'` 扩展解析 `phase: "progress"`，
   `agentHub.ts` 的 `onSubagentFanout` 按 `toolCallId + index` 更新对应泳道/助手状态。

**涉及文件**：
- `src/omichub/application/services/chat_service.py`（两处）
- `frontend/src/composables/useAgentChatStream.ts`
- `frontend/src/stores/agentHub.ts`
- `tests/unit/test_parallel_subagent_service.py`（补事件流测试）

#### 改动 2：人格层（后端 schema + 提示词，解决 G3）

**原则**：人格是纯展示层，不触碰执行安全边界——底层执行者仍是已注册、有
`subagents_spawnable` 的专家 Agent，权限模型不变。

**做法**：

1. `parallel_subagents` 工具的 `tasks[]` schema 增加可选字段：
   - `display_name: string`（助手昵称，如"柯恩"；由父模型生成）
   - `persona_hint: string`（一句话人格/角色描述，仅用于展示和注入子任务提示词开头）
2. `parallel_subagent_service.py` 的 `_validate_tasks` 透传这两个字段；
   `_run_child` 把它们拼进子任务 prompt 前缀（"你本轮以'柯恩'的身份工作，负责……"），
   并带进 `worker_started`/`worker_finished` 事件与 `ui_payload.progress`。
3. 同一 `agent_id` 允许在多个任务中复用（8 个调研维度 = 8 个 `agent-general` 实例
   各带不同 task + 不同 display_name）——核对 `_validate_tasks` 确认无 agent_id 去重逻辑，
   有则放开。
4. 提示词规范：在 `data/ai/prompts/general.md`（及 `router.md`）增加编排段落：
   - 复杂复合任务**先写 `plan.md`**（工作区写文件工具已有）再执行（解决 G9）；
   - 招募助手时为每个子任务起一个简洁中文名 + 一句话分工；
   - 收到单个助手结果后用一句话点评质量，再决定继续等还是行动；
   - 全部回流后汇总，需要时发起下一波招募（如"调研波 → 写作波"）。
5. 提示词体积遵守 §10 护栏：编排规范控制在 ~30 行内，超出的下沉到 shared 或 Skill。

**涉及文件**：
- `src/omichub/application/services/parallel_subagent_service.py`（schema + validate + child prompt）
- `data/ai/prompts/general.md`、`data/ai/prompts/router.md`
- `tests/unit/test_agent_config_consistency.py` 不需改（不动白名单）

#### 改动 3：ask_user 冒泡（后端，解决 G5，= §15.3 阶段 B 原方案）

按 `data/ai/README.md` §15.3 的既定方案实施：

1. 在发 `subagents.aggregated` 之前，检测 `fanout_envelope.ui_payload.progress` 中是否存在
   `status in {"awaiting_input", "approval_pending"}` 的子任务；
2. 命中则从 `llm_payload.results` 提取对应子任务的 `user_request` 字段，构造
   `ask_request` chunk（复用 `chat_service.py:5911/6549` 的既有格式）额外 yield，
   并暂停本轮 fan-out 等待用户回答；
3. 用户答案经现有 `answerAskRequest`（`agentHub.ts`）作为下一条 user 消息回灌续跑；
4. legacy + LangGraph 双路径都改；
5. `tests/unit/test_parallel_subagent_service.py` 加负路径测试。

#### 改动 4：花名册 + 逐人气泡 UI（前端，解决 G3/G4 展示侧）

1. **「助手招募」花名册卡片**：在阶段 A 的只读泳道卡基础上演进为新组件
   `SubagentRosterCard.vue`（或给 `OverdriveProgressCard.vue` 加 `roster` 模式）：
   - 每个助手一行：头像（按 `display_name` hash 生成几何头像，无名字时回退 Agent 头像）、
     昵称、一句话任务、状态；
   - running 状态显示轮播的拟人状态梗（"正在充电" / "泡了杯茶" / "正在摸鱼"，前端本地
     随机，纯装饰）；
   - 终态显示「已下班」（succeeded）/「请假了」（failed）。
2. **「助手消息」气泡**：`worker_finished` 事件到达时，在消息流插一条可折叠气泡
   「助手消息 | 来自 {display_name}」，内容 = 该子任务的 `## 执行摘要`；
   折叠态只显示标题行，展开看全文。
3. **主 Agent 点评**：由提示词驱动（改动 2.4），模型在每个助手结果回流后自然输出
   一句话点评，无需新组件。

**涉及文件**：
- `frontend/src/components/ai-chat/SubagentRosterCard.vue`（新增或改造）
- `frontend/src/components/ai-chat/types.ts`（`SubagentFanoutEvent` 扩展 display_name/status）
- `frontend/src/composables/useAgentChatStream.ts`、`frontend/src/stores/agentHub.ts`

#### 改动 5：并行上限与配置（解决 G8）

- 将 `subagent_max_parallel` 默认值从 ≤4 提升到 8（对齐截图规模），
  `subagent_max_concurrent`（信号量）保持独立可调，避免资源打满；
- 确认管理端「设置 → 平台设置」暴露该配置；
- `.env.example` 同步注释说明。

#### 第一层验收标准

- 开启 `subagent_fanout_enabled`，让通用助手处理一个"文件解析 + 多维调研"复合任务；
- 页面依次出现：`plan.md` 创建工具调用 → 串行工具链 → 「助手招募」花名册（≥4 个
  有名有姓的助手，状态梗轮播）→ 每个助手完成时出现「助手消息 | 来自 X」气泡 + 花名册
  对应行变「已下班」→ 主 Agent 逐个点评 → 汇总后可再发起一波招募；
- 某子任务触发 `ask_user` 时前端弹 `AskUserCard`，回答后该子任务续跑至终态；
- 回归：`uv run pytest tests/unit/test_parallel_subagent_service.py
  tests/unit/test_agent_config_consistency.py -q` 全绿；
  `cd frontend && npx vue-tsc --noEmit` exit 0；
- 改完重启 `docker restart omichub-web`（[[omichub-web-no-autoreload]]）。

### 第二层：真异步消息回流（对齐 Kimi 内核，解决 G1）

第一层上线验证后再立项。设计要点：

1. **非阻塞招募**：`parallel_subagents` 增加 `async: true` 模式——立即返回
   `{run_id, assistants: [...]}`，子任务转入后台（进程内 asyncio task 或 Celery），
   主 Agent 工具调用当场结束，继续自己的循环（写文件、搜索、总结）。
2. **消息回流通道**：后台子任务完成事件写入会话事件流，以 `room_speech`（senderAgent =
   助手人格）或 `subagents` chunk 推给前端——即截图的「助手消息 | 来自 X」逐条到达；
   遵守 §14.4 统一 SSE 事件契约，不新造 chunk 类型。
3. **等待工具**：新增 `wait_assistants(run_id, timeout)` 工具，主 Agent 显式
   「等待助手消息」，返回当前已完成的助手结论列表（= 截图的「等待助手消息」帧）。
4. **跨波团队存续**：`run_id` 命名的助手团队在会话内存续，第二波招募可引用第一波
   结论（写入 `plan.md` 或上下文摘要传入）。
5. **风险点**：会话流生命周期（用户中途发新消息/断开重连时后台任务的归属与回收）、
   消息落库顺序、并发写同一会话 timeline——需要专门设计评审，建议与 §14 阶段 C/D
   （超频房间统一）合并立项，避免两套异步机制并存。

### 第二层验收标准

- 招募后主 Agent 在助手运行期间能继续输出文本/调用其他工具；
- 助手结果逐个以群聊气泡形式到达，无需等全部完成；
- 刷新页面后花名册与已回流消息可恢复（事件持久化）；
- 中断/重连场景后台任务可回收或续传。

---

## 5. 落地顺序与工作量估算

| 顺序 | 项 | 层 | 侧 | 预估 |
| --- | --- | --- | --- | --- |
| 1 | 改动 1：接通 per-child 事件流 | 一 | 后端为主 | 0.5–1 天 |
| 2 | 改动 2：人格层 schema + 提示词 | 一 | 后端 + 配置 | 0.5 天 |
| 3 | 改动 3：ask_user 冒泡（§15.3 阶段 B） | 一 | 后端 | 0.5–1 天 |
| 4 | 改动 4：花名册 + 逐人气泡 UI | 一 | 前端 | 1–2 天 |
| 5 | 改动 5：并行上限配置 | 一 | 配置 | 0.5 小时 |
| 6 | 第一层联调验收 | 一 | 全栈 | 0.5 天 |
| 7 | 第二层：异步消息回流（含设计评审） | 二 | 全栈 | 另行立项 |

第 1 项是地基（事件不通则 UI 无数据），必须先做；2/3 可并行；4 依赖 1 的事件格式。

---

## 6. 注意事项与约束

1. **双路径同步**：凡涉及工具调用副作用 / SSE 的改动，legacy 与 LangGraph 两条路径
   都要改（`data/ai/README.md` §11.1，[[langgraph-vs-legacy-dual-path]]）。
2. **SSE 契约**：逐人进度复用 `type="subagents"`（新增 `phase: "progress"`），
   助手发言复用 `room_speech`，决策询问复用 `ask_request`——不新造前端不认识的
   chunk 类型（§14.4）。
3. **安全边界不变**：人格层只是展示与提示词包装，子任务执行者仍受
   `subagents_spawnable` 白名单 + 受限工具集（C2 防递归 fan-out）约束；不放开
   agent_id 注册要求。
4. **权限与配额**：`subagent_max_parallel` 提升到 8 后关注模型侧 RPM/配额压力，
   必要时配合 `subagent_max_concurrent` 限流。
5. **改完重启**：`docker restart omichub-web`（omichub-web 无热重载）。
6. **文档同步**：第一层落地后更新 `data/ai/README.md` §15（实现进度），并将本文档
   相关结论合并进 §13.5（可优化项）的勾选状态。
