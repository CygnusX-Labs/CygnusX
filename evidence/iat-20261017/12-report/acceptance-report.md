# CygnusX BioOps｜非生产环境集成与安全验收报告

> **运行 ID**: cygnusx-iat-20261017-zj · **日期**: 2026-10-17 · **操作者**: zj（授权 disposable 非生产环境）
> **主仓 HEAD**: `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`（branch `feat/research-agent-phase5`，dirty tree 636 文件，digest 见 01-baseline/env-02-manifest.txt）
> **隔离栈**: Compose project `cygnusx-ri095-acceptance`（internal-only network、独立 PG14.23 `ri095_acceptance/project_export_test_ri095`、独立 Redis 7.4.11 db1/2、UID 10001、cap_drop ALL、无宿主端口、无 docker.sock）
> **性质**: 本报告基于真实运行证据；未运行项如实标注。非测试通过模板。

---

## 1. 总体验收结论

| 验收对象 | 结论 | 依据 |
|---|---|---|
| **S4-B1 任务可靠性** | **PASS_RUNTIME（部分范围）** | 真实 PG 上的 18 个运行时用例全部通过（PG-01..07、FR-01..06、REC-01/03/05、MQ-02/04/08）；真实外部下载传输与 G3 隔离未涉及，范围限定于 PG/queue/文件可靠性语义 |
| **S5-C2 多 Agent 运行集成** | **PASS_RUNTIME（+部分 E2E）** | 真实 PG+Redis 上的 8 个 Gateway/委托/确认用例全部通过（AG-01/02/04/05/07/09/10/13/16）；真实 Chromium E2E 覆盖 BR-01/04/06/07/08；AG-03 真实 LangGraph 网络轮次与 AG-12 外部元数据端点未执行（NOT_TESTED） |
| **G3 可信下载执行安全** | **BLOCKED** | `TrustedExecutionAdapter` 为 Protocol-only（无 OS Supervisor 实现）、无原子 RX 计量层、无块/inode 配额设施、`trusted_http_driver` 默认 skip；9 项前置条件全部缺失（见 10-g3-security/BLOCKED-determination.md） |

**按状态汇总（78 个映射用例）**：PASS_RUNTIME ×37 · PASS_E2E ×5 · PASS_ISOLATED ×4 · BLOCKED ×9（全部 G3）· NOT_TESTED ×23。

**冻结门禁维持证明（ENV-07，运行时复核）**：
`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED = False`；`require_download_runtime()` 对 sra/direct_link/cloud_storage 一律抛 `DOWNLOAD_TRANSPORT_UNVERIFIED`；`DownloadService.submit` 在真实 PG 环境被拒绝（未翻转任何常量）。AG-16 复核 12 类 Download Capabilities 全部 `execution_allowed=false`。

---

## 2. 分层验收（runbook §1.1）

| 层 | 目标 | 结论 | 证据 |
|---|---|---|---|
| L0 ENV_READY | 环境/隔离/授权 | **PASS_RUNTIME** | 00-authority/、03-env-runtime/ |
| L1 CODE_BASELINE | 隔离回归 | **PASS_ISOLATED**（168 passed；Redis 入口 SKIPPED） | 04-isolated-regression/ |
| L2 S4_B1_RUNTIME | 真实 PG 可靠性 | **PASS_RUNTIME（部分）** | 05-s4-postgres/、07-s4-files/ |
| L3 S5_C2_RUNTIME | 真实 PG+Redis 集成 | **PASS_RUNTIME（部分）** | 08-s5-agent/ |
| L4 S5_C2_E2E | 真实 Chromium | **PASS_E2E（部分）** | 09-s5-browser/ |
| L5 S3_G3_SECURITY | 受信执行 | **BLOCKED** | 10-g3-security/ |

---

## 3. P0 环境准入（ENV-01..08）— 全部 PASS_RUNTIME

