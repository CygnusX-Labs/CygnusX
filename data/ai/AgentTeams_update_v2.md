# AgentTeams 多 Agent 协同优化框架 v2（交互体验与"真干活"专项）

> 文档性质：在 v1（`AgentTeams_update.md`，编排骨架已验收）之上的**体验与实效优化规格**。
> 审核日期：2026-08-11（生产实证审核：Bridge 状态库 + OmicHub 任务库 + 容器运行时实测）。
> 问题动机（用户原声）："生成一系列的东西，没有干啥子活"、"交互体验不好"。
> 本文与 v1 的关系：v1 的编排骨架（状态机/租约/审批/审计/只读边界）全部保留；
> v2 只解决两件事——**让 Case 真正产出可用结果**（执行层修复 + 会诊长"手"），
> **让用户在聊天窗口里看得懂、点得动**（交互闭环）。每项给出改动文件、实现要点、验证方式，
> 可直接交 Codex / 开发者逐项执行。顺序严格 P0 → P1 → P2。

---

## 0. 生产实证审核结论（2026-08-11）

审核方法：直接读取 Bridge 生产状态库（`cases.json` + `audit.jsonl`）、OmicHub `tasks` 表、
运行中容器的真实行为（snakemake CLI 实测），并逐文件核查前端投影链。

**总结论：v1 的骨架是对的，但"骨架会动、肌肉没有"——历史上 9 个真实 Case 无一到达
`closed`；会诊专家没有读取真实数据的工具，只能凭问题文本发表意见（这是"没干啥活"的
直接根因）；聊天窗口内用户能看到的事件稀疏、延迟高、交付物不可下载（这是"体验不好"的
直接根因）。**

### 0.1 生产 Case 全量清单（9 个 Case，0 个 closed）

| Case | 状态 | 卡死/失败原因（实证） |
| --- | --- | --- |
| bioops_ff5d…（07-31 预检阻断演示） | `preflight_blocked` | 演示数据，符合预期 |
| bioops_e586…（07-31 预检成功演示） | `approval_pending` | **用户从未批准，悬置 11 天，无任何提醒/超时** |
| bioops_7850…（07-31 浏览器验证） | `approval_pending` | 同上 |
| bioops_fe40…（07-31 防篡改验证） | `execution_failed` | 演示数据 |
| bioops_ed00…（08-01 rna-seq 全流程） | `executing` | **任务 `f85c814d` 在 OmicHub 侧 `queued` 10 天、progress=0，从未被 Worker 消费；Case 无看门狗，永远显示"执行中"** |
| bioops_e94f…（08-01 E2E 差异分析） | `execution_failed` | 任务真实提交但 snakemake 立即退出：`error: argument --logger: invalid choice: 'rich_loguru' (choose from 'rich-loguru')`（R1，**已修，见 P0-1**） |
| agentteams-acceptance ×2（08-04） | `received` | 验收脚本残留，工单 completed 但 Case 状态机未推进 |
| runtime_cancel…（08-10） | `cancelled` | 正常取消链路验证 |

### 0.2 根因分级（R1–R5）

