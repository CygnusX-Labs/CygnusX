# AgentTeams 生产集群化改造实施方案

> **日期**：2026-08-07  
> **状态**：Phase 0/1 的单节点可部署只读 Worker 闭环已完成；共享持久化与 Kubernetes 高可用待平台落地  
> **适用范围**：OmicHub AI 助手、Overdrive、AgentTeams Bridge / Gateway、Kubernetes AgentTeams 控制面  
> **目标**：让“多 Agent”从当前的应用进程内并行调用，升级为可水平扩缩、可追踪、可恢复、可证明并行的生产集群执行模式。

---

## 1. 背景与结论

当前系统已经具备三种不同层级的协作能力：

| 能力 | 当前实现 | 是否真实并行 | 是否适合生产长任务 |
|---|---|---:|---:|
| 对话内 `parallel_subagents` | OmicHub API 进程内 `asyncio.gather` | 是 | 否，受单个 API 请求、模型连接和进程容量约束 |
| Overdrive | Manager 生成 DAG 波次，底层复用对话内 fan-out | 是 | 部分适合，仍依赖 API 请求生命周期 |
| AgentTeams Case | Bridge / Gateway / Work Item / Matrix 协作外壳 | 控制面具备 | 否，生产 Worker 尚未接入真实分析运行时 |

关键现状：

1. `ParallelSubAgentService` 已经使用 `asyncio.gather` 与并发信号量执行子 Agent，因此“应用内并行”是真实存在的。见 `src/omichub/application/services/parallel_subagent_service.py`。
2. `integrations/agentteams/worker/worker_runner.py` 是验收用途的轮询器：非验收任务只返回 `awaiting_skill_runtime`，不会执行 LLM、工具或分析任务。
3. Compose 里的 `agentteams-worker-code`、`agentteams-worker-viz`、`agentteams-worker-scrna` 位于 `agentteams-acceptance` profile，不能作为生产集群证明。

因此，本方案**不替换**已有的低延迟 fan-out，而是新增一条集群执行路径：当任务需要长时运行、可审计交付、跨节点扩缩、失败恢复或人工审批时，由 Manager 创建 AgentTeams Case 并把真实 Work Item 交给专属 Worker 集群执行。

---

## 2. 目标、非目标与成功标准

### 2.1 目标

1. 每个生产 Worker 都能实际执行受限的 LLM 推理、知识检索、代码评审、可视化评审或经审批的 OmicHub 分析操作。
2. 多个无依赖 Work Item 可以被不同 Pod 并发领取、执行和回报；并发性必须能从事件时间线和 trace 中证明。
3. Worker 可水平扩缩、支持 lease 超时回收、幂等重试、取消、人工审批和故障隔离。
4. OmicHub 保持数据、任务、权限的唯一事实来源；AgentTeams Worker 不获得 PostgreSQL、Redis、Docker socket、宿主机或用户数据卷权限。
5. 用户能在 Chat / Studio / AgentTeams Case 页面看到：任务图、责任 Agent、执行状态、有效结论、证据引用、失败原因和最终交付物。

### 2.2 非目标

1. 不把所有普通问答迁移到集群。单 Agent 问答和短小、无副作用的 fan-out 继续在应用内完成。
2. 不让 Worker 直接访问 OmicHub 数据库、Redis、Celery Broker、文件系统或 Docker daemon。
3. 不自定义或假设官方 AgentTeams / HiClaw 版本的 CRD 格式；Team、Worker、Human 等资源使用目标版本官方 schema。
4. 不允许 Agent 自动绕过审批提交、取消或扩大资源规格。

### 2.3 验收成功标准

下列条件全部满足时，才能将“AgentTeams 集群执行”标记为生产可用：