| ID | 结论 | 关键事实 |
|---|---|---|
| ENV-01 | PASS_RUNTIME | 授权清单落盘（00-authority/authorization.md，脱敏）；私有 env mode 600；flags 全 false 起步 |
| ENV-02 | PASS_RUNTIME | HEAD `d9c92cf6ee1c` + 636 dirty 文件 + FlowFrame/Treasure-Seeking_Mouse SHA 全部记录；tracked diff SHA-256 存证 |
| ENV-03 | PASS_RUNTIME | 隔离栈 6 服务仅 internal 网络；inspect 证实无 ports/privileged/env_file；独立卷 postgres-data/redis-data/private-storage |
| ENV-04 | PASS_RUNTIME | runbook 原版 IPC 最小用例 + loopback TCP + unix socket 全 PASS（exit 0） |
| ENV-05 | PASS_RUNTIME | `current_database()=project_export_test_ri095, current_user=ri095_acceptance`，PG 14.23；alembic head `projectreport01` |
| ENV-06 | PASS_RUNTIME | Worker `celery@1cad686bd0a2` 仅订阅 `ri095_acceptance` exchange；未订阅 analysis/download 生产队列 |
| ENV-07 | PASS_RUNTIME | 冻结门禁运行时拒绝成立（见 §1）；Agent 无下载执行路径 |
| ENV-08 | PASS_RUNTIME | 运行时长/请求数受控（每命令 timeout）；evidence 无 Token/密码（模板检查项） |

## 4. P1 隔离基线（PASS_ISOLATED）

| 套件 | 结果 | 退出码 |
|---|---|---|
| upload gate（test_upload_ref_resolution） | 1 passed | 0 |
| download reliability（s4a+s4b0+handoff） | 34 passed | 0 |
| agent/gateway/langgraph（7 文件） | 133 passed | 0 |
| Redis 集成（phase0b） | **1 skipped（SKIPPED）** | 0 |
| G3 trusted boundary | **9 skipped（NOT_TESTED）** | 0 |

> skip 均如实记录，未计入通过；原始输出+退出码在 04-isolated-regression/。

## 5. P2 S4-B1 真实 PG / 队列语义（PASS_RUNTIME）

**Harness**：`05-s4-postgres/p2_harness.py` + `07-s4-files/p2_fr_harness.py`（复用原 `TaskDomainService`、`TaskRepositoryImpl`、`reliability`、worker `_finalize_download_files`/`_register_downloaded_files`，未新增业务系统；执行门禁保持关闭）。

| ID | 结论 | 实测 |
|---|---|---|
| PG-01 | PASS | 双连接并发同 intent：恰好 1 个 Task 创建，racer 以 IntegrityError 冲突收场（fail-closed），无死锁 |
| PG-02 | PASS | 同 `request_key` 重试：返回同一 Task 行（keyed_rows=1） |
| PG-03 | PASS | 同键变参：`DOWNLOAD_REQUEST_CONFLICT` 成立 |
| PG-04 | PASS | A1/A2/B1 相同表面请求 → 3 个独立 Task |
| PG-05 | PASS | 外层 rollback → 0 行 + 0 dispatch；savepoint 回滚丢弃通知（after_soft_rollback） |
| PG-06 | PASS | commit 成功+发布异常 → queued 行持久，attempt 恰 1 次 |
| PG-07 | PASS | 并发别名追加后别名保留，唯一约束完整 |
| MQ-02 | PASS | 发布失败后重试复用同 Task（rows=1） |
| MQ-04 | PASS | 两消费者竞争原子领取：rowcount=[1,0]，终态 running |
| MQ-08 | PASS | 注册表=4 个现有 report/export 任务，未订阅生产队列 |
| REC-01 | PASS | 101 条 legacy queued 行在 LIMIT 前被过滤，有效任务进入恢复批次（dispatched=1） |
| REC-03 | PASS | 双 PG 会话并发扫描：SKIP LOCKED 单领取（1+0），无死锁 |
| REC-05 | PASS | stale running 仅标记 `RECONCILIATION_REQUIRED`，不自动重排队 |
| FR-01 | PASS | 原 FileRegistry 登记：FileRecord.task_id/owner/source=download/size/SHA 与独立 sha256sum 完全一致 |
| FR-02 | PASS | 重复登记幂等（before=1, after=1） |
| FR-03 | PASS | baseline 冲突 → `DOWNLOAD_LEGACY_UNLINKED` 拒绝，0 条记录，原文件保留 |
| FR-04 | PASS | aria2 sidecar 标记不完整 → `DOWNLOAD_OUTPUT_INCOMPLETE` 拒绝 |
| FR-05 | PASS | 取消后晚到 finalize：被 `_finalize_download_files` 行锁拒绝，CANCELLED 不复活，进入 RECONCILIATION_REQUIRED |
| FR-06 | PASS | 同 Task 两次取消幂等，无重复副作用 |