| # | 根因 | 证据 | 后果 |
| --- | --- | --- | --- |
| R1 | **执行层断裂**：Worker 镜像（2026-08-11 02:39 重建，snakemake 9.25.1 + plugin 0.3.0）拒绝 `--logger rich_loguru`；config 默认值与 compose env 都是下划线形 | `core/config.py:273`；`docker-compose.worker.yml:45,105`；容器内 `snakemake --logger rich_loguru` 实测 REJECTED | **当前任何流水线任务提交即败**——Case 的 submit-01 必挂 |
| R2 | **会诊"无手"症**：`evidence_refs` 只是 prompt 里的字符串（`"task:abc123"`），专家 Agent 在 `safe_only=True` 下只有 `ask_user/knowledge_search/web_search/skill` 四类工具，**没有任何读取任务结果/QC 报告/文件内容的工具** | `agent_consultation_service.py:172`（refs 直接 JSON dump 进 prompt）；`parallel_subagent_service.py:398-404`（safe_only 白名单） | agent-qc 质控、agent-rnaseq 解读、agent-delivery 交付全部退化为"LLM 凭空发表意见"——**"生成一系列东西没干活"的直接根因** |
| R3 | **通用型 Case 名存实亡**：`workspace_execution` 通道 OmicHub 侧已实现（工具注入 + 产物登记），但 **Bridge 侧没有任何 Worker 实现认领 workspace 工单**——`production_runner/quality_runner/delivery_runner` 全部只调 `execute_readonly_work_item` | `integrations/agentteams/worker/*.py` 全文核查 | treeplot 类即席任务（v1 §3.4）实际跑不起来 |
| R4 | **静默失败文化**：watch 循环所有异常 `try/except + logger.warning` 吞掉；`execution_failed` / `quality_blocked` 后用户只收到一句状态通知，**没有错误摘要、没有建议动作、没有重试入口** | `agentteams_case_watch_service.py:73-76,101-104,140-142`；`case_room_projector.py:127-133`（仅 5 种事件有发言模板） | 用户看到"失败了"但不知道为何、怎么办 |
| R5 | **交互断点**（详见 §2）：建 Case 需 2 轮 LLM 往返 + 确认卡 + 手动点确认；入口埋藏在"..."菜单只塞文本模板；聊天内只有 20s 轮询状态卡、无进度泳道；两套审批卡并存；交付只给一个 manifest 路径文本，无下载 | 前端核查（§2 各项均附 file:line） | 用户觉得"繁琐、慢、看不见进展、拿不到结果" |

---

## 1. P0 — 让 Case 真干活（执行层与会诊层）

### P0-1 ✅ 已完成（2026-08-11）：snakemake logger 参数修复（R1）

- `src/omichub/core/config.py`：`snakemake_monitor_logger` 默认 `rich_loguru` → `rich-loguru`
  （snakemake ≥9 将插件 entry point `rich_loguru` 归一化为连字符形 choices，下划线形被拒绝）。
- `deploy/docker/docker-compose.worker.yml`：两处 `SNAKEMAKE_MONITOR_LOGGER` 同步改连字符形。
- `src/omichub/infrastructure/execution/local.py`：`_ensure_monitor_logger_plugin` 的版本检查
  守卫放宽为 `{"rich_loguru", "rich-loguru"}`，保证改名后插件版本校验仍生效。
- 已执行：`worker` 与 `rocketmq-worker` 容器重建（env 即时生效，无需重建镜像）；
  容器内 `snakemake --logger rich-loguru --dry-run` 实测通过。
- ⚠️ 遗留：worker 镜像内烘焙的代码默认值仍是旧值，下次镜像构建时随源码更新；
  当前由 compose env 覆盖兜底。

### P0-2 任务看门狗：消灭"永远 executing / 永远 queued"（R1 另一半）

**问题**：Case `executing` 后，Bridge 只被动等 `omic_task.*` 事件；OmicHub 任务若
queued 丢失（Worker 宕机/broker 丢消息）或失败未被 reconcile 捕获，Case 永久悬置，
用户无任何感知。

**施工**：

1. Bridge `service.py` `reconcile_case` 增加超时臂：
   - `omic_task_ids` 关联任务在 OmicHub 侧 `queued` 超过 `TASK_QUEUED_TIMEOUT_SECONDS`
     （默认 900s）→ 审计事件 `omic_task.stalled`，调 `GET /api/v1/tasks/{id}` 复核一次，
     仍 queued 则把 Case 转 `execution_failed` 并附 `failure_reason="task_never_started"`；
   - 任务 `failed` → 现有支路保留，但把 `error_message` 尾部 500 字符摘录进审计事件
     `omic_task.failed.payload.error_excerpt`（当前只有 status，没有原因）。
