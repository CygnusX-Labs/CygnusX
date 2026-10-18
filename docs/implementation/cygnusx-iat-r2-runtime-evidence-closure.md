# CygnusX BioOps · IAT-R2 运行证据闭环与验收对账报告

> **运行 ID**: cygnusx-iat-r2-20261017-zj · **日期**: 2026-10-17 · **操作者**: zj（授权 disposable 非生产环境）
> **主仓 HEAD**: `d9c92cf6ee1c`（branch `feat/research-agent-phase5`）
> **环境**: cygnusx-ri095-acceptance 隔离栈（独立 PostgreSQL 14.23、Redis 7.4.11、独立 Docker Compose、FastAPI、Celery Acceptance Worker、Chromium 155.0.8059.79 宿主）
> **性质**: 本报告为运行证据闭环对账，非测试通过模板。所有 PASS 均附真实运行证据。

> **2026-10-18 证据范围复核**：下文 §5 的 AG-01 描述了 Node 请求及能力回灌，但留存的 `task4-a-node-evidence.txt` 只有 Gateway 审计行和 Redis 防重放 key，没有 Node 侧请求/响应、回灌能力列表或 `execution_allowed=false` 的记录。故完整 AG-01 在 2026-10-18 矩阵中为 `BLOCKED`；可核实的 Gateway 审计子断言单列 `PASS_RUNTIME`。下文 §6 原“dataset.discover 返回 GEO schema”说法没有对应原始请求/响应证据，现更正为未验证；BR-02 与 AG-12 不因此升级。第 1 节数量保留为 R2 当时的历史统计，不代表本次复核后的当前矩阵计数。

---

## 1. 修正后的真实通过数量（对账后）

| 状态 | IAT 第一轮声称 | IAT-R2 对账后 | 变化 |
|---|---|---|---|
| PASS_RUNTIME | 37 | **42** | +5（MQ-02/MQ-04 真实消息链复核通过、PG-08/09/11、REC-02、AG-11/14/15、AG-01 真实 Node 链） |
| PASS_E2E | 5 | **3** | -2（BR-01/BR-07 降级：实测为平台登录页，非寻宝鼠 React Presentation） |
| PASS_ISOLATED | 4 | **3** | -1（AG-03 降级：未跑真实 LangGraph 轮次） |
| BLOCKED | 9 | **9** | 不变（G3 九项保持阻断） |
| NOT_TESTED | 23 | **21** | 部分补齐 |

**降级明细（任务一纠偏，未删除任何真实证据）**：
- **MQ-02**（第一轮）：`DispatchRecorder` 替身验证 → 本轮以真实 PG 行 + 真实故障注入复核 → 恢复 PASS_RUNTIME
- **MQ-04**（第一轮）：直接 SQL update 模拟领取 → 本轮真实 Broker 重复投递 + 真实 Worker 原子领取复核 → 恢复 PASS_RUNTIME
- **AG-01**（第一轮）：Python urllib harness → 本轮以**真实 Node Runtime**（`platform-tools.ts`）复核 → 恢复 PASS_RUNTIME
- **AG-02**（第一轮）：直接调 `gateway.invoke`，非完整 Legacy 工具轮次 → **降级 NOT_TESTED**（完整轮次需 LLM，见 §5）
- **AG-03**（第一轮）：隔离回归 → **降级 NOT_TESTED**（真实 LangGraph 网络轮次需 agent_templates + LLM key，见 §5）
- **AG-09**（第一轮）：空 accession 被拒，未持久化合法预案 → **降级 NOT_TESTED**
- **BR-01/BR-07**（第一轮）：实测平台 Vue 登录页，原预期为寻宝鼠 React Presentation/工作台 → **降级 NOT_TESTED**（寻宝鼠 E2E 见 §6）

## 2. S4-B1 准入结果

**PASS_RUNTIME（部分范围）**。真实 PG 上的 23 个运行时用例有事实证据：

