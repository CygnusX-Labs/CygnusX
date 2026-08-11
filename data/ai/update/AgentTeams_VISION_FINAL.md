# AgentTeams 最终目标：用户参与的单窗口多专家群聊

> 版本：1.0（收敛版）
> 日期：2026-08-11
> 性质：产品架构最终目标与验收标准
>
> 本文替代以下过时/重叠文档成为 AgentTeams 的唯一权威目标描述：
> - `data/ai/update/AgentTeams_update.md`（v1 比赛交付版）
> - `data/ai/update/AgentTeams_update_v2.md`
> - `data/ai/update/AgentTeams_update_v2.1.md`
> - `data/ai/update/AgentTeams_update_v2.2_report.md`
> - `data/ai/update/AgentTeams_codex_prompt*.md`
> - `data/ai/update/update_agent.md` 中关于 AgentTeams 的章节
>
> 旧文档全部移入 `data/ai/update/archive/` 归档，不再作为执行依据。

---

## 1. 一句话定位

**AgentTeams 是 OmicHub 里“用户参与的单窗口多专家群聊”背后的编排框架。**

用户只在当前 AI 助手 / Studio 聊天窗口里发任务、看进展、做决策；多个平台真实 Agent 以各自头像和人格在同一窗口里轮流发言、协作把任务做完；AgentTeams 负责这些专家之间的状态机、工作项派发、审批、审计和跨角色上下文传递。

---

## 2. 最终用户体感

用户发起一个复杂请求后，聊天窗口里依次出现：

1. **Manager 接单**：主 Agent 说明“我将协调几位专家一起完成”。
2. **规划专家发言**：领域 Agent 输出计划摘要（如 RNA-seq 分析师给出分析方案）。
3. **计划确认卡**：用户在窗口内确认 / 修改 / 取消。
4. **专家陆续入群**：数据管理员、领域分析师、代码助手、可视化助手、质控员等以各自头像出现，显示“正在处理”。
5. **逐个回流**：谁先完成，谁先在群里发言，附上结果摘要和产物。
6. **Manager 点评**：主 Agent 对每条结果做验收点评，决定接受、返工或触发下游。
7. **用户被@**：需要决策时（高风险审批、信息不足），群里弹出询问卡片，用户就地回答。
8. **最终交付**：主 Agent 汇总结论、产物清单、质控结论和限制；`agent-delivery` 可生成 Plotly 等动态可视化网页报告，在聊天内直接预览。

整个过程中用户**不跳转到独立 Case 页、不打开 Element 外链、不离开当前聊天窗口**。

---

## 3. 架构总览

