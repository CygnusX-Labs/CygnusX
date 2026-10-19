# CygnusX G3-E3 Phase 1 Linux Scope Runtime Acceptance

## 结论

**BLOCKED / NO `PASS_RUNTIME`.** 本轮没有创建或启动真实下载进程，没有访问外部网络，
没有修改生产环境。Scope 持久化冲突恢复和启动 claim 的代码及隔离回归已完善；真实
cgroup、namespace、20 路并发、Supervisor/Worker 崩溃恢复和内核停止语义均未验收。

安全门禁保持关闭：

```text
DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False
WRITE_RUNTIME_ACCEPTED=False
```

## 修改文件

- `src/cygnusx/infrastructure/download/linux_scope_backend.py`：并发 scope 插入碰到 DB
  唯一约束冲突时 rollback 并读取已提交行，只有 scope 身份与完整 admission 绑定一致才
 复用；行锁下只有 `prepared` 状态可 claim 启动，`starting`/`running` 的重试不再次启动，
  `unknown`/终态拒绝；Scope DB 行先提交，再建 cgroup；cgroup 准备失败会持久标记
  `unknown`；已启动进程缺少 `/proc` start-time 时先提交 `unknown` 诊断状态。
- `deploy/download-supervisor/scope_exec.c`：受信 helper 源码，使用
  `clone3(CLONE_INTO_CGROUP)` 在进程创建时原子加入 scope cgroup，并在子进程执行前降权。
- `src/cygnusx/infrastructure/database/models/download_execution.py` 与
  `alembic/versions/dwnscope06_add_process_identity.py`：Scope 持久模型和 PID start-time、
  host boot ID、return code 字段迁移。
- `src/cygnusx/infrastructure/download/supervisor_server.py`：Supervisor 依赖契约、确定性
  scope、start-state 重试和启动失败清理编排。
- `tests/unit/test_linux_scope_backend.py`：覆盖唯一插入冲突恢复、持久启动 claim 重入、
  default-deny 恢复扫描、`unknown` 拒绝启动和进程身份缺失等隔离行为；重复 prepare
  不覆盖已持久租约，租约延长仅由 renew CAS 完成。
- `tests/unit/test_download_supervisor_server.py`：覆盖 start 重试、unknown fail-closed、
  停止编排和 watchdog 清理隔离行为。
- `ARCHITECTURE_DESIGN/CygnusX_download_architecture.md`：回写下载/Supervisor 当前实现和
  Phase 1 运行阻塞事实。
- `docs/implementation/cygnusx-g3-e3-linux-runtime-acceptance.md`：本阶段验收交付与
  环境原始探针记录。

没有新增 Task、队列或下载系统；复用既有 Admission、Scope、Supervisor、Worker 和
FileRegistry 结构。

## Scope 生命周期与身份

持久状态为 `prepared -> starting -> running -> stopped`，不确定状态进入 `unknown`。
Scope 唯一性由数据库 `uq_download_scope_execution(task_id, execution_id)` 和
`uq_download_scope_ref(scope_ref)` 约束。`prepare()` 对相同 scope 的并发插入不依赖进程
内存锁：唯一约束冲突方 rollback 后读取同一 scope 并核验 task/owner/attempt/execution/
epoch/admission/budget/caller/environment/policy 全绑定；冲突行缺失或身份不同则拒绝。
DB Scope 行先提交，再创建 OS cgroup；若 cgroup 创建或控制文件检查失败，持久 Scope 转
为 `unknown` 并拒绝启动，避免产生数据库不可发现的 cgroup 子树。

`exec_once()` 在 `SELECT ... FOR UPDATE` 内将 `prepared` 原子转为 `starting`。第二个
Supervisor 即使此前也读到 `not_started`，取得锁后若状态已是 `starting` 或 `running`，
不会再调用 launcher；`unknown` 和其他状态不允许启动。Supervisor 重试经 Authority
核验后复用确定性 scope。Scope 状态为 `starting` 时 `start_state()` 等待最多约五秒读取
持久身份；只有 `running`、PID start-time/host boot ID 一致且 cgroup 显示 populated 才
认定已启动。状态仍不确定时不作成功判断。

原子 helper `deploy/download-supervisor/scope_exec.c` 使用
`clone3(CLONE_INTO_CGROUP)` 设计在进程创建时加入目标 cgroup。helper 在本机以
`cc -Wall -Wextra -Werror -O2` 编译通过，但本轮没有执行它。数据库中记录的 PID、
`/proc/<pid>/stat` start-time、host boot ID、Task、attempt、execution、epoch 与 scope
的真实对应关系因此未获运行证明。

## 当前真实 Linux 环境

只执行只读环境探针和一个无网络 namespace 创建探针；未尝试 sudo、容器、挂载、修改
cgroup 或启动业务服务。

```text
uid=1000(zj) gid=1000(zj) groups=1000(zj),65534(nogroup)
Linux zj 6.8.0-147-generic #147-Ubuntu SMP PREEMPT_DYNAMIC Thu Sep 24 11:33:16 UTC 2026 x86_64
CapEff: 0000000000000000
NoNewPrivs: 1
0::/user.slice/user-1000.slice/user@1000.service/tmux-spawn-e59e94fe-7753-44eb-96f1-c0b15337eab7.scope
cgroup_mount=cgroup2 ro,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot
controllers=cpuset cpu io memory hugetlb pids rdma misc
cgroup_root_owner=nobody:nogroup 555
bwrap=/usr/bin/bwrap, bubblewrap 0.9.0
```

