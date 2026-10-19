# P0-A/G3 Runtime Identity & Migration Acceptance

## 结论

- 执行身份契约复核：**PASS_ISOLATED**（源码逐点确认 + 现有隔离回归成立）。
- 真实 PostgreSQL 并发（任务二）：**BLOCKED** — 本环境无可授权 PG（无 psql/initdb，docker daemon 无权限），未获得独立测试数据库授权。
- dwnexec04 迁移演练（任务三）：**BLOCKED** — 同上；静态迁移契约有隔离测试，真实 PG 未执行。
- Supervisor 身份接线（任务四）：**CODE_PARTIAL**，接线清单已列；OS 执行证据 **NOT_TESTED**。
- G3 九项 HTTP Runtime 认证：**BLOCKED**（维持 0/9）。
- `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`、`WRITE_RUNTIME_ACCEPTED=False` 未改动。未启动下载、未启动 Supervisor、未连接任何业务数据库。

复核基线：主仓 HEAD `7c028af698762710f5d0b0dc632a060226ac298a`（工作树含多包共享 dirty，与 `evidence/p0a-g3-runtime-identity/current-baseline/` 快照一致推进）。

## 1. 执行身份状态机

```
READY(execution_epoch=0, execution_id=NULL)
  -- consume_execution_admission CAS: status=READY ∧ revoked=false ∧ epoch=expected ∧ attempt匹配
  → CONSUMED(epoch+1, execution_id=uuid5(task, "download-execution:v{VER}:{attempt}:{epoch+1}"))
CONSUMED -- 签名停止回执结算 → SETTLED
READY/CONSUMED -- revoke → REVOKED / RECONCILIATION_REQUIRED
RECONCILIATION_REQUIRED -- 匹配 stopped 回执 → SETTLED
REVOKED/SETTLED -- 终态：revoke 幂等返回，替代结算拒绝
```

关键源码位置：

| 事实 | 位置 |
|---|---|
| 确定性身份生成（uuid5，含算法版本号 `EXECUTION_ID_ALGORITHM_VERSION`） | `src/cygnusx/infrastructure/download/trusted_execution.py:27`（`deterministic_execution_id`） |
| claim CAS + execution_id 持久化 + 确定性校验 | `src/cygnusx/infrastructure/database/repositories/download_execution_admission.py` `consume_execution_admission`（约 290–340 行） |
| 服务端重验：Task 绑定、attempt/epoch、caller、lease nonce | `src/cygnusx/infrastructure/download/supervisor_authority.py` `DatabaseAdmissionAuthority.revalidate` |
| 启动幂等三态契约（not_started/started/unknown） | `src/cygnusx/infrastructure/download/supervisor_server.py` `EnforcedScopeBackend.start_state` 契约 + SupervisorService.start 顺序 |
| 迁移保护 | `alembic/versions/dwnexec04_bind_download_execution_identity.py` |

## 2. 契约复核逐项结论（任务一）

| 检查项 | 结论 | 依据 |
|---|---|---|
| execution_id 完全服务端生成 | **确认** | caller 传入的 execution_id 必须等于 `deterministic_execution_id(task, attempt, epoch+1)`，否则 `DOWNLOAD_EXECUTION_ID_INVALID`；Authority 侧同样以确定性派生值校验请求，错值 `SUPERVISOR_EXECUTION_ID_REJECTED`。caller 无法注入任意身份。 |
| 生成算法稳定且版本兼容 | **确认** | uuid5 namespace=task_id，name 含 `v{EXECUTION_ID_ALGORITHM_VERSION}`，版本升级即产生新身份空间，不与旧身份碰撞。 |
| Task/attempt/epoch/execution_id 绑定不可变 | **确认（隔离）** | CAS 仅在 status=READY、epoch 精确匹配、attempt 匹配时写 CONSUMED+epoch+1+execution_id；重放路径（Authority claim 时 status=CONSUMED）要求 epoch 精确等于已消费 epoch 且 execution_id 精确匹配，任何偏差 `SUPERVISOR_ATTEMPT_BINDING_REJECTED`。DB 约束 `uq_download_admission_execution_identity(task_id, execution_id)`。 |
| 不同 Task 不错误复用身份 | **确认（隔离）** | uuid5 namespace 为 task_id；resolve 强制 task_id/owner/caller 匹配；迁移唯一约束含 task_id。 |
| 旧 epoch 无法获得新执行权限 | **确认（隔离）** | claim 后 epoch 单调 +1；renew 要求请求 epoch == 当前持久 epoch 且一次性 lease_nonce 按 (supervisor_id, nonce) 消费，重放 `SUPERVISOR_LEASE_NONCE_REPLAY`。 |
| caller 不能替换执行身份 | **确认（隔离）** | 同第 1 行；caller 仅来自 mTLS 证书映射，HTTP 头/JSON 不参与身份决定。 |
| 审批、预算、环境、工具摘要一致 | **确认（隔离）** | `resolve_execution_admission` 重查 request/source digest、expires、caller；claim 校验 tool_digest、environment_id、request_digest；预算限额从 Budget 行读入 VerifiedAdmission。 |
| 重放不产生第二个有效 claim | **确认（隔离）** | 相同 Task/attempt/epoch/execution_id 重试复用已 CONSUMED 事实（`already_claimed` 路径），不重复扣 epoch、不改预算 reserved/admitted；不同身份的重试被拒。 |