```text
┌─────────────────────────────────────────────────────────────────┐
│  前台：AI 助手 / Studio 单窗口聊天                                │
│  复用组件：room_speech / overdrive_progress / AskUserCard        │
│         / OverdriveApprovalCard / 产物下载面板                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ SSE / HTTP
┌────────────────────────────▼────────────────────────────────────┐
│  编排框架：AgentTeams Bridge + Gateway + Worker 集群              │
│  - Case 状态机（15 态）                                           │
│  - Work Item 租约 / 认领 / 重试                                   │
│  - 审批与 HMAC 签名                                               │
│  - append-only 审计事件                                           │
│  - 角色 → 平台 Agent 映射                                         │
│  - MinIO/S3 case 级共享存储                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ execute-readonly / workspace_execution
┌────────────────────────────▼────────────────────────────────────┐
│  执行大脑：OmicHub 平台真实 Agent（data/ai/*.yaml 定义）           │
│  - consultation 端点调用 ParallelSubAgentService                 │
│  - 携带该 Agent 自己的提示词 / Persona / Skill / MCP / 工具白名单   │
│  - 以 requester_ref 对应的真实用户身份运行                        │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 关键边界

- **AgentTeams 不运行 LLM，只编排工单。** 所有“思考”都发生在 OmicHub 平台 Agent 的 consultation 回合里。
- **AgentTeams 不替代平台 Agent 权限体系。** 每个专家能调用什么工具，仍由 `data/ai/*.yaml` 和 Tool Pack 决定。
- **AgentTeams 不新建虚构角色。** 用户看到的每个头像都对应平台上一个真实、已启用的 Agent。
- **用户是群聊成员。** 计划确认、高风险审批、澄清提问都发生在同一条对话流里。

---

## 4. 角色与可用 Agent 清单

### 4.1 固定角色

| 角色 | 平台 Agent | 职责 |
| --- | --- | --- |
| Manager | 当前会话主 Agent（通常为 `agent-general` 路由后的主 Agent） | 接单、选规划专家、审核计划、协调专家、点评结果、汇总交付 |
| 数据管理员 | `agent-data` | 文件/样本/元数据预检、输入完整性审查 |
| RNA-seq 分析师 | `agent-rnaseq` | RNA-seq 规划、解读、结果解释 |
| ATAC-seq 分析师 | `agent-atacseq` | ATAC-seq 规划与解读 |
| 单细胞分析师 | `agent-scrna` | 单细胞完整分析 |
| 单细胞上游专家 | `agent-scrna-upstream` | FASTQ / Cell Ranger / 上游 QC |
| 单细胞整合专家 | `agent-scrna-integration` | 整合、聚类、批次校正 |
| 单细胞高级专家 | `agent-scrna-advanced` | 注释、轨迹、通讯 |
| 代码助手 | `agent-code` | 脚本实现、代码审查、复现 |
| 可视化助手 | `agent-viz` | 图表、出版级绘图 |
| 质量审计员 | `agent-qc` | 独立质控、证据审查、三态结论 |
| 交付报告员 | `agent-delivery` | 交付清单、runbook、证据汇总 |
| 云运维工程师 | `agent-cloud-ops` | 平台健康、资源、故障分诊（管理员场景） |
| 通用助手 | `agent-general` | 需求澄清、跨领域协调 |
| 傻妞 | `shania` | 轻量陪伴、研究思路（不进入重任务编排） |
| MCP 构建师 | `agent-mcp-builder` | MCP 构建相关任务 |

> `agent-router`（星尘 AI）仅作为入口路由，不直接作为群聊中的专家发言；路由后由 `agent-general` 或其他主 Agent 担任 Manager。

### 4.2 角色映射单一来源

角色 → Agent 的映射统一由 `AgentTeamsCapabilityRegistry` 维护，三处消费必须一致：

1. Bridge `service.py` 在创建 Work Item 时解析 target。
2. Gateway `agent_policies` 校验 capability 与 tool 白名单。
3. `CaseRoomProjector` 把审计事件 actor 投影为前端头像/名字。

禁止在 Bridge/Gateway/Worker 里再写一份硬编码映射。

---

## 5. 单窗口群聊流程

### 5.1 触发条件

当用户请求满足以下任一条件时，Manager 决定开启 AgentTeams 群聊：

- 涉及多个领域（如 RNA-seq + 可视化 + QC）
- 需要多步骤执行和独立质控
- 需要用户多次决策
- 明确需要“专家团队协作”

简单问答、单步低风险任务仍由单个 Agent 直接回答，不走群聊。

### 5.2 群聊阶段

```text
Manager 接单
  → 选择 lead planner（真实领域 Agent）
  → planning_running：lead planner 出 plan.md + 参数草案
  → 校验失败 → 退回修订（≤5 轮）
  → 计划确认卡（用户在同窗口确认 / 修改 / 取消）
  → preflight_running：数据管理员等做串行前置
  → executing：多专家并行 Work Item，结果逐个回流到群聊
  → quality_running（可选）：当分析结果确实可能涉及质量检测时，由 agent-qc 独立质控
  → delivery_ready：agent-delivery 汇总交付，支持 Plotly 等动态可视化网页报告
  → closed：Case 关闭，交付清单可下载
```

每个阶段转换都写审计事件，并投影为 `room_speech` 或 `overdrive_progress`。

### 5.3 消息类型

| 场景 | SSE 类型 | UI 形态 |
| --- | --- | --- |
| 专家发言 / 结果回流 | `room_speech` | 带头像、名字的气泡 |
| 专家正在处理 | `overdrive_progress` | 泳道进度条 / 招募卡 |
| 需要用户决策 | `ask_request` | 弹窗卡片 |
| 高风险操作审批 | `overdrive_approval_request` | 审批卡片 |
| 模式切换 | `mode_changed` | 进入/退出群聊态 |
| 产物就绪 | `overdrive_progress` + artifacts | 文件下载入口 |

所有类型都是前端已识别的既有事件，**不新造事件类型**。

---

## 6. 与旧路径的关系

### 6.1 保留并作为唯一前台

- **超频模式（overdrive room）前端组件**：`room_speech`、`overdrive_progress`、`AskUserCard`、`OverdriveApprovalCard` 全部复用。
- **AgentTeams Bridge/Gateway/Worker**：作为编排框架完整保留。
- **consultation 端点 + ParallelSubAgentService**：作为专家执行内核保留。

### 6.2 移除或降级

| 旧路径 | 处理方式 | 原因 |
| --- | --- | --- |
| MAS 编排（orchestrator + DAG） | **移除启用逻辑**，保留代码但默认关闭、不再作为产品入口 | 与单窗口群聊形态冲突；默认关闭已证明不可见 |
| 对话内 fan-out (`parallel_subagents`) 在 AgentTeams 场景下 | **收敛其使用范围**：常规 AI 助手页面继续保留；AgentTeams 群聊内不走 fan-out，改由 Bridge Work Item 编排 | 避免两条 multi-agent 路径竞争；保留常规页面轻量并行能力 |
| AgentTeams Matrix/Element 外链群聊 | **移除 Element iframe 抽屉/外链入口** | 体验割裂，不是产品内原生群聊 |
| 独立 Case 详情页作为主入口 | **保留但仅作为审计详情入口**，不强制跳转 | 复杂任务必须在聊天内闭环 |
| 旧版 v1/v2/v2.1/v2.2 施工文档 | **移入 archive/** | 版本爆炸、互相引用错误 |

### 6.3 历史数据

已存在的 AgentTeams Case 记录和审计事件继续保留，但前端不再展示 Element 外链入口，只展示投影后的 room_speech 时间线。

---

## 7. 数据契约

### 7.1 Case 与 Work Item

沿用现有 `CaseRecord` / `WorkItemRecord` 模型：

- `case_id`：一次用户任务对应一个 Case。
- `work_item_id`：一个专家任务对应一个 Work Item。
- `target`：AgentTeams 身份（如 `agent-rnaseq`、`data-steward`）。
- `agent_id`：由角色映射解析出的平台 Agent ID。
- `execution_mode`：`readonly_consultation` 或 `workspace_execution`。
- `depends_on`：DAG 依赖。
- `context_refs` / `evidence_refs`：结构化上下文引用。
- `plan_hash`：已确认计划的 sha256，未确认不得进入执行。

### 7.2 产物与共享存储

- case 级共享前缀：`s3://agentteams-evidence/{case_id}/`
- 专家产物写入该前缀，下游通过 `artifact_fetch` 拉取。
- 同时登记 `file_records`（`source="agentteams"`），保证 `/files` 页面可见。
- 大文件走 S3，小预览走 `workspace_file_preview`（20KB）。
- **输入文件只读保护**：当 Agent 需要在沙箱中对文件进行操作时，输入文件必须以只读方式挂载/复制到沙箱工作目录，防止专家误删或覆盖原始数据。

### 7.3 群聊消息持久化

- Bridge 审计事件是权威来源。
- `CaseRoomProjector` 把审计事件投影为 SSE chunk。
- 前端按 `event_id` / `idempotency_key` 去重，保证刷新后可重建。
- 事件游标从 `sandbox_meta` 迁移到独立 `agentteams_case_cursors` 表。

---

## 8. 验收标准

### 8.1 功能验收

在一个聊天窗口内跑完一个复合任务（例如 RNA-seq + QC + 可视化）：

1. Manager 接单并说明将协调哪些专家。
2. 规划专家（如 `agent-rnaseq`）在群里发言交付计划。
3. 用户在窗口内确认计划，不跳转页面。
4. 至少 3 个不同职能专家真实参与并发言。
5. 专家结果按完成顺序逐个回流，附带产物。
6. Manager 对每条结果做验收点评。
7. 当分析结果触发质量检测时，`agent-qc` 给出真实三态结论（PASSED / WARNING / BLOCKED）。
8. `agent-delivery` 汇总交付，产物可下载；支持 Plotly 等动态可视化网页报告在聊天内预览。
9. 遇到高风险操作时，窗口内弹出审批卡。
10. 刷新页面后，同一 Case 的发言、进度、状态可重建。

### 8.2 非功能验收

- 所有 16 个 Agent 都可被招募为专家。
- 角色映射单一来源，无硬编码漂移。
- Bridge/Gateway/Worker 仍可通过原有契约测试。
- 简单问答不走 AgentTeams，避免过度编排。
- 不再依赖 MAS / Element 外链；AgentTeams 场景下不再独立使用 fan-out。

### 8.3 完成定义（Definition of Done）

只有当以下全部满足时，才宣布 AgentTeams 收敛完成：

- [ ] 旧版文档已归档，本文件成为唯一权威目标。
- [ ] MAS 编排默认关闭且不再进入主入口。
- [ ] AgentTeams 场景下 fan-out 已收敛；常规 AI 助手页面的 fan-out 能力保留。
- [ ] Element 外链入口已移除。
- [ ] 独立 Case 详情页不再作为强制入口。
- [ ] 角色映射表统一并三处一致。
- [ ] 全部 16 个 Agent 可在群聊中被招募。
- [ ] 计划确认、审批、ask_user 全部在聊天窗口内闭环。
- [ ] 端到端验收场景通过。
- [ ] 回归测试全绿。

---

## 9. 附：旧文档归档清单

以下文件移入 `data/ai/update/archive/`，不再作为执行依据：

- `AgentTeams_update.md`
- `AgentTeams_update_v2.md`
- `AgentTeams_update_v2.1.md`
- `AgentTeams_update_v2.2_report.md`
- `AgentTeams_codex_prompt.md`
- `AgentTeams_codex_prompt_v2.1.md`
- `AgentTeams_codex_prompt_v2.2.md`
- `update_agent.md` 中关于 AgentTeams 的章节（保留该文件本身，但删除其 §12.1 及 AgentTeams 相关段落，统一引用本文）