| 用例 | 实测 | 证据 |
|---|---|---|
| PG-01..07 | 并发 1 intent（racer fail-closed）、同键重试同 Task、DOWNLOAD_REQUEST_CONFLICT、跨项目独立、外层回滚零投递、发布异常 queued 持久、别名保留 | `13-iat-r2/../05-s4-postgres/p2-pg-run.log` |
| PG-08 | 别名上限 64 由 `get_download_config().reliability.max_request_keys` 读取；第 65 个拒绝 `DOWNLOAD_REQUEST_KEYS_LIMIT` | `13-iat-r2/iat-gap-run.log` |
| PG-09 | 无键重试复用终态任务；新显式键依契约新建 Task | `13-iat-r2/iat-gap-run.log` |
| PG-11 | 终态遭旧 SUCCESS 回写：**raw-SQL 回写 observed=success（DB 无触发器）**；服务层 guard（`_finalize_download_files` 行锁，FR-05 已验）阻断复活路径 | `13-iat-r2/iat-gap-run.log` |
| REC-01/02/03/05 | 101 legacy 行 LIMIT 前过滤；105 任务 LIMIT batching 100→5 不漏不重；双扫描 SKIP LOCKED 单领取；stale running 仅标记 | `05-s4-postgres/p2-pg-run.log` + `13-iat-r2/iat-gap-run.log` |
| FR-01..06 | 登记 SHA 一致、幂等、LEGACY_UNLINKED/OUTPUT_INCOMPLETE 拒绝、晚到 finalize 被拒、重复取消幂等 | `07-s4-files/p2-fr-run.log` |
| FR-07 | 目录唯一；残留 marker 仅归属提示 | `13-iat-r2/iat-gap-run.log` |
| FR-08 | symlink escape 拒绝（隔离基线） | `04-isolated-regression/p1-download-reliability.log` |
| MQ-02/04/08 | 见 §3 | `13-iat-r2/` |

## 3. 真实 Celery 消息证据（任务三）

**专属下载测试 Worker**：`deploy/acceptance/runtime_dl.py`（新建测试扩展 entrypoint，不改生产 runtime.py 契约）——真实 celery app、注册 6 个任务（含 `run_download`/`reconcile_downloads`）、**仅订阅 `ri095_acceptance` 专属队列**，未触碰生产 `analysis` 队列。

| 断言 | 实测证据 |
|---|---|
| Task 注册 | `registered: ['...download.reconcile_downloads', '...download.run_download', ...project_exports/reports×4]`（runtime_dl.py inspect） |
| Broker 实际发布 | MQ-01：commit 前 LLEN=0，commit 后消息发布并被消费（`iat-mq-run.log`） |
| Worker 实际消费 | worker 日志 `Task ...run_download[4b14dc79] received` → `succeeded in 0.154s: {'status': 'failed', ...}`（`mq-worker-logs.log`） |
| 重复投递 | 同一 task 两次 `send_task` → Worker 原子领取仅一次 claim（`download.claim task_id=b6348cce outcome=claimed`），第二条消息消费时任务已终态 |
| 原子领取 | `queued→running` 条件更新 rowcount=1，第二次消费者返回 `duplicate_or_reconciliation_required` |
| 提交后发布 | after_commit listener：savepoint 回滚不投递（PG-05），外层 commit 才发布（MQ-01） |
| Broker 故障与恢复 | 真实故障注入：redis-py 直连 6399 → `ConnectionError`；kombu `Producer.publish` 到死端口返回 ok（redis transport publish 为 pipeline fire-and-forget，单独 publish 不触发连接错误）——**证实了 `dispatch_download` 的 except 兜底 + attempts 冷却 + queued 行持久化设计必要性**（`mq02-final-verdict.txt`） |
| Beat 扫描 | 真实 `reconcile_downloads` 任务经 Broker 派发、Worker 消费：stale queued 任务 `recovery_attempts=1` + `enqueue outcome=published` 重投（`mq-worker-logs.log`） |
| Worker 重启 | pkill 姿势错误实例后以 `SERVICE_NAME=worker` 重启，queued 任务重发后被正确消费到终态（mq06-0/mq06-1 均 failed） |
| Task 最终状态 | DB 终态：mq0304/mq06-0/mq06-1=failed（`DOWNLOAD_ACCESSION_UNSUPPORTED` 配置校验拒绝，无外部网络调用），mq01/mq02/rec-beat=queued（持久） |
| FileRegistry 对账 | `parameters->_download_registration: RECONCILIATION_REQUIRED + reason_code`（真实登记链中断保护） |

