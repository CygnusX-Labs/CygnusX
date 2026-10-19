# CygnusX G3-E3 OS Enforcement Runtime

## 验收结论

**NO-GO / BLOCKED。** 本轮没有任何 `PASS_RUNTIME` 项，也没有解除执行门禁：

```text
DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False
WRITE_RUNTIME_ACCEPTED=False
```

`PASS_ISOLATED` 仅表示后文列出的契约和失败关闭行为通过隔离测试。
真实 Linux scope、网络 RX 硬预算、磁盘硬配额、PostgreSQL/Worker 联合运行、
签名停止回执以及九项 HTTP 测试均不是已验收能力。

## 修改文件

- `src/cygnusx/infrastructure/download/linux_scope_backend.py`：持久进程身份和
  退出码、cgroup v2 `cgroup.kill`/`cgroup.events` 清理校验；无网络策略控制器
  时拒绝声称出口已撤销；Supervisor 重启时扫描并尝试清理未终态 scope；启动前
  校验 root-owned digest-pinned command 并接入原子 scope launcher。启动只允许
  `prepared + cgroup empty`；lease 更新采用 running/未过期 CAS。由于当前没有
  可信计量源，`observe()` 明确拒绝返回伪造 RX/quota 数值。
- `supervisor_authority.py` / `supervisor_server.py`：将经 Task 与 Admission
  重新核验的 HTTP URL、allowlisted host/port/path 一并放入 `VerifiedAdmission`；
  Supervisor 在接受 start 前再次做精确匹配，Linux backend 拒绝缺少目标绑定的
  scope。该变更解决目标身份不可传递问题，不构成网络出口或 redirect 强制。
- `deploy/download-supervisor/scope_exec.c`：使用 Linux
  `clone3(CLONE_INTO_CGROUP)` 在创建时将目标进程放入 cgroup v2；helper 部署和
  目标内核路径尚未在授权 OS runner 上验证。
- `src/cygnusx/infrastructure/database/models/download_execution.py`：scope
  增加 PID start-time 和 host boot ID 字段。
- `alembic/versions/dwnscope06_add_process_identity.py`：新增向前迁移。
- `tests/unit/test_linux_scope_backend.py`：PID identity、cgroup population 和
  网络出口未实现时拒绝验收的隔离测试。
- `tests/unit/test_p0a_migration_contract.py`、`dwnexec04`：此前已修复迁移在
  `execution_id` 列创建前查询该列的问题，相关测试验证该顺序。

既有身份链仍复用 Task、Admission、Budget、DatabaseAdmissionAuthority、
SupervisorService、Celery Worker 和 FileRegistry；本轮没有新增第二套下载任务。

## Scope 与身份

当前状态机为 `prepared -> starting -> running -> stopped`，无法确认的状态为
`unknown`。`start_state` 对 `starting`、`unknown`、PID/boot identity 不匹配和
cgroup 状态缺失均不允许重启。数据库唯一约束限定 Task/execution_id 与
scope_ref。Admission claim 仍通过现有 Authority 与 CAS。
并发请求读到 `starting` 时会重读持久状态最多约 5 秒，让首个启动完成 PID/boot
身份登记；只有转为 `running` 且身份和 cgroup 均匹配才复用，超时仍为 `unknown`。
隔离用例覆盖 `starting -> running`；跨进程 20 路 PG/OS 并发仍未实测。
失败转入 `unknown` 时会持久化经格式校验的内部故障码（长度不超过 32 的 ASCII
字母数字/下划线）；不合法文本回退为 `unknown`。该字段仅供恢复诊断，状态仍为
`unknown`，不会改变执行或验收结论。
已有 scope 的 `prepare()` 重用会逐项比较 owner、attempt、execution、epoch、
admission、budget、caller、environment 和 policy revision；任何授权或预算变化
都会拒绝绑定，不复用旧 scope。