- 三个不同角色 Worker 对三个无依赖 Work Item 的开始时间间隔小于 10 秒，并在 trace 中显示重叠执行区间。
- 每一个 Work Item 都有 `claimed → running → completed | failed | awaiting_approval | cancelled` 的持久化状态和不可变事件记录。
- 某一个 Worker Pod 被删除后，未完成任务在 lease 到期后由其他同角色 Pod 接管，且同一幂等键不产生重复副作用。
- `workflow-submit`、`workflow-cancel`、写文件、运行 Pipeline 等高风险动作没有有效审批 token 时被拒绝。
- 网络策略和部署验证证明 Worker 无法访问 OmicHub PostgreSQL、Redis、Docker socket、用户工作区和宿主机路径。
- 端到端压测、故障注入、权限测试和回滚演练全部通过。

---

## 3. 目标架构

```text
浏览器 / Chat / Studio
        │ SSE / REST
        ▼
OmicHub API ── Router / Overdrive Manager ── 决策：本地 fan-out 或集群 Case
        │                                         │
        │ 本地、短任务                             │ 长任务 / 审批 / 交付
        ▼                                         ▼
ParallelSubAgentService                    AgentTeams Bridge（控制面）
        │                                         │
        ▼                                         ├── Case / DAG / Work Item / Lease / Audit
主 Agent 汇总                                │
                                                  ▼
                                       AgentTeams Controller / 队列
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    ▼                             ▼                             ▼
         Research Worker Deployment     Code Worker Deployment       Analysis Worker Deployment
         (只读检索/会诊)                (代码/可复现性审查)           (审批后的分析提交/监控)
                    │                             │                             │
                    └────────────── AgentTeams Gateway / Bridge ───────────────┘
                                                  │
                                                  ▼
                            OmicHub 受限服务 API / Sandbox / Pipeline API
                                                  │
                                                  ▼
                          产物、任务状态、审计事件、OpenTelemetry Trace
```

### 3.1 路由边界

| 请求特征 | 运行路径 | 原因 |
|---|---|---|
| 普通问答、单专家建议 | 单 Agent Chat | 低延迟、无需调度成本 |
| 2–4 个独立、只读、预计少于 90 秒的子问题 | 应用内 `parallel_subagents` | 已有并发能力，结果可直接注入主 Agent |
| 多专家观点比较、无副作用 | `MultiExpertConsultationService` | 并发收集意见，主 Agent 综合 |
| 需要用户显式开启的短 DAG | Overdrive | 需要过程可视化，但仍可在会话内收敛 |
| 预计超过 90 秒、需要审批/复试、分析 Pipeline、交付归档、跨会话跟踪 | AgentTeams 集群 Case | 必须脱离 API 请求生命周期，并提供可恢复执行 |

路由结果应由统一意图路由器输出以下字段，并持久化到会话和 Case：

```json
{
  "execution_mode": "local_fanout | overdrive | cluster_case",
  "reason": "需要提交正式 RNA-seq 流程并产出可审计交付物",
  "estimated_duration_seconds": 1800,
  "requires_approval": true,
  "required_roles": ["data-steward", "workflow-operator", "quality-auditor"],
  "fallback_mode": "overdrive"
}
```

`cluster_case` 不应由模型单独决定。服务端必须根据工具副作用、预计耗时、用户权限和平台开关二次校验。

---

## 4. 生产 Worker 设计

### 4.1 Worker 类型与职责

| Worker | 可执行能力 | 禁止能力 | 扩缩策略 |
|---|---|---|---|
| `research-worker` | 文献/数据库检索、只读专业会诊、证据整理 | 提交任务、取消任务、写工作区 | 按队列长度扩缩 |
| `code-worker` | 代码审查、脚本建议、受限静态检查 | 生产文件写入、Pipeline 提交、数据库访问 | 按队列长度与模型并发扩缩 |
| `analysis-worker` | 预检、审批后的任务提交、状态监控 | 自主扩大资源、跨项目访问、直接容器控制 | 按 Pipeline 队列与资源配额扩缩 |
| `quality-worker` | 结果质量门、artifact 逻辑引用检查 | 修改产物、重跑任务 | 低并发、按 Case 队列扩缩 |
| `delivery-worker` | 汇总可交付证据、报告打包、归档建议 | 直接删除或覆盖原始数据 | 低并发、按完成 Case 扩缩 |