**明确限制**：以上均为 SQLite 隔离证据。数据库 claim 幂等（CAS 唯一行变更）**不等于** Supervisor 进程启动幂等——后者依赖 `EnforcedScopeBackend.start_state` 三态读数，而真实 backend 尚不存在（见 §5）。当前 ``SupervisorService`` 编排已强制 prepare 后读取三态、仅 `not_started` 允许 `exec_once`、`unknown` 走停止对账，隔离回归覆盖两侧 fail-closed，但真实进程不重复启动只能由真实 backend 证明。

## 3. 真实 PostgreSQL 并发（任务二）— BLOCKED

- 环境事实：本机无 psql/pg_ctl/initdb；`docker ps` 权限被拒；未获独立测试数据库授权。按资料包授权边界，未启动任何数据库，未连接业务库。
- 已覆盖的隔离等价物：`tests/unit/test_download_execution_admission.py`（CAS 单次消费、身份拒绝、预算条件预留、回滚、BIGINT 溢出守卫、终态幂等）与 authority/server 套件（`evidence/p0a-g3-runtime-identity/isolated-verification.json`，125/77 项通过记录）。
- 任务二十个场景（并发 Admission、并发 claim、attempt/epoch 隔离、异常/回滚、崩溃重试、撤销竞争、预算竞争）全部 **BLOCKED / NOT_TESTED**。所需 SQL 结果、事务状态、行数、预算变化、原始日志均无真实来源，不虚构。

## 4. dwnexec04 迁移演练（任务三）— BLOCKED

- 静态契约确认（`alembic/versions/dwnexec04_bind_download_execution_identity.py`，已读源码）：
  1. 预检存在 CONSUMED/SETTLED 历史 → 直接 RuntimeError 阻断（CONSUMED/SETTLED 阻断 = 代码确认，真实 DB 未演）。
  2. 预检 execution_id 列已有数据 → 阻断，要求前向对账迁移。
  3. READY 且 execution_id NULL → 转 RECONCILIATION_REQUIRED 并置 revoked（不推断历史身份 = 代码确认）。
  4. downgrade 在存在身份数据时拒绝，只允许空表回退。
- `tests/unit/test_p0a_migration_contract.py` 覆盖上述分支（SQLite/静态），迁移链单 head（`scripts/check_migrations.py` 通过记录在 isolated-verification.json）。
- READY/CONSUMED/SETTLED/RECONCILIATION_REQUIRED 四种历史数据集的真实 PG 演练、迁移异常一致性、重复部署预检、回滚恢复：**BLOCKED / NOT_TESTED**。活动执行期间的受控停机与状态对账规程在既有报告中已定义，本轮无可迁移实例，无操作。

## 5. Supervisor 身份接线清单（任务四）

| 问题 | 当前答案 | 状态 |
|---|---|---|
| 谁拥有可信执行身份 | `DownloadExecutionAdmissionModel.execution_id`（持久真源）+ `deterministic_execution_id` 算法（trusted_execution.py）；Task.parameters._download_execution_binding 是指向 admission/budget 的服务端引用 | CODE_IMPLEMENTED |
| 谁能创建执行实例 | `SupervisorService.start`：受信 Authority claim → backend.prepare → start_state==not_started 才 exec_once；Worker 只能提交持久引用，经 mTLS | CODE_PARTIAL（listener/编排隔离验证；真实 backend 缺失） |
| 谁能续租 | Worker → mTLS client → `renew`：Authority 重验精确 consumed epoch + 一次性 lease_nonce 单次消费 | CODE_IMPLEMENTED（隔离） |
| 谁能请求停止 | Worker stop / 用户取消 / watchdog 过期回收，全部经 `_stop_scope`：先 revoke_egress，再 kill_and_wait_empty，最后 observe 验证 Task/scope/execution/epoch 精确匹配才出 quiescence；revoke 失败 → SUPERVISOR_STOP_INCOMPLETE | CODE_PARTIAL（OS 事实未证） |
| 避免重复启动 | backend 三态 `start_state` 持久契约 + Admission CAS 幂等，两层独立；Worker 只续租明确 running | 契约 CODE_IMPLEMENTED；真实 backend NOT_IMPLEMENTED |
| Worker 死后谁回收 | 独立 watchdog（不依赖 Worker finally），逐 scope 隔离失败、单轮失败保留下轮重试；`expired_scopes` 返回持久 ExecutionBoundaryRequest | CODE_PARTIAL；常驻部署缺失 |
| 必须来自 Supervisor 的证据 | quiescence 观察、进程树空、RX/块/inode 计量、签名停止回执（nonce 单次） | 契约就绪，真实数据面 0 项 |
| 旧 epoch 失效证明 | epoch 单调 + lease_nonce 单次消费 + authority 精确 epoch 重验 | 隔离 PASS；PG 并发未验 |