当前 Supervisor 存活期间的 wait task 记录进程退出码；仅当 `cgroup.events`
报告 scope 为空才写入终态。Supervisor 重启后没有 OS 保存的退出码时仍为
`unknown`，不会从 PID 消失推断成功。

PID 存活校验现在同时比较 `/proc/<pid>/stat` start-time 和 host boot ID，避免
把同 PID 的新进程当成原执行。启动已由 `scope_exec.c` 的
`clone3(CLONE_INTO_CGROUP)` 在创建时加入 cgroup；helper 部署权限、目标内核
支持和真实 cgroup 归属尚未运行验证。跨 Supervisor 的数据库行锁限制同一 scope
的单次 `exec_once`；“20 个并发请求最多一个有效受控进程”仍待真实 PG/OS runner
验证。

## OS 强制边界

现有 bwrap 启动请求 user/PID/network/mount namespace，清空继承环境，以 UID/GID
10001 启动 host-side child 后再使用 namespace 内 UID/GID 0，只读挂载 `/usr` 和
`/bin`，并把工作目录、HOME、TMP 和 cache 分别绑定到 scope 内目录。启动前检查
runtime UID 可穿越全部 scope 路径父目录，并为三个独立可写目录设置 UID/GID
10001。该参数和
目录所有权尚未由授权 OS runner 实测；网络凭据、所有可写路径和 capability 集合
仍需运行时审计。cgroup 清理只有在 `cgroup.kill` 可用且 `cgroup.events` 明确
报告 `populated 0` 时才将进程状态记为 stopped。PID 消失不再足以证明 scope
清空。

仍缺少真实 Supervisor 服务身份、namespace 验证、checkpoint 路径审计、
块/inode 硬配额和配额
证据。当前环境没有 cgroup 写权限，故这些设施没有运行。

## 网络出口与硬预算

尚无受控 HTTP proxy 或等价的唯一出口。没有实际 DNS/IPv4/IPv6/redirect 授权、
跨连接和 Range/重试同步 RX 预算扣减，也没有同步接收前阻断超额的网络路径。
`revoke_egress` 当前明确返回
`SUPERVISOR_EGRESS_CONTROLLER_UNAVAILABLE`，不再以数据库字段更新冒充系统
出口已撤销。文件大小统计不能替代网络预算。本项：`NOT_TESTED / BLOCKED`。

## 停止、Watchdog 与回执

SupervisorService 保留 `revoke_egress -> kill_and_wait_empty -> observe` 顺序。
缺少网络控制器时停止流程会因出口撤销失败而拒绝 quiescence；cgroup 清理失败
或无法证明 `populated 0` 时保留 `unknown`。Recovery 会枚举持久活动 scope 并
尝试 cgroup 清理。`MutualTLSSupervisorServer.serve_forever()` 已把监听器与周期
watchdog 放入同一 Supervisor 常驻生命周期，并在退出时取消 watchdog；但仓库没有
Supervisor 可执行入口、证书/DB 配置和受管部署单元，因此尚未部署或运行。`evidence()`
仍拒绝，因为没有 Supervisor 私钥与经过认证的 OS 观察。可信签名停止回执：
`NOT_IMPLEMENTED`。

## 联合测试状态