`agent-code`、`agent-viz`、`agent-scrna` 可以作为专业角色配置，不等于直接复用 OmicHub Chat 内的完整 Agent 权限。集群 Worker 需要单独的、最小化的能力 profile 和模型配置。

### 4.2 Worker 生命周期

1. Worker 用短期身份令牌调用 `GET /v1/work-items/assigned` 获取自己可见的 pending Work Item。
2. Worker 调用 `POST /v1/cases/{case_id}/work-items/{work_item_id}/claim` 原子领取任务；Bridge 写入 lease owner、lease expiry、attempt 与 trace ID。
3. Worker 立即上报 `running`，之后按固定间隔发送 heartbeat；长任务还要上报阶段性进度与可读摘要。
4. Worker 通过 Gateway 调用允许的模型或 OmicHub 受限 API，所有请求携带 `case_id`、`work_item_id`、`attempt`、`trace_id` 和幂等键。
5. 需要高风险操作时，Worker 转为 `awaiting_approval` 并返回审批请求；审批后仅能使用作用域匹配的一次性 token。
6. Worker 返回结构化结果：结论、证据、逻辑 artifact 引用、推荐后续动作和错误摘要；Bridge 验证 payload 后持久化为 `completed` 或 `failed`。
7. Manager 仅汇总 `completed` 且通过契约校验的结果；失败、取消和待审批项必须显式呈现，不得被模型补写为“已完成”。

### 4.3 Work Item 契约升级

在现有 `WorkItemRecord` 的基础上增加或明确以下字段。字段必须进入 Bridge 持久化存储，而不是仅存在 `sandbox_meta`：

```json
{
  "work_item_id": "quality-01",
  "case_id": "case-xxx",
  "target_role": "quality-auditor",
  "capability": "quality-gate",
  "status": "pending",
  "attempt": 0,
  "max_attempts": 3,
  "lease_owner": null,
  "lease_expires_at": null,
  "idempotency_key": "sha256:...",
  "trace_id": "...",
  "depends_on": ["analysis-01"],
  "input_refs": ["omic://project/..."],
  "output_refs": [],
  "approval_scope": null,
  "created_at": "...",
  "updated_at": "..."
}
```

状态转移只允许：

```text
pending → claimed → running → completed
                         ├→ awaiting_approval → running
                         ├→ failed → pending（仅可重试失败）
                         └→ cancelled
claimed / running → pending（lease 超时回收）
```

Bridge 必须拒绝非法跳转、非目标身份领取、过期 lease 上报、重复完成和跨 Case artifact 引用。

### 4.4 幂等、Lease 与失败恢复

- `claim` 使用数据库或具备 CAS 语义的共享存储，不可只依赖进程内 `asyncio.Lock`。
- 所有可能产生副作用的调用使用 `idempotency_key`；同键重试返回已有回执，不重复提交 Pipeline。
- Worker heartbeat 间隔建议为 lease 时长的三分之一；默认 lease 120 秒，最长任务通过受控续租延长。
- Pod 异常、网络断连或超时后，由 Bridge 的 sweeper 回收过期 lease，并将任务重新投递给同角色队列。
- 任何自动重试不得改变输入、资源规格或审批作用域；超过 `max_attempts` 后进入 `failed` 并通知 Manager / 用户。

---

## 5. 安全与数据边界

### 5.1 不可突破的边界

1. Worker 只访问 Bridge / Gateway 与允许的 OmicHub API；禁止访问 PostgreSQL、Redis、Celery、Docker socket、宿主机和用户挂载卷。
2. Worker 接收 `omic://`、对象存储签名 URL 或受限下载引用，不接收任意本地绝对路径。
3. Bridge 使用角色专属 token；Manager token 不下发给浏览器或普通 Worker。
4. 审批 token 必须绑定 `case_id + work_item_id + action + flow_id/task_id + expiry`，且只能消费一次。
5. LLM 原始 prompt、工具完整输出和可能含敏感信息的日志不进入用户可见 Case 摘要；只保留脱敏后的结论与证据引用。