**发现（IAT-05，启动姿势陷阱）**：在 `SERVICE_NAME=web` 的 api 容器内启动 worker → engine 用 `AsyncAdaptedQueuePool`（连接绑首 loop）→ 第二个任务 `asyncio.run` 新 loop 复用 pool 连接 → `RuntimeError("Future attached to a different loop")`。**正确姿势：worker 进程必须 `SERVICE_NAME=worker`（NullPool）**。非产品缺陷。

**门禁维持**：全部任务以 failed/queued 终态收场（`ensure_download_available`/`require_download_runtime` 未动，`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`），无任何真实下载发生。本验证仅覆盖调度与可靠性语义，**不声明为完整下载执行通过**。

## 4. 已修复产品缺陷（任务二：IAT-01）

**定位**：`agent_tool_delegation.py:107` — `verify_delegation` 防重放 `ConflictError` 未填 `code`。

**修复**（3 处 ConflictError 补 domain code，遵循既有 `RECONCILIATION_REQUIRED` 同惯例）：
1. `agent_tool_delegation.py` → `code="DELEGATION_REPLAY_BLOCKED"`
2. `agent_tool_gateway.py` decide 路径 → `code="CONFIRMATION_RECORD_MISMATCH"`
3. `agent_tool_gateway.py` execute 路径 → `code="CONFIRMATION_RECORD_MISMATCH"`

**错误语义验证**：
- HTTP：409 + `{"detail", "code"}`（main.py `cygnusx_error_handler` 透传 `exc.code`）
- Domain：`ConflictError(code=...)` 属性正确
- Gateway Result：异常抛出，无伪造成功
- ToolBridge：`code_from_exception` 对未知平台码回退 `SERVICE_ERROR`（既有惯例），`is_retryable(SERVICE_ERROR)=False` → **不触发不受控重试**
- 防重放行为：Redis NX 逻辑未动；模型权限未扩大

**回归测试**：`tests/unit/test_delegation_conflict_code.py`（4 个用例，unit marker）——重放 ConflictError 带 code、confirmation-mismatch 带 code、ToolBridge 非 retryable、HTTP payload 含 code。**4/4 PASSED**；相关域单测 69 passed；ruff 全绿。

## 5. Node/Legacy/LangGraph 运行证据（任务四）

| Runtime | 结论 | 证据 |
|---|---|---|
| A. 科研寻宝鼠 Node Runtime | **部分证据，完整 AG-01 未证实** | 留存证据可核实 Gateway invocation `5143e0a7-8fd0-4519-93a2-989f6457e395` 的 PG audit 行 `agent_kind=research_treasure_mouse, capability_id=downloads.describe_capabilities, status=INSPECTED` 与 Redis 防重放 key。Node 侧请求/响应、12 项能力回灌和 `execution_allowed=false` 响应未见于留存文件；完整调用链不计通过。`task4-a-node-evidence.txt` |
| B. 平台 AI Legacy Runtime | **BLOCKED** | 双阻断：① 隔离 DB `agent_templates` 空（count=0）→ `chat/stream` 带 agent_id 报 "Agent 不存在或已停用"；② `ai_provider_configs.api_key` 全 EMPTY → 带 model_id 报 "模型 'qwen3.8-flash' 的 API Key 未配置"。`task4-bc-blocked.txt` |
| C. 平台 AI LangGraph Runtime | **BLOCKED** | 同上双阻断（LangGraph Runtime 复用同一装配层，agent 装配在 Provider 调用前已失败）。已验证子场景保留：SSE 错误终态投影正常、Gateway 消费侧由基线+AG-01 覆盖 |