2. OmicHub 侧（治本）：`task_service.submit` 的 enqueue 与 DB 行落地目前是"先写库后投递"
   （`task_service.py:112-122`），投递异常会留下孤儿 queued 行。新增 Celery beat 周期任务
   `requeue_stale_tasks`（间隔 300s）：扫描 `queued` 超过 10 分钟且无 `started_at` 的任务，
   调 `enqueue_task` 重投一次；重投后仍静止的标记 `failed` + `error_message="调度丢失，已自动标记失败"`。
   改动文件：`src/omichub/infrastructure/celery_app/tasks/`（新增）、`celery.py`（beat 注册）。
3. 存量清理：把生产库里 `f85c814d…`（queued 10 天）手动标记 failed，让 Case `bioops_ed00…`
   走 reconcile 落到终态，不再污染演示。

**验证**：单测覆盖 reconcile 超时臂与 requeue 幂等；实测停掉 Worker 提交任务 →
10 分钟内 Case 收到 `execution_failed` 且聊天内可见原因摘录。

### P0-3 会诊长"手"：只读数据访问工具包（R2，本文最重要的一项）

**问题**：专家会诊的信封里 `evidence_refs` 是不透明字符串，专家"看不见"任何真实数据，
质控/解读/交付全是空对空。**这违背 §17.3 自己写下的原则（QC 要锚定确定性 metrics）**。

**设计**：为 consultation 增加一组**平台侧只读解析工具**（不走 MCP、不写库、按
`requester_ref` 鉴权），并让 Bridge 在派单时把引用解析为真实内容摘要随 question 注入：

1. OmicHub 新增只读工具（`tool_configs/tools_schema.yaml` 注册，`read_only_hint: true`，
   因而自动落入 `safe_only` 白名单）：
   - `task_result_summary(task_id)` → 返回任务状态、flow、参数快照、产物清单、
     QC metrics JSON（Q30/比对率/重复率/样本相关性等流水线自算指标）与错误摘录；
   - `task_file_preview(task_id, path, max_bytes=20000)` → 读取任务产物文本头部
     （报告/日志/TSV 前 N 行），二进制拒绝；
   - `workspace_file_preview(path, max_bytes=20000)` → 用户工作区文件预览（权限按
     `requester_ref` 隔离）。
   实现要点：复用 `pipeline_result_service` 与 file_records 的既有读取逻辑；
   所有返回截断（沿用 8000 字符工具结果截断，A12）。
2. `agent_consultation_service.py` 的 prompt 契约升级：
   - 指令中显式列出上述工具及"**凡引用 task:/file: 证据，必须先调用工具读取真实内容，
     禁止凭引用字符串臆测**"；
   - 信封 `evidence_refs` 语义升级为"已核验引用"——QC/解读结论中的关键数值必须能对应到
     `task_result_summary` 返回的 metrics 字段（对齐 §17.4 强化方向 2）。
3. Bridge 侧（不改业务智能，只做数据搬运）：`execute_readonly_work_item` 在 question
   渲染时把 `context_refs` 中的 `task:*` 展开为 `task_result_summary` 的预取摘要
   （经 Gateway 新增只读代理端点，或由 OmicHub 会诊服务在收到 refs 后自行预取——
   **推荐后者**，Bridge/Gateway 零改动）。
4. `agent-qc` 提示词契约（`data/ai/qc.yaml`）：三态结论必须逐项引用 metrics 字段名与数值；
   无 metrics 可引时禁止给 PASSED（落 WARNING 并说明证据缺口）。

**验证**：单测——会诊中专家调用 `task_result_summary` 能拿到真实 QC JSON；
端到端——对一个已完成 RNA-seq 任务发起解读工单，回流信封的 `evidence_refs` 含具体
metrics 字段（如 `qc.mapping_rate=97.2%`），不再是裸 `task:uuid`。

### P0-4 失败诊断与恢复回路（R4）

**施工**：

1. `case_room_projector.py`：`omic_task.failed` / `case.execution_failed` 增加发言模板，
   内容含 `error_excerpt`（P0-2 注入）+ 一句可执行建议（"可在 Case 详情页重试提交 /
   修改参数后重新规划"）。