### 5.2 Kubernetes 运行基线

- AgentTeams 控制面、Bridge、Gateway、Worker 分别部署到独立 ServiceAccount 与最小 RBAC。
- 先应用 `deploy/agentteams/kubernetes/network-policy.default-deny.yaml`，再增量开放 Worker → Bridge/Gateway 与必要 DNS/模型出口。
- 所有 Pod：`runAsNonRoot`、`readOnlyRootFilesystem`、`allowPrivilegeEscalation: false`、无 hostNetwork、无 hostPath、无 Docker socket。
- 模型密钥、Bridge token、审批签名密钥通过 Secret Manager / Kubernetes Secret 引用注入；不得提交 `.env` 或命令行参数。
- 使用 HPA/KEDA 依据队列深度、执行时延、模型并发和租约积压扩缩；每种角色设置独立最大副本数和并发上限。

---

## 6. 可观测性与“真实并行”证明

### 6.1 必备事件

Bridge 为每个 Work Item 记录至少以下不可变事件：

```text
work_item.created
work_item.claimed
worker.heartbeat
work_item.running
tool.requested
approval.requested
approval.resolved
work_item.completed | work_item.failed | work_item.cancelled
lease.expired | work_item.requeued
```

事件至少包含 `case_id`、`work_item_id`、`agent_id/role`、`pod_name`、`attempt`、`trace_id`、单调时间戳和脱敏摘要。

### 6.2 Trace 与指标

- OpenTelemetry trace 根节点：`agentteams.case.run`。
- 子 span：`work_item.claim`、`worker.execute`、`gateway.llm`、`omichub.preflight`、`omichub.task.submit`、`quality.gate`、`manager.summarize`。
- 指标：队列深度、claim 延迟、执行时长、并发运行数、lease 回收数、重试次数、审批等待时间、每角色成功率、每 Case 成本、P95/P99 时延。
- UI 中展示 Gantt / 瀑布时间线。三个无依赖任务只有在 `worker.execute` span 实际重叠时，才能显示“并行执行”。

### 6.3 审计查询

管理端应提供以下查询：

1. 一个 Case 的 DAG、每次尝试、所属 Pod、最终结果和审批链。
2. 按角色查看当前队列、运行数、失败率和租约过期数。
3. 按 trace ID 跳转 OmicHub Chat、Bridge 事件、Gateway 调用和任务产物。
4. 查询“伪并行”情况：同波任务开始时间差过大、同一 Worker 串行领取、Manager 在子任务完成前提前总结。

---

## 7. 分阶段实施计划

### Phase 0：冻结边界与基线（1 个迭代）

- [ ] 明确路由阈值：预计时长、工具副作用、审批要求、交付要求。
- [ ] 将 `execution_mode` 写入统一路由结果、会话 metadata 与 Case。
- [x] 为 Bridge Work Item 补齐 lease、attempt、trace、依赖和幂等字段。
- [ ] 将 Bridge CaseStore 从单实例文件存储迁移到共享、可原子更新的持久化存储。
- [ ] 修复并纳入 CI：Bridge 完整契约测试必须可稳定完成，禁止超时卡住。

**退出门槛**：现有应用内 fan-out、Overdrive、Bridge/Gateway 回归测试全绿；不引入生产 Worker。

### Phase 1：只读专业 Worker 集群（1–2 个迭代）

- [ ] 实现 `research-worker`、`code-worker`、`viz-worker` 的真实执行 runtime。
- [x] 为 `agent-code`、`agent-viz`、`agent-scrna` 实现受限 Gateway 只读执行 runtime。
- [x] Runtime 只允许 Gateway 的只读 Agent 能力，并校验固定 schema：`conclusion`、`recommendations`、`evidence_refs`、`risks`。
- [x] Worker 支持 claim、heartbeat、完成、失败、lease 回收和幂等重试。
- [ ] 部署为独立 Deployment，至少每角色 2 个副本；接入 HPA/KEDA。
- [ ] 在管理端展示 Work Item 时间线和真实 Pod 标识。