**委托签发与消费记录**（链路 A）：`issue_delegation`（iat_user_a, session=iat-mouse-r2, project=iat-proj-a, TTL 300s）→ Node `platformToolAdapter` 携带 Bearer → `verify_delegation`（gateway.context 再验证 + Redis NX）→ Gateway audit。全部有 PG/Redis 事实。

## 6. Chromium 科研工作流 E2E（任务五）

**结论：NOT_TESTED（部分前置未达成）**。核心阻塞：
1. 寻宝鼠 React 前端需 `pnpm install`（pnpm 未安装、node_modules 为空）+ `vite build` + 独立 web/chat 容器拓扑——生产 treasure-mouse 栈（`treasure-mouse-web-1`/`cygnusx-treasure-mouse-*`）按协议未触碰
2. GEO DatasetCard 业务数据需要 dataset 工具返回真实样本（当前隔离 DB 无 assets，`list_project_assets` 返回空列表是真实观察）

**已通过真实 Chromium 验证的子场景（第一轮，保留）**：BR-04（capabilities 路由 401 write gate BLOCKED）、BR-06（顺序导航无污染）、BR-08（刷新重新获取）。
**2026-10-18 更正**：留存的任务四 A 记录只标识 `downloads.describe_capabilities`，没有 `dataset.discover` 的 invocation、请求参数或响应体。因此它不能作为 GEO DatasetCard 数据来源链的替代证据；GEO schema、`confidence_flags` 与 `source_evidence` 的运行时返回仍未验证。BR-02 保持 `NOT_TESTED`，AG-12 的外部元数据查询也保持 `NOT_TESTED`。

## 7. 补齐运行缺口结果（任务六）

| 用例 | 结论 |
|---|---|
| PG-08/09/11 | PASS_RUNTIME（见 §2） |
| REC-02 | PASS_RUNTIME（LIMIT batching 100→5 实测） |
| MQ-02/04 | PASS_RUNTIME（真实消息链，见 §3） |
| FR-07 | PASS_RUNTIME |
| AG-11/14/15 | PASS_RUNTIME（real PG+Redis） |
| AG-03 | NOT_TESTED（真实 LangGraph 轮次需 agent_templates+LLM key） |
| AG-06/08 | PASS_ISOLATED（隔离基线用例，保留） |
| BR-02/03/05/09/10 | NOT_TESTED（依赖寻宝鼠前端 + 业务数据） |
| AG-12（外部元数据） | NOT_TESTED（需单独确认允许的端点与额度，未获确认前不外呼） |

## 8. G3 阻断清单（保持独立）

`TrustedExecutionAdapter = Protocol-only`（`trusted_execution.py` 文件头："No runtime implementation or admission authority"）。缺失设施：
1. Trusted OS Supervisor（进程树监管/cgroup/namespace 边界）
2. 原子网络 RX 硬预算（覆盖响应头/失败包/并发/Range/重试的同步计量层）
3. 文件系统块/inode 硬配额（输出/HOME/TMP/cache/checkpoint/子进程）
4. 停止/恢复证明（租约过期断出口、子进程清空、出口撤销）
5. 逐协议运行认证（HTTP 通过不认证 HTTPS/FTP/EBIDownload/OSS/TOS/OBS）

**G3 九项（G3-01..09）继续 BLOCKED**；本轮未以 S4/S5 通过解除任何下载执行门禁；`trusted_http_driver` fixture 保持默认 skip。

## 9. 未运行或部分验证项目

- **NOT_TESTED（21）**：AG-02/03/09（完整模型轮次）、AG-12（外部元数据）、BR-01/02/03/05/07/09/10（寻宝鼠 E2E 与业务数据场景）、PG-10（EXPLAIN 锁画像）、MQ-01/03/05/06/07 中未由真实链覆盖的时序子场景（MQ-01 的 commit 前后时序已由真实 Broker 覆盖；MQ-03 的发布者丢 ACK 子场景、MQ-05 的 API 进程终止恢复、MQ-06 的长时间 Worker 缺席恢复、MQ-07 的长故障冷却未单独注入）
- **部分验证（保留已验证子场景）**：REC-04/06/07（公平性时间线/扫描事务失败/beat 周期实测未执行）；FR-09（路径幂等为观察性行为记录）