2. Bridge `service.py`：新增 `retry_case_submission`（复用 `plan_hash` 冻结快照，
   幂等键升版本 `submit-v{n+1}`），暴露 `POST /v1/cases/{id}/retry`；
   OmicHub `agentteams.py` 加代理端点；前端 Case 详情页与聊天内 Case 卡加"重试"按钮
   （仅 `execution_failed` 态可见）。
3. watch 循环的 `except` 兜底（`agentteams_case_watch_service.py`）：连续 3 次同一 Case
   拉取失败时，向聊天投影一条"协作 Case 状态同步异常，请稍后刷新或联系管理员"，
   杜绝彻底静默。

**验证**：构造一个必败任务（非法 flow 参数快照绕过预检的测试桩）→ 用户在聊天内看到
失败原因摘录 + 重试按钮；重试后幂等键升版、审计链完整。

---

## 2. P1 — 交互体验闭环（聊天窗口内看得懂、点得动）

> 前端正以超频 v2 组件为体验标杆（进度泳道、审批卡、产物下载），AgentTeams Case 投影
> 与其复用同一套组件（v1 A10 已确立），以下各项是对齐差距，不是新建组件。

### P1-1 一键建 Case：消灭"两轮 LLM + 文本模板"（R5）

**现状**：`KimiChatInput.vue:871-877` 菜单项只往输入框塞模板文字；`create_agentteams_case`
工具链路是 LLM 首调 → 确认卡 → 用户点确认发消息 → LLM 二调带 `_confirmed` 才真正建单
（`chat_service.py:6232-6296`）。慢且脆弱（依赖 LLM 两次正确决策）。

**施工**：

1. 会话已有足够信息时（统一意图路由判 `case` 且 `project_id/flow_id` 均可解析），
   第一跳 LLM 调用即由后端直接弹确认卡，**用户点击确认后前端直接调
   `POST /api/v1/agent-teams/cases`**（绕过第二次 LLM 往返），Case 卡插入聊天。
   改动：`agentteams_case_tool_service.py` 确认通过路径由"等 LLM 二调"改为
   "确认消息触发后端直接建单"；`ToolCallEntry.vue:107-114` 的确认消息处理同步简化。
2. 输入框"..."菜单的模板项改为打开**结构化建单弹窗**（复用
   `AgentTeamsCasesPanel.vue:214-280` 已有表单，抽成共享组件），填完直接调 API 建单，
   不再伪装成"发给 AI"。
3. 会诊卡"基于此创建协作 Case"按钮（`StudioView.vue:604-607`）同样改为携带
   `consultation_summary` 直接建单，而不是粘贴文本。

**验证**：从点击到 Case `received` ≤ 1 次用户确认 + 1 次 API 调用；聊天内立即出现
Case 卡（无需等 15s watch）。

### P1-2 聊天内进度泳道与更多发言（R5）

**现状**：聊天里 Case 只有 20s 轮询的 `AgentTeamsCaseCard`（状态+下一步执行者）；
room_speech 只有 5 种事件有文本（`case_room_projector.py:127-133`），
`work_item.claimed / preflight 进行中 / 提交中 / 解读中` 等全部静默。

**施工**：

1. `case_room_projector.py` 补发言/进度模板：`work_item.claimed`（"XX 已领取工单"）、
   `omic_task.submitted`（附任务链接）、`omic_task.progress`（节流：每 ≥20% 或状态翻转
   投影一次 `overdrive_progress`）、`remediation_pending`、`delivery_ready`。
2. `work_item.*` 事件投影 `overdrive_progress` 时携带任务栅格数据（每个工单一格：
   角色名/状态/耗时），前端 `OverdriveProgressCard` 已支持渲染——Case 在聊天里获得
   与超频 run 相同的泳道进度卡。
3. `AgentTeamsCaseCard.vue` 增加最近 3 条事件摘要行（来自已有的轮询响应），
   让用户不点进详情页也能感知"在动"。

**验证**：跑一个完整 Case，聊天内可见 ≥8 条进展（含泳道进度变化），
无任何 ≥60s 的"死寂"区间。

