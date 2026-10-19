# CygnusX G3-E3 Phase 1R Runtime Acceptance

## 结论

**BLOCKED / NO `PASS_RUNTIME`.** 本轮在环境准入阶段停止，没有连接或迁移 PostgreSQL，
没有创建 cgroup、启动 Supervisor/Worker 或受控进程，也没有运行故障注入。没有重跑
Phase 1 已记录的相同 namespace/cgroup 探针；既有环境原文见
[Phase 1 验收记录](cygnusx-g3-e3-linux-runtime-acceptance.md) 和
[G3 OS enforcement 证据](../../evidence/g3-enforced-scope-runtime/20261019-local.md)。

门禁保持：

```text
DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False
WRITE_RUNTIME_ACCEPTED=False
```

## 测试环境与准入

当前可用环境是受限的本地开发工作区，不是明确授权的独立 Linux 测试机。最近已记录的
只读环境事实：Linux `6.8.0-147-generic`、Bubblewrap `0.9.0`；有效 capability 为零，
`NoNewPrivs=1`；cgroup v2 根只读、属主 `nobody:nogroup`、权限 `555`；user/PID/network/
mount namespace 创建被内核拒绝。没有已配置的独立 PostgreSQL 连接，也没有可用的
Docker daemon。Bubblewrap 已安装不代表 namespace 可用。`clone3(CLONE_INTO_CGROUP)`
在目标环境的 syscall/kernel 支持情况未探测，本轮没有执行 helper。

本轮没有获得以下 Phase 1R 运行身份，因此不具备迁移或启动任何测试资源的准入：

- `Environment ID`、独立测试机/VM 标识、运维授权人和测试结束清理责任人：未提供。
- PostgreSQL 主机、版本、独立测试库凭据及迁移/销毁授权：未提供；未尝试连接生产或未知数据库。
- Supervisor 专用身份、服务证书/调用方映射、固定测试命令及 helper 部署权限：未提供。
- 已委派的 cgroup v2 scope 子树和控制器；可读写的 `cgroup.procs`、`cgroup.events`、`cgroup.kill`：未提供。
- 允许 Bubblewrap 使用的 user、PID、mount、network namespace 策略，以及可用 `clone3` 的内核和 syscall policy：未提供。
- 独占测试目录、UID/GID `10001`、CPU/内存/PID/磁盘额度和清理所有者：未提供。

### 解锁环境要求

运维需提供专用、非生产 Linux VM/runner 和书面授权；不得通过修改生产全局安全设置来满足。
runner 必须启用 cgroup v2，并把专用 scope 子树委派给独立 Supervisor/helper 身份，确认
`cgroup.procs`、`cgroup.events`、`cgroup.kill` 可用且 `clone3(CLONE_INTO_CGROUP)` 未被
内核或 syscall policy 禁止。需允许 Bubblewrap 在该测试环境内创建所需 user/PID/mount/
network namespace。下载执行 UID/GID `10001`、隔离工作目录和资源限制必须预置。现有
backend 会创建并 `chown` scope 工作目录，C helper 会调用 `setgroups`/`setresgid`/
`setresuid`；受信 Supervisor/helper 因此必须具备经运维批准的等效权限（例如受限的
`CAP_CHOWN`、`CAP_SETGID`、`CAP_SETUID`）以及仅针对该委派子树的 cgroup 访问。helper
必须 root-owned、不可被 group/other 写入。普通 Worker 不得获得 root、Docker Socket、
上述特权或任意 cgroup 写权限。

另需一套与生产隔离、版本受支持的 PostgreSQL 测试实例和一次性数据库，允许应用
`dwnscope05`、`dwnscope06` 并进行并发事务测试。提供非生产 Supervisor 配置、测试证书与
caller 映射、固定且无业务凭据的受控命令、唯一测试目录、资源额度、测试时段和明确的
停止/清理责任人。运行前应记录 runner、数据库和源码版本，并确认所有测试目标均无外网
访问需求。未满足以上条件前不得开始 Phase 1R 运行测试。

## 修改文件

- `docs/implementation/cygnusx-g3-e3-phase1r-runtime-acceptance.md`：本轮准入结论、
  未测试矩阵、环境要求和回滚步骤。
- `ARCHITECTURE_DESIGN/CygnusX_download_architecture.md`：追加 Phase 1R 当前能力摘要。

本轮没有修改运行时代码、迁移、配置或门禁，也没有创建测试数据库、cgroup 或进程。
工作树包含其他未提交改动；没有纳入或回滚这些改动。

## 验收矩阵