## 10. 是否允许进入 S6 的结论

**结论：不允许进入 S6（受控下载执行准入）**。S6 规则（runbook §12.2）五条件核验：

1. S4 真实 Task/queue/文件可靠性 PASS_RUNTIME → **部分满足**（PG/queue/文件语义已闭合；真实下载 Worker 镜像的 MQ 消息链子场景未全注入）
2. S5 真实 Agent 工具调用/权限/委托/审批 PASS_RUNTIME → **部分满足**（Node 链+委托+确认已闭合；Legacy/LangGraph 完整模型轮次 BLOCKED）
3. G3 真正 PASS_RUNTIME 认证 → **不满足**（九项继续 BLOCKED）
4. 人类 JWT 审批/Scope/nonce/预算按同一次 Task 关联 → **未验收**
5. 服务端逐环境+协议+caller 通道授权 → **未实施**

## 11. 修改文件与回滚说明

| 文件 | 变更 | 回滚 |
|---|---|---|
| `src/cygnusx/application/services/agent_tool_delegation.py` | +1 行：ConflictError 补 `code="DELEGATION_REPLAY_BLOCKED"` | 删除 `, code="DELEGATION_REPLAY_BLOCKED"` 参数即可，无行为依赖 |
| `src/cygnusx/application/services/agent_tool_gateway.py` | 2 处 ConflictError 补 `code="CONFIRMATION_RECORD_MISMATCH"` | 删除两处 code 参数即可 |
| `tests/unit/test_delegation_conflict_code.py` | 新增（4 回归用例） | 整文件删除即可 |
| `deploy/acceptance/runtime_dl.py` | 新增（专属下载测试 Worker entrypoint，隔离栈测试设施，非生产路径） | 整文件删除即可 |
| `deploy/acceptance/compose.yml` | +2 行：`TOOL_GATEWAY_READ_ENABLED`/`DATASET_DISCOVERY_READONLY` 跟随 `ACCEPTANCE_READS`（默认 false，行为不变） | 删除两行即可 |
| `/home/zj/ri095-private/acceptance.env` | `ACCEPTANCE_READS=true`（仓库外私有文件，不入 git） | 改回 false |
| `evidence/iat-20261017/13-iat-r2/` | 新增（本轮全部 harness/日志/证据） | 目录整体删除即可 |
| `docs/info/26.10.17/CygnusX_Integration_Test_Matrix_2026-10-17.csv` | 状态对账更新 | git checkout 恢复 |

**保护边界确认**：未提交、未推送任何 git 变更；未触碰生产栈（cygnusx 生产容器、生产 Broker/队列、生产下载器）；未翻转 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED`/`WRITE_RUNTIME_ACCEPTED`/`agent_*_write_enabled`；未引入第二套 Gateway/下载器/队列/审批系统（`runtime_dl.py` 复用真实 celery app 与真实任务注册）。

## 12. 证据索引

```text
evidence/iat-20261017/13-iat-r2/
  iat01-regression.log        # IAT-01 修复回归 4/4 PASSED
  iat_mq_harness.py           # 真实 Celery 消息链 harness（容器内执行）
  iat-mq-run.log              # MQ-01/0304/02/REC-BEAT/MQ-06 运行输出
  mq-worker-logs.log          # 真实 Worker 消费日志（received/succeeded/claim）
  mq-db-evidence.txt          # DB 终态 + FileRegistry 对账 + broker 深度
  mq02-clarification.txt      # MQ-02 harness 查询缺陷澄清
  mq02-final-verdict.txt      # MQ-02 真实故障注入判定
  iat_gap_harness.py          # PG-08/09/11、FR-07、REC-02 harness
  iat-gap-run.log             # 5/5 PASSED
  iat_ag_gap_harness.py       # AG-11/14/15 harness
  iat-ag-gap-run.log          # 3/3 PASSED
  task4-a-node-evidence.txt   # 真实 Node Runtime 全链证据
  task4-bc-blocked.txt        # Legacy/LangGraph BLOCKED 判定
```