### P1-3 实时性：SSE 重连 + 推送替代轮询（R5）

**现状**：聊天内 Case 事件链路是 Celery 15s 轮询（`config.py:140`）；
`agentHub.ts:643-682` 的 agentteams-events SSE **无重连**；Case 卡本身只有 20s 轮询。

**施工**：

1. `agentHub.ts` `startAgentTeamsCaseEvents` 补重连（照搬 `startOverdriveEvents`
   的指数退避 + 游标重放，`agentHub.ts:554-576` 已有样板）。
2. watch 间隔 15s → 5s（`agentteams_case_watch_interval_seconds`；Redis 锁已兜底）。
3. P2 再考虑 Bridge → OmicHub webhook 推送（见 §3），P1 阶段 5s 轮询已够用。

**验证**：断网 30s 恢复后聊天内事件自动续传不丢；Case 状态翻转在聊天内 ≤6s 可见。

### P1-4 统一审批与拒绝理由（R5）

**现状**：Case 审批走 `AgentTeamsCaseCard`（批准/拒绝，拒绝理由硬编码
"用户拒绝当前冻结计划。"，`AgentTeamsCaseCard.vue:69-70`）；超频审批走
`OverdriveApprovalCard`——两套 UI 两套 API。

**施工**：

1. `AgentTeamsCaseCard` 拒绝按钮改为弹出理由输入框（默认文案可改），
   理由随 `rejectCase` 提交并进审计。
2. 审批卡展示 `plan_hash` 短码 + 参数明细折叠区（v1 P0-4b 已在详情页实现，
   聊天卡补齐），用户确认的就是这份快照。
3. 统一视觉：Case 审批卡与 `OverdriveApprovalCard` 的按钮排布/措辞对齐
   （批准并执行 / 拒绝），降低学习成本。

### P1-5 交付可下载（R5）

**现状**：`case.closed` 气泡只有 manifest 路径文本；详情页 manifest 只有裸 JSON 预览；
无产物文件列表、无下载按钮（`AgentTeamsCaseView.vue:469-475`）。

**施工**：

1. `delivery-01` 会诊信封扩展 `artifacts`（沿用 P0-3 的工具，交付 Agent 调
   `task_result_summary` 收集产物清单），Bridge 把 artifacts 写进
   `case.closed` 审计事件 payload。
2. 投影器把 artifacts 投影为超频同款产物区（`OverdriveProgressCard` 的
   "正式交付"分组已支持下载按钮），用户在聊天内直接下载结果文件。
3. manifest 下载：详情页 `manifest_uri` 文本改为"下载 manifest.json"按钮 +
   结构化预览（折叠 JSON 树），API 用既有 `GET /agent-teams/cases/{id}/manifest`
   （`agentteams.py:238-242` 已存在，前端接上即可）。
4. `omic_task_ids` 渲染为任务详情页链接。

**验证**：Case 关闭后，用户在聊天内 1 次点击下载到交付文件；manifest 可下载。

### P1-6 专家视觉身份本地化（R5）

**现状**：气泡 avatar/color 完全依赖后端事件字段，缺省全员同一机器人 Lottie +
同一蓝色（`KimiMessageItem.vue:460-466`）。

**施工**：前端建 `roleIdentity.ts` 静态映射（agent_id → 名字/emoji 头像/主题色），
后端字段缺失时按映射兜底；8 个身份 8 种颜色，Manager 恒紫、QC 恒橙等约定写死，
与 `case_room_projector.py` 的 `ROLE_AGENT_MAP` 注释互相引用。

---

## 3. P2 — 架构收敛与健壮性

1. **Bridge → OmicHub 事件推送**：Bridge 审计流已有 SSE（`/cases/{id}/events/stream`），
   OmicHub 侧把 15s/5s 轮询换成"每活跃 Case 一条长连 SSE 订阅读取 + 断线游标重放"，
   watch 降为 60s 兜底校正。彻底消除聊天内事件延迟。