不得新增第二套下载任务系统：本轮未新增任何 Task/Approval/Queue/Gateway；接线全部复用原 Task/Admission/Budget/FileRegistry。未使用 Mock Supervisor 宣称进程隔离——所有隔离测试的 AsyncMock 明确记为不证明 OS 事实，报告与证据口径一致。

## 6. G3 九项 Runtime 认证

small_file / unauthorized_address / unauthorized_redirect / unknown_length / network_over_budget / disk_quota_exhausted / cancel / worker_sigkill / partial_reconciliation：全部 **BLOCKED**（0/9，`tests/integration/test_download_trusted_http_boundary.py` 维持 skip）。阻断原因不变：无授权非生产 Linux 强制设施（cgroup/netns/mount/quota/RX 数据面）、无独立授权 PG/Redis/Worker、无自有 HTTP 端点。本轮未请求也未获得这些资源。

## 7. 历史数据处理结论

- 已有 CONSUMED/SETTLED 历史的库不能直接应用 dwnexec04，必须前向对账迁移；迁移代码在 DDL 前硬阻断，不会改写财务/审计事实。
- 无身份的 READY 记录转 RECONCILIATION_REQUIRED 并撤销，不猜测执行身份。
- 若历史执行正在运行：迁移前必须完成受控停机（断出口 → 停止全部 scope → 可信空 scope 回执）与状态对账；本轮无活动执行，未操作。

## 8. 证据路径

- 本轮工作树基线：`evidence/p0a-g3-runtime-identity/current-baseline/`
- 隔离回归与迁移静态检查原始记录：`evidence/p0a-g3-runtime-identity/isolated-verification.json`（125/77/71/59 项分集合，不相加）
- 历史隔离日志：`evidence/p0a/`（p0a-final-rerun.log、regression-final.log、final_hashes.json）、`evidence/g3-e2-runtime/`
- 迁移契约测试：`tests/unit/test_p0a_migration_contract.py`；迁移源码：`alembic/versions/dwnexec04_bind_download_execution_identity.py`

## 9. 未解决的安全风险

1. PG 并发原子性只有 CAS 语义与唯一约束支撑，未经真实 PG 双连接证明（阻塞 PA-04/05/07）。
2. `EnforcedScopeBackend` 无真实实现，进程启动幂等与 OS 停止只是契约，存在实现偏离风险。
3. Supervisor 服务默认 authority/backend 为空、未默认装配，生产接线配置未定义。
4. 迁移会取表锁，真实库锁窗口与预检耗时未测。

## 10. 最终验收结论

执行身份契约在源码与隔离层面成立，**未升级为 PASS_RUNTIME**。真实 PG 并发、真实迁移演练、Supervisor OS 执行、九项 HTTP 认证全部维持 BLOCKED。G3 不放行，S6/S7 维持 NO-GO，下载与写门禁保持关闭。本轮仅产出源码复核与本报告，无代码改动、无数据库操作、无提交。


## 11. 2026-10-19 复验

- `scripts/check_migrations.py`：退出 0，迁移链拓扑连通、head 唯一。
- P0-A/G3 定向隔离集合（supervisor authority/server、admission、迁移契约、worker supervisor）：77 passed，退出 0。均为 SQLite/AsyncMock 隔离证据，不构成 PASS_RUNTIME。
- 复验命令与结论记录：`evidence/p0a-g3-runtime-identity/reverify-20261019/`。
- 结论与阻断状态不变：真实 PG 并发、真实迁移演练、Supervisor OS 证据、九项 HTTP 认证维持 BLOCKED；两个运行门禁保持 false。