**退出门槛**：三个独立只读任务可在三个 Pod 并发完成；删除任一 Pod 后任务可回收；无敏感系统权限泄露。

**本轮实施记录（2026-08-07）**：已交付 Bridge Work Item 的 `claim → running → terminal` 状态机、租约/心跳/重试/依赖/幂等字段、受限 Gateway 调用、`agent-code`/`agent-viz`/`agent-scrna` 生产 Worker profile 与三角色并行集成测试。当前 `CaseStore` 仍为文件存储，因此不能将 Bridge 扩为多副本；在迁移至具备原子 claim 的共享数据库或队列、并补齐 Deployment/HPA/KEDA 前，不得将该 Docker Compose profile 宣称为高可用 Kubernetes 集群。

### Phase 2：审批后的分析操作（2 个迭代）

- [ ] 实现 `analysis-worker`，仅通过 Bridge 调用 OmicHub 预检、任务提交、任务查询和取消接口。
- [ ] 接入一次性审批 token、输入快照比对、资源/流程白名单和任务幂等键。
- [ ] 由 `quality-worker` 自动领取完成任务的质量检查 Work Item。
- [ ] 由 `delivery-worker` 生成交付证据包和 Case closeout 建议。

**退出门槛**：真实测试项目可完成“预检 → 审批 → 提交 → 监控 → 质控 → 交付”闭环，且每个动作可审计和回放。

### Phase 3：与 Chat / Studio / Overdrive 收敛（1 个迭代）

- [ ] Router 对符合条件的请求自动提议 `cluster_case`，由用户确认后创建 Case。
- [ ] Overdrive 不再自行长时间持有 SSE；对于集群任务，仅承担规划、进度镜像和最终汇总。
- [ ] Chat 通过 Case 事件订阅展示实时进度；Studio 通过逻辑 artifact 引用打开结果，不直接共享 Worker 文件系统。
- [ ] 为本地 fan-out、Overdrive、AgentTeams Case 统一事件命名、trace 关联和前端展示契约。

**退出门槛**：用户从 Chat 发起、在 AgentTeams 页面观察、回到 Chat 获取最终报告的体验一致；任意页面刷新不丢失状态。

### Phase 4：生产灰度与扩容（持续）

- [ ] 先向管理员/白名单项目开放只读 Case，再开放审批后的分析 Case。
- [ ] 设定队列积压、失败率、租约回收、成本和超时的告警阈值。
- [ ] 根据指标调整角色副本数、模型并发、超时、重试和路由阈值。
- [ ] 每月进行一次 Worker 故障演练、权限回归和审批绕过测试。

---

## 8. 接口与代码改造清单

| 范围 | 改造内容 | 主要位置 |
|---|---|---|
| 路由 | 增加服务端可校验的 `execution_mode` 和 cluster 触发策略 | `src/omichub/application/services/unified_intent_router.py`、`chat_service.py` |
| Case 数据 | Work Item 持久化状态机、lease、attempt、trace、依赖、幂等 | `integrations/agentteams/bridge/.../models.py`、`case_store.py` |
| Bridge | claim/heartbeat/complete/fail/requeue/取消接口与权限校验 | `integrations/agentteams/bridge/.../app.py`、`service.py` |
| Worker runtime | 将 claim adapter 扩展为真实受限执行器；按角色拆镜像/配置 | `integrations/agentteams/worker/`（新增生产 runtime） |
| Gateway | 增加角色能力 allowlist、统一结果 schema、trace 透传与限流 | `integrations/agentteams/gateway/` |
| 部署 | 生产 Deployment、HPA/KEDA、Secret、NetworkPolicy、PDB | `deploy/agentteams/kubernetes/`（新增 manifests/Helm values） |
| API/UI | Case DAG、时间线、审批、失败重试、artifact 与 trace 链接 | `src/omichub/api/v1/agentteams.py`、`frontend/src/` |
| 可观测性 | 事件表/流、OTel、指标、告警、管理员查询 | Bridge audit、OmicHub observability services |

### 8.1 不应删除的既有能力