无网络 `unshare --user --map-root-user --pid --net --mount true` 探针输出：

```text
unshare: unshare failed: Operation not permitted
NAMESPACE_CREATE_DENIED
```

Bubblewrap 私有 namespace 探针输出：

```text
exit=1
bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.
```

`/sys/fs/cgroup` 为只读 cgroup v2，当前进程无有效 capability；不能创建 delegated cgroup，
也不能验证 bwrap namespace、目标进程归属或最小权限。`DATABASE_URL`、`REDIS_URL` 未配置；
没有连接 PostgreSQL/Redis，也没有启动 Supervisor、Celery 或 Worker。

## 验收矩阵

| 项目 | 状态 | 证据 |
|---|---|---|
| 持久 Scope 唯一约束冲突后复用同一绑定 | `PASS_ISOLATED` | FakeSession 回归；未对真实 PG 并发 |
| Scope 先持久化、cgroup 准备失败持久标记 unknown | `PASS_ISOLATED` | FakeSession/临时目录回归；未对真实 cgroup 演练 |
| `prepared` 启动 claim 行锁内单次转移 | `PASS_ISOLATED` | 状态转换与 exec 重入回归；未运行多 Supervisor |
| 重启恢复扫描 running Scope 并在 ready 前请求清理 | `PASS_ISOLATED` | FakeSession/临时文件回归；不是内核进程清理证据 |
| 同 execution_id 并发启动 20 次最多一个进程 | `BLOCKED` | 无授权 PG、cgroup 写权限和 OS runner |
| 启动成功但 ACK 丢失后重试不重复启动 | `PASS_ISOLATED` | 持久 `running`/`starting` 的 exec 重入回归；未注入真实 ACK 丢失 |
| PID + start-time + boot ID 与 scope 准确关联 | `BLOCKED` | 真实进程启动不可执行；仅有解析/绑定隔离测试 |
| PID、mount、network、user namespace | `BLOCKED` | 内核拒绝非特权 namespace 创建 |
| 新进程原子加入 cgroup v2 | `BLOCKED` | cgroup 根只读；helper 仅编译 |
| Worker SIGKILL 后独立回收 | `BLOCKED` | 无真实 Worker、Scope cgroup 和常驻 Supervisor |
| Supervisor 重启后恢复并处置未决 Scope | `BLOCKED` | 无授权 PG/cgroup；未运行恢复过程 |
| `kill_and_wait_empty()` 的真实停止语义 | `BLOCKED` | 无 cgroup 写权限；未向真实进程发出 cgroup.kill |
| `unknown` 不会重新启动 | `PASS_ISOLATED` | 状态 claim 对 unknown 拒绝的单测 |
| 可信停止回执 | `BLOCKED` | 本 backend 无可信内核观察/签名证据，本轮未生成回执 |
| 真实 HTTP 下载 | `NOT_TESTED` | 本阶段明确禁止进入 HTTP 下载阶段 |

没有项目获得 `PASS_RUNTIME`。真实停止记录不存在；不得以测试 double、cgroup 文件模拟或
进程 PID 消失代替内核停止证据。

## 验证与原始命令结果

- 环境：Python `3.11.14`；Linux `6.8.0-147-generic`；bubblewrap `0.9.0`。
- C helper 编译：`cc -Wall -Wextra -Werror -O2 deploy/download-supervisor/scope_exec.c -o /tmp/cygnusx-scope-exec`：PASS（只编译，未执行）。
- Ruff（backend 与 scope 测试）：PASS。
- mypy（`linux_scope_backend.py`）：PASS。
- Scope/Supervisor/Authority/P0-A migration 定向测试：`80 passed, 1 skipped`；唯一 skip
  是需要 host-root ownership 的正向系统二进制测试，当前 user namespace 将 host root
  映射为 UID 65534，未计作通过。
- `scripts/check_migrations.py`：迁移内部依赖检查通过，迁移图连通且单 head；没有对
  PostgreSQL 应用迁移。
- `git diff --check`：本轮代码与验收报告通过。

`uv` 使用 `UV_CACHE_DIR=/tmp/omichub-uv-cache`，因为默认缓存目录所在挂载只读。无网络
namespace、cgroup 或数据库运行日志可交付；上面的拒绝输出就是本机实际探针原文。

## 未完成能力与安全边界

当前环境不具备本阶段真实验收所需权限，因此授权 OS 验收为 `BLOCKED`，不把缺权限降格成
通过。下一次真实验收需要运维明确提供的隔离 Linux runner、专用 PostgreSQL、已委派的
scope cgroup 控制器、Supervisor 独立身份和清理责任人；在该环境依次执行 20 路并发、
ACK 丢失、Supervisor 重启、Worker SIGKILL 和 cgroup.kill 退出检查，并保存 Task/scope/
execution/epoch、PID 身份及 `cgroup.events` 原始结果。

此报告不认证受控网络出口、RX 硬预算、block/inode quota、签名 quiescence 回执或
FileRegistry 真实对账。所有下载与写门禁保持关闭。本轮不进入真实 HTTP 下载阶段。