| 要求 | 状态 | 本轮证据/原因 |
|---|---|---|
| dwnscope05 / dwnscope06 迁移与最终 PostgreSQL schema | `BLOCKED` | 无授权独立 PG；未连接、未迁移 |
| Scope 唯一约束与并发 prepare | `NOT_TESTED` | 无真实 PG；隔离测试不能代替唯一索引竞争 |
| 并发 exec_once claim 与 Admission/Scope 关联 | `NOT_TESTED` | 无真实 PG 锁和事务验证 |
| execution_id 不可替换、epoch 隔离 | `NOT_TESTED` | 未在真实数据库验证约束和关联 |
| 事务回滚、重复迁移及异常恢复 | `NOT_TESTED` | 无一次性 PG；本轮未应用迁移 |
| 单个无网络进程、Scope 持久化和 cgroup 创建 | `BLOCKED` | 无授权 cgroup 子树或 Supervisor；未启动进程 |
| 子进程 cgroup 归属、PID start-time、host boot ID | `BLOCKED` | 没有真实受控进程与 cgroup 事件 |
| Namespace 实际生效和 UID/GID 降权 | `BLOCKED` | namespace 创建受限；无专用 Supervisor/helper 身份 |
| Worker 不持有 Supervisor 特权 | `NOT_TESTED` | 无实际部署的 Worker/Supervisor 身份对照 |
| 进程退出对账、无未授权文件或网络请求 | `NOT_TESTED` | 没有运行受控命令 |
| 20 路 start：最多一个有效进程和一个 Scope | `BLOCKED` | 无真实 PG 和 OS runner |
| 20 路 start：不重复消费 Admission/预算、不产生脱离 Scope 的进程 | `BLOCKED` | 无真实事务、进程数和 cgroup 归属证据 |
| 20 路 start：其余请求复用原事实或安全拒绝 | `NOT_TESTED` | 未执行并发请求 |
| A. DB commit 后、cgroup 创建前崩溃 | `NOT_TESTED` | 未进行故障注入 |
| B. starting 持久化后、进程启动前崩溃 | `NOT_TESTED` | 未进行故障注入 |
| C. 进程启动后、ACK 返回前崩溃 | `NOT_TESTED` | 未进行故障注入 |
| D. Supervisor 运行期间重启 | `BLOCKED` | 无常驻非生产 Supervisor 和真实 Scope |
| E. Worker SIGKILL 后独立回收 | `BLOCKED` | 无 Worker、PG、scope cgroup 和独立 Supervisor |
| F. 同 execution_id 重试 | `NOT_TESTED` | 本轮没有真实 start 请求 |
| G. 旧 epoch 请求重新启动 | `NOT_TESTED` | 未向真实 Authority/Supervisor 发送请求 |
| H. PID 重用或进程身份不匹配 | `NOT_TESTED` | 未运行进程身份故障注入 |
| I. cgroup 创建失败 | `NOT_TESTED` | 未在 OS cgroup 注入失败 |
| J. 强制停止中的部分失败 | `NOT_TESTED` | 未运行 OS 停止流程 |
| 任一不确定状态 fail-closed | `NOT_TESTED` | 本轮未运行故障场景；既有单测仅为 `PASS_ISOLATED` |
| Watchdog 不依赖 Worker finally、lease 到期触发回收 | `BLOCKED` | 无常驻非生产 Supervisor、PG 或真实 scope |
| Supervisor 重启扫描、cgroup 无残留进程 | `BLOCKED` | 没有运行真实 Supervisor 或 cgroup |
| 停止失败保留对账状态 | `NOT_TESTED` | 无真实 cgroup 部分失败场景 |
| 不误杀其他 Task 或清理其他环境 Scope | `NOT_TESTED` | 没有多 Scope/环境 OS 运行证据 |
| 受控网络出口、RX 硬预算、磁盘 block/inode 配额、签名停止回执 | `NOT_IMPLEMENTED` | 当前源码明确拒绝伪造出口撤销/遥测/回执；本轮不扩展实现 |
| 真实 HTTP 下载 | `NOT_TESTED` | 本阶段禁止进入 HTTP 下载阶段 |

既有 `80 passed, 1 skipped` 是 Phase 1 的隔离测试结果，不是 Phase 1R 本轮测试；不计为
`PASS_RUNTIME`。本轮没有新增原始运行日志。环境探针原文和隔离测试命令保留在上述既有
Phase 1 证据文件中，没有复制成新的“通过”证据。

## 失败、拒绝与安全状态

当前可引用的拒绝事实仅限 Phase 1 已记录的 namespace 创建失败、cgroup v2 只读和缺少
独立 PG/OS runner；没有对 Phase 1R 场景重新发起探测。没有已验收的 `Environment ID`、
PostgreSQL 版本、Supervisor 版本、Task/Scope/execution/attempt/epoch、PID 身份或 cgroup
事件，因此 Phase 1R 没有任何可记为 `PASS_RUNTIME` 的运行记录。

## 回滚方案

本轮没有运行资源或数据库变更需要回滚。未来测试必须使用一次性数据库和专属 cgroup
子树：结束时先停止 Supervisor/Worker，确认测试 cgroup `populated 0` 且没有残留 PID，
再导出证据并销毁一次性 runner/数据库。若保留测试数据库，只有在备份并确认 scope 表无
待审计事实后，才可按依赖顺序回滚 `dwnscope06`、`dwnscope05`；不得对生产数据库执行。
代码回滚须由负责人逐文件审查阶段差异，不得覆盖当前工作树中的其他未提交变更。

## 后续安全能力

在真实验收前，HTTP egress controller、DNS/重定向强制、接收前 RX 计量、硬性 block/inode
quota、可信内核观察和签名 quiescence 回执均不视为已实现或已运行验证。网络出口缺失时，
不得把数据库字段或 cgroup 清空等同于 `egress_revoked=true` 或可信停止回执。所有下载和写
门禁继续关闭。

**Phase 1R 结论：BLOCKED。** 当前唯一下一步是取得上述授权 Linux runner 与独立 PostgreSQL，
再按本报告矩阵执行；本轮到此停止，不启动 HTTP 下载阶段。