2. **workspace_execution 的 Worker 认领实现**（R3）：`production_runner.py` 增加
   workspace 工单分支——认领后经同一条 Bridge→Gateway→OmicHub 透传链调
   `mode=workspace_execution` 会诊（OmicHub 侧已实现），结果信封（含 artifacts）
   回写工单。补一个 treeplot 迷你 Case 的集成测试固化。
3. **approval_pending 超时提醒**：Case 悬置超过 N 小时（默认 24h）向聊天投影一条
   "Case 等待您批准已超过 24h"提醒（带批准/拒绝按钮），超过 7 天自动转 `cancelled`
   并通知——消灭 07-31 那两个悬置 11 天的幽灵 Case。
4. **acceptance 残留治理**：`received` 态但所有工单 completed 的 Case（08-04 两个）
   暴露 reconcile 不覆盖"无规划态"入口的问题；reconcile 增加 `received` 态的
   正常推进臂，并清理存量测试 Case。
5. **会诊质量遥测**：每次 consultation 记录 envelope 解析成功率、工具调用次数、
   evidence 引用命中率（结论数值可回溯到 metrics 的比例），进管理端面板——
   让"质控是不是又在空谈"可度量。

---

## 4. 与 v1 / §17 设计决策的关系

v1 确立的四条原则全部保留：角色→平台 Agent 映射、只读执行边界、单窗口投影契约、
业务智能不进 Bridge。v2 没有推翻它们，而是补上它们漏掉的两块：

1. **"只读"不等于"无数据"**：v1 把只读执行边界做成了"专家没有任何读数据的工具"，
   矫枉过正。P0-3 的只读工具包在**不突破三层强制**（Bridge 422 / Gateway 剥离 /
   `safe_only=True`）的前提下把数据读能力还给了专家——所有新工具 `read_only_hint: true`，
   物理上仍不可能写。
2. **"审计可追溯"不等于"用户看得懂"**：v1 的审计链完整但几乎全部沉淀在详情页；
   v2 把审计事件**翻译**成聊天内的进度、诊断与可下载交付（P1-2/P0-4/P1-5），
   审计仍是唯一事实源，聊天只是它的投影。

§17.4 的两个强化方向在 v2 中的落点：QC 锚定结构化 metrics → P0-3 第 1/4 条；
数值级证据绑定 → P0-3 第 2 条 + P2-5 的引用命中率遥测。

---

## 5. v2 验收标准

1. **真闭环**：新建一个 RNA-seq Case，从建单到 `closed` 全程无人工兜底干预，
   流水线任务真实跑完（snakemake returncode=0），聊天内可下载交付文件。
2. **真质控**：agent-qc 的 PASSED 结论中每个关键数值可回溯到
   `task_result_summary` 返回的 metrics 字段；故意喂一个比对率 30% 的任务，
   QC 必须 BLOCKED 且引用具体数值。
3. **真体验**：建单 ≤1 次确认；聊天内进展无 ≥60s 死寂；失败时用户看到原因摘录 +
   重试按钮；断网恢复后事件自动续传。
4. **零悬置**：不存在 queued >10min 无解释的任务、不存在 approval_pending >24h
   无提醒的 Case、不存在 executing 无看门狗的 Case。
5. **通用型落地**：treeplot 迷你 Case 端到端通过（规划→确认→workspace 执行→
   质控→交付，/files 可见产物）。

---

## 6. 施工顺序与验证纪律

- P0-1 已完成（2026-08-11，见 §1）。其余严格 P0 → P1 → P2。
- 每完成一项：Bridge/Gateway/Worker 契约测试回归（`integrations/agentteams/**/tests/`）、
  OmicHub 单测（`tests/unit/`）；后端改动 `docker restart omichub-web`；
  Celery 改动 `docker restart omichub-worker`（worker 栈改动用
  `bash scripts/worker-compose.sh up -d`）。
- 业务智能（诊断建议文案、QC 判定规则）仍只允许写在 OmicHub 侧 Agent/服务里；
  Bridge/Gateway/Worker 只做编排、搬运与审计。