- `ParallelSubAgentService`：继续承担低延迟、无副作用、少量并行子问题。
- `MultiExpertConsultationService`：继续用于只读会诊，避免为轻量意见创建集群 Case。
- Overdrive 的 DAG 规划和前端过程展示：改为集群任务的 Manager / UI 层，而非长任务执行容器。
- Bridge / Gateway 的身份边界、审批签名和 Matrix 代理：作为集群控制面的安全基础保留。

---

## 9. 测试、演练与发布门禁

### 9.1 自动化测试矩阵

| 测试层级 | 必测场景 |
|---|---|
| 单元测试 | 状态转移、lease、幂等、审批 scope、角色授权、结果 schema 校验 |
| 契约测试 | Bridge ↔ Worker、Worker ↔ Gateway、Bridge ↔ OmicHub API 的成功与拒绝路径 |
| 集成测试 | 三角色并发领取、依赖 DAG、同角色竞争 claim、Pod 崩溃回收、取消与重试 |
| E2E 测试 | Chat 创建 Case → 用户审批 → 集群执行 → 质控 → 汇总报告 → artifact 打开 |
| 安全测试 | 网络隔离、越权领取、跨项目引用、伪造审批、重复提交、敏感日志泄露 |
| 性能测试 | 队列堆积、HPA 扩容、模型限流、Bridge 重启、长任务 heartbeat |

### 9.2 并行验收用例

创建一个包含三个无依赖只读 Work Item 的 Case：

```text
research-01  → research-worker
code-01      → code-worker
viz-01       → viz-worker
```

断言：

1. 三个 `work_item.claimed` 由不同 Pod 发出。
2. 三个 `work_item.running` 的时间差小于 10 秒。
3. 三个 `worker.execute` trace span 存在时间重叠。
4. Manager 只能在三个 Work Item 均进入终态后输出最终汇总。
5. 输出报告含每个角色的结论、证据引用与失败/跳过说明。

### 9.3 故障演练用例

- 执行中删除一个 Worker Pod：任务 lease 到期后应被重新领取，副作用操作不重复。
- Bridge 滚动重启：已完成事件不丢失、运行任务在恢复后继续 heartbeat 或被回收。
- Gateway 超时/模型限流：Worker 以可控退避重试，超过上限进入失败，不阻塞兄弟任务。
- 用户拒绝审批：高风险 Work Item 进入 `cancelled`，下游依赖任务被阻塞并给出原因。

---

## 10. 回滚策略

1. 路由开关：`cluster_case` 只允许在站点设置和项目白名单同时启用；关闭后新请求回退到 Overdrive 或普通 Chat。
2. 在任何 Worker 失败率、租约回收或权限告警超过阈值时，立即停止新 Case 的集群派发，不中断已完成 Case 的查询。
3. 已创建但未执行的 Case 可由 Manager 标记为 `paused` / `cancelled`；已提交 OmicHub Pipeline 的取消仍需原审批 scope。
4. 事件和结果不可删除，只能追加回滚/取消事件，保证审计完整性。
5. 本地 `parallel_subagents` 保持独立可用，避免集群故障导致普通 AI 助手不可用。

---

## 11. 实施前决策清单

以下决策需在开始 Phase 1 前由产品、平台和安全负责人确认：

1. Bridge 的共享持久化后端选型，以及高可用、备份和数据保留周期。
2. 官方 AgentTeams / HiClaw 目标版本、Worker/Team 资源 schema 和升级策略。
3. 每类 Worker 的模型供应商、并发配额、成本预算与降级模型。
4. `cluster_case` 的触发阈值、最大任务数、最大 DAG 深度、默认 lease 和重试次数。
5. 高风险动作的审批人、审批 TTL、取消权限和紧急熔断流程。
6. 产物逻辑引用、对象存储签名 URL、脱敏日志和审计数据的保留规则。

确认上述决策后，实施顺序必须是：**共享状态机与测试门禁 → 只读 Worker → 审批后的分析 Worker → Chat/Studio 收敛 → 灰度扩容**。不得跳过只读集群验收直接开放分析任务。