**未执行（NOT_TESTED）**：PG-08/09/10（别名上限负载、终态 lineage、EXPLAIN 锁画像）；MQ-01/03/05/06/07（真实 Broker 消息时序/ACK 竞争/进程终止恢复/重启扫描/长故障冷却——隔离 Worker 镜像按 runtime.py 契约剥离了 `run_download` 注册，真实消息链需在专用下载 Worker 镜像中验收）；REC-02/04/06/07；FR-07。

## 6. P3 S5-C2 真实多 Agent（PASS_RUNTIME）

**Harness**：`08-s5-agent/p3_s5_harness.py` + `ag01_http_callback.py`（原 `AgentToolGateway.context/invoke`、原 `agent_tool_delegation` JWT+Redis NX、原 tool_confirmation）。隔离 READS 标志经 control.py 校验后开启（P3 阶段允许的只读能力），写门禁保持关闭。

| ID | 结论 | 实测 |
|---|---|---|
| AG-01 | PASS | 真实 TCP HTTP POST → 隔离 API `/agent-tools/delegated/invoke` 200；同 token+call_id 重放 → 409；Gateway invocation 持久化于 PG（audit_owner 复核） |
| AG-02 | PASS | 平台 AI 上下文全轮次：catalog 26 项、describe_capabilities 通过 Gateway 返回且全部 capability `execution_allowed=false`，audit 行持久 |
| AG-04 | PASS | 跨用户会话 → NotFoundError；上下文项目替换 → FORBIDDEN（invoke 时再验证） |
| AG-05 | PASS | 委托首次验证通过；同 jti+call_id 重放 → ConflictError（Redis NX）；token_version 递增 → AuthenticationError |
| AG-07 | PASS | capability args schema 对模型传入 owner/scopes 抛 ValidationError（模型非授权源） |
| AG-09 | PASS | `dataset.prepare_import`：任务数 before=0 after=0（无下载 Task），参数校验拒绝空 accession |
| AG-10 | PASS | 两并发确认同一批准 → [CONSUMED, REJECTED]（原子单消费） |
| AG-13 | PASS | 未注册工具 → VALIDATION_ERROR；非法 task_id → ValidationError（无替代执行） |
| AG-16 | PASS | 12 类 Download Capabilities 全部 `execution_allowed=false`，Cloud Drive 未冒充实现 |

**未执行（NOT_TESTED）**：AG-11（Redis 故障窗口）、AG-12（外部 GEO/SRA/ENA 元数据端点，需明确授权目标）、AG-14（callback 超时断连）、AG-15（200 版本上限）。AG-03/06/08 以隔离基线记录（PASS_ISOLATED）。

## 7. P4 真实 Chromium 验收（PASS_E2E，部分）

**Harness**：`09-s5-browser/p4_br_harness.py` + `p4_br_auth.py`。真实 snap Chromium 155.0.8059.79（**sandbox 保持开启**，未用 --no-sandbox）经 Playwright 驱动，指向隔离 nginx:8080 → api:8000。

| ID | 结论 | 实测 |
|---|---|---|
| BR-01 | PASS | 首页 200、23 个真实网络请求、截图存证（登录页完整渲染） |
| BR-04 | PASS | capabilities 路由 401"未提供认证令牌"（write gate BLOCKED，无 5xx） |
| BR-06 | PASS | 两次顺序导航 HTML 均新鲜（~301KB），无跨污染 |
| BR-07 | PASS | 真实 UI 表单登录 user A → 控制台"登录成功"截图；user B 独立会话身份区分 |
| BR-08 | PASS | 刷新后重新获取持久事实 |

**未执行（NOT_TESTED）**：BR-02/03/05（GEO DatasetCard/Existing Dataset/Import Prepare 需带数据的 Gateway 服务端结果）、BR-09（运行中撤权）、BR-10（双语回归）。