| 项目 | 状态 | 证据 |
|---|---|---|
| PID start-time/boot ID 与 cgroup 状态解析 | `PASS_ISOLATED` | backend 单元测试 |
| 缺少 runtime telemetry 时拒绝构造观察 | `PASS_ISOLATED` | backend 单元测试 |
| 非法 scope 状态及已过期/非 running lease 拒绝重启或续租 | `PASS_ISOLATED` | backend 单元测试；无 PG CAS 运行验证 |
| 未知状态保留校验后的失败原因供恢复诊断 | `PASS_ISOLATED` | backend 单元测试；无 PG 崩溃恢复演练 |
| 已启动进程缺少 PID start-time 时持久转入 `unknown` | `PASS_ISOLATED` | backend 转换单测；无运行时 procfs 故障演练 |
| 常驻入口同时运行监听器和 watchdog 生命周期 | `PASS_ISOLATED` | fake-listener 生命周期单测；无部署/运行验收 |
| Scope 双并发 Supervisor 启动 20 次 | `NOT_TESTED` | 无真实 PG、无 OS runner |
| cgroup kill 和进程树退出 | `BLOCKED` | 当前 cgroup v2 根只读 |
| network namespace 中受控 HTTP | `NOT_TESTED` | egress controller 未实现 |
| RX 硬预算与 Range/重试 | `NOT_IMPLEMENTED` | 无接收路径计量器 |
| block/inode quota | `NOT_IMPLEMENTED` | 无受信 quota helper/filesystem |
| dwnexec04/dwnscope05/dwnscope06 PG 演练 | `BLOCKED` | 未连接或启动授权 PG |
| 九项 HTTP runtime 测试 | `NOT_TESTED` | 九项 skipped，不能计为通过 |
| Admission 到 Task/FileRecord/SHA 对账 | `BLOCKED` | 真实 Worker/PG 未执行 |

## 本轮验证

- Ruff：backend、scope model、相关测试与新迁移检查通过。
- mypy：`linux_scope_backend.py` 定向检查通过。
- 原子 launcher 严格编译：`cc -Wall -Wextra -Werror -O2`，通过。
- 最小 UID、user namespace 与独立 HOME/TMP/cache 启动配置：`CODE_IMPLEMENTED`，
  未在授权 OS runner 运行验证。
- scope 父路径穿越权限检查：单测覆盖 private ancestor 拒绝；`PASS_ISOLATED`。
- 工具二进制只接受解析后位于 `/usr`、所有路径组件 root-owned 且不可由
  group/other 写入的常规可执行文件，并校验 admitted SHA-256。符号链接和摘要
  不匹配拒绝用例通过；正向系统二进制用例因当前 user namespace 将宿主 root
  映射为 UID 65534 而 `SKIPPED`，未计为通过。
- P0-A/Supervisor/backend 定向测试：最新 `71 passed, 1 skipped`，仅隔离测试；
  root-owned 正向 binary 用例因 uid-mapped 环境明确 skip。
  正向 root-owned binary 用例在当前 uid-mapped 环境明确 skip。
- Scope 全绑定一致性（attempt/admission/budget 等）：`PASS_ISOLATED`，无 PG
  并发运行证据。
- Alembic 静态拓扑检查：单 head 通过；没有在 PostgreSQL 应用迁移。
- G3 九项 integration harness：沿用原 fixture 的 `NOT_TESTED` skip；没有把
  skip 计为通过。

## 环境、回滚和剩余风险

本次执行环境 `CapEff=0`、`NoNewPrivs=1`、`/sys/fs/cgroup` 不可写；Docker
daemon 不可访问，未发现本地 `psql`/`initdb`。没有启动数据库、Broker、Worker、
Supervisor listener、HTTP source 或下载任务。原始命令结果记录在
`evidence/g3-enforced-scope-runtime/20261019-local.md`。

源码回滚须逐文件审查 scope model、migration、backend 和测试，不删除已有
Admission/Task/FileRecord 审计事实。任何未来运行回滚都必须先关闭出口、停止并
验证 scope 为空，再对账部分文件；本轮没有运行资源需要清理。

**G3-E3 最终结论：NO-GO。** 当前代码改进了原子 scope 启动、最小 host UID 和独立
可写目录配置、持久进程身份识别及失败关闭清理，
但受控 HTTP、原子网络硬预算、磁盘硬配额、真实 watchdog 部署、
可信停止回执、授权 PG 联合验证和九项真实 HTTP 场景都未完成。不得据此开放
HTTP 下载或 Agent 写权限。