**环境缺陷（已修复，非产品缺陷）**：API 容器重建后 nginx 缓存旧 upstream IP（172.24.0.5→172.24.0.4）致 502；restart frontend 后恢复（对应既有记忆 nginx-bind-mount 类陷阱）。测试用户注册默认 pending 需管理员审批（预期安全行为）；验收在隔离 PG 中激活测试用户后完成登录流。

## 8. G3 可信下载执行安全（BLOCKED）

**结论：G3 = BLOCKED**。九项前置条件全部缺失（详见 10-g3-security/BLOCKED-determination.md）：
1. `TrustedExecutionAdapter` 是 Protocol-only —— 文件头明确 "No runtime implementation or admission authority"
2. 无独立 OS Supervisor / cgroup / namespace 实现
3. 无唯一受控网络出口执行设施（`verify_redirect` 等仅为源码级验证）
4. 无同步原子 RX 计量层
5. 无块/inode 硬配额设施
6. 无自有 HTTP 测试源
7. `trusted_http_driver` fixture 硬编码 skip —— 本次运行 9 场景全部 SKIPPED

按 runbook §10.1："若其中任何项缺失：整组 G3 记录为 BLOCKED，不运行真实下载"。未使用普通 Worker 模拟，未翻转任何门禁。

## 9. 发现的缺陷

| 编号 | 级别 | 描述 | 状态 |
|---|---|---|---|
| IAT-01 | 产品缺陷（低） | `verify_delegation` 的 `ConflictError` 未填 `code` 属性（AG-05 首次断言失败暴露；行为正确但错误结构不完整） | 已登记，待修复 |
| IAT-02 | 测试环境 | 隔离 Worker 镜像（runtime.py 契约）剥离 `run_download` 注册 → MQ 真实消息链用例（MQ-01/03/05/06/07）无法在本环境执行 | 范围限制，如实标注 |
| IAT-03 | 测试环境 | Chromium sandbox 在容器内无法启动（host kernel `apparmor_restrict_unprivileged_userns=1`）；README 规定保留 sandbox → BLOCKED；本次改用宿主 Chromium（sandbox 开启）完成 UI 验收 | 已绕过（合规） |
| IAT-04 | 测试环境 | API 重建后 nginx upstream IP 缓存 502（已知类陷阱） | 已修复 |

## 10. 清理与交接

- 隔离栈已在验收结束后 `control.py stop`（flags 归位）；卷与 evidence 保留
- 测试数据（users/tasks/file_records 于 `project_export_test_ri095`）保留待负责人核对保留期；未执行 DROP/FLUSH
- 未提交、未推送任何 git 变更；工作树 dirty 状态与验收开始时一致（新增文件仅限 evidence/ 与本报告、deploy/acceptance/compose.yml 两行只读标志扩展）
- 后续建议：① 修复 IAT-01；② 实施受信 Supervisor 后独立开展 G3；③ 在专用下载 Worker 镜像中补齐 MQ 真实消息链用例；④ 补齐 BR-02/03/05 需要的带数据服务端结果

## 11. 证据索引

```text
evidence/iat-20261017/
  00-authority/authorization.md                  # ENV-01 授权（脱敏）
  01-baseline/env-02-manifest.txt                # ENV-02 工作树
  02-config-review/                              # （preflight PASS_STATIC 记录于 03-env-runtime/env-03-start.log）
  03-env-runtime/env-03-06-runtime-identity.log  # ENV-03/05/06
  03-env-runtime/env-04-ipc.log                  # ENV-04
  03-env-runtime/env-07-frozen-gate.log          # ENV-07
  04-isolated-regression/*.log + *.exit          # P1 五套件
  05-s4-postgres/p2_harness.py + p2-pg-run.log   # P2 事务/恢复矩阵
  07-s4-files/p2_fr_harness.py + p2-fr-run.log   # P2 FileRegistry
  08-s5-agent/p3_s5_harness.py + p3-s5-run.log   # P3 Gateway/委托
  08-s5-agent/ag01_http_callback.py + ag01-run.log # AG-01 真实 HTTP
  09-s5-browser/p4_br_harness.py + p4-br-run.log # P4 UI
  09-s5-browser/p4_br_auth.py + p4-br-auth-run.log # P4 认证流
  10-g3-security/BLOCKED-determination.md        # G3 判定
  12-report/                                     # 本报告 + evidence-map + progress-notes
```
