# G3-E2 Trusted HTTP acceptance

本轮结论：PARTIAL_CODE / PASS_ISOLATED / RUNTIME_BLOCKED。真实 HTTP 场景 0/9；没有运行认证。DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED、WRITE_RUNTIME_ACCEPTED 及 Agent 写开关未改动，S6/S7 仍 NO-GO。

## 基线与范围

历史基线见 `evidence/g3-e2-runtime/baseline.json`；当前工作树基线见 `evidence/p0a-g3-runtime-identity/current-baseline/`。历史主仓 HEAD、递归子仓和 dirty 状态不能替代当前 checkout 的运行指纹；工具/镜像 digest UNKNOWN，未读取凭据或联系生产。真实验收前必须重新冻结本次源码与镜像。

## 源码与事实

新增 src/cygnusx/infrastructure/download/supervisor_server.py、`supervisor_authority.py` 与 `execution_request.py`；Admission 仓储增加 consumed epoch 重验与 Task 状态检查。HTTP 直链 Worker 现在通过该持久绑定构造器调用 Supervisor client 的 `start/observe/renew/evidence`，签名上下文继续交给既有 FileRegistry 校验；缺失绑定、mTLS 配置、未知/失败回执均 fail closed，绝不回退本地 aria2c。Supervisor 实际后端、运行配置和真实服务仍未部署。

- 独立 HTTP/1 TLS listener 要求 CERT_REQUIRED 和 TLS >=1.2；caller 从 TLS peer certificate SHA-256 固定映射派生，不能由 HTTP header/JSON 指定。固定路由、请求头/体界限、超时、不接受 chunking/压缩，连接完成后关闭。真实握手未运行。
- SupervisorService 默认 authority/backend 均空，拒绝启动；启动服务前必须成功 default-deny recovery。start 先受信 authority 重查/claim，再 prepare 全隔离边界，最后 exec_once。Task+epoch 派生固定 scope；Worker 请求的 execution ID 现由 Task/attempt/初始 epoch 确定性派生，重试可稳定对账同一 scope；跨进程持久唯一性仍由真实后端负责，此轮未证明。
- `DatabaseAdmissionAuthority` 从 Task 持久 `_download_execution_binding` 解析精确 admission/budget 引用，校验 mTLS caller 与固定 profile，重读 Task/Approval/Admission/Budget，并在同一 SQL 事务 claim 单次 epoch；renew revalidates exact consumed epoch。它产出包含 Task/owner/admission/budget/attempt/execution/epoch/protocol、project、source/destination/policy/tool digest、environment/caller、expiry/lease、RX/disk blocks/inode 上限的 `VerifiedAdmission`。这只是可注入的 SQL authority；Supervisor 服务没有默认装配它，PG 并发和 Worker→Supervisor 的真实生命周期未验。
- 启动失败和取消同样进入先 revoke_egress、再 kill_and_wait_empty、最后 observe/quiescence 流程；停止不释放业务预算。lease 每次重查 authority；撤销/过期/异常保守停止。watchdog_once 与独立循环不依赖 Worker finally；常驻 daemon、故障隔离和重启清理尚未部署/运行。
- EnforcedScopeBackend 仍为 Protocol，**没有**实际 cgroup/netns/mount/quota/RX 数据面。没有 shell/CLI 启动实现，没有真实下载驱动或部署配置。没有用内存后端代替内核强制。

lease 更新契约现显式要求 `execution_epoch` 与一次性 `lease_nonce`：client 只使用本次 `start` 返回的 epoch，server 将 nonce 按 `(supervisor_id, nonce)` 持久消费，并在同一 authority 事务重验 Task/Admission/epoch；重复 nonce、未知 epoch 或缺少 start 绑定均拒绝。新增 `dwnlease03` 向前迁移和 SQLite 隔离回归验证该防重放边界。随后 `dwnexec04` 将确定性 `execution_id` 写入 Admission，使相同 start 重试能复用原 claim，改变执行身份则拒绝；迁移遇已有 consumed/settled 历史记录会显式停止，不伪造身份。该持久表尚未应用真实 PG，且实际服务端日志/审计落盘、证据单调序号、签名 key 管理、固定 CLI digest 校验和 durable scope journal 都仍待真实后端实施。

后续隔离检查修正了停止观测的身份绑定：`_stop_scope` 现在要求观测的 Task、scope、execution 和 epoch 与启动/停止请求完全一致，再检查 quiescence；watchdog 后端契约返回过期 scope 对应的持久 `ExecutionBoundaryRequest`，不再仅凭 scope UUID 清理。新增四个隔离用例覆盖 stop 观测身份错配，服务端与 authority 聚焦测试共 18 项通过，Ruff/mypy 通过。AsyncMock 后端仍不证明任何 OS 停止事实；真实设施与九场景状态未变。

启动重试幂等随后被显式写入 `EnforcedScopeBackend` 契约：Supervisor 在 `prepare` 后必须读取持久三态 `start_state(scope, admission)`；只有明确 `not_started` 才允许调用 `exec_once`，`started` 复用原 scope，`unknown` 或非法值直接拒绝并进入停止/对账路径。相同 Task/attempt/epoch 的重试不能再次启动 CLI。Worker 同样只续租明确 `running` 状态；`unknown` 或未来未识别状态立即以 `DOWNLOAD_SCOPE_RECONCILIATION_REQUIRED` 停止并对账。新增回归覆盖两侧 fail-closed 状态，当前 P0-A/G3 定向集合为 77 项通过。该检查约束真实 backend/Worker 的实现责任，仍不证明任何 Linux scope 或进程树事实。

继续检查 watchdog 生命周期时发现，单个过期 scope 的 observe/stop 异常会打断同一轮剩余清理，并使常驻 watchdog 循环退出。现对每个 scope 独立记录失败并继续清理后续项；若枚举/整轮仍失败，watchdog 捕获后等待下一周期重试。新增离线回归证明第一项失败后第二项仍 revoke/kill/observe；Supervisor 服务测试 16 项通过，Ruff/mypy 通过。该行为不证明后端能强制停止，也未启动常驻进程。

stop 编排还调整为：egress revoke 抛错时仍按顺序尝试 kill-and-wait，任一 containment 调用失败均以 `SUPERVISOR_STOP_INCOMPLETE` 拒绝完成状态，不继续 observe/签发 quiescence。新增回归验证 revoke 失败后 kill 仍被调用且 stop 返回拒绝；Supervisor 服务测试现 17 项通过。真实 egress 与进程树效果仍未知，watchdog 会保留失败并在后续轮次重试。

HTTP listener 的五秒 timeout 现只覆盖请求头/请求体读取，不覆盖 Supervisor dispatch；避免慢的 stop/kill-and-wait 因 HTTP parser deadline 被取消。handler 回归使用 1ms read deadline 和较慢的隔离 dispatch，确认操作完成并返回结果；Supervisor 服务测试现 18 项通过，Ruff/mypy 通过。该改动不设 OS 操作时限，真实后端仍需自行提供安全 deadline 与失败回收。

## 验证与证据

原始日志及退出码：evidence/g3-e2-runtime/isolated-tests.txt/.exit、mypy.txt/.exit、ruff.txt/.exit。命令均 UV_CACHE_DIR=/tmp/cygnusx-g3-uv-cache uv run --offline --no-sync。第一次默认 uv cache 因只读缓存失败，改用 /tmp；未安装依赖/改锁文件。

pytest tests/unit/test_download_supervisor_server.py tests/unit/test_download_supervisor_client.py tests/unit/test_download_trusted_execution_contract.py -q：54 passed（其中新增 11 项），仅隔离控制契约，不能与别的套件相加。涵盖默认拒绝、恢复先于启动、固定 scope、错误 caller/Task/lease/预算零启动、失败启动停止顺序、撤销 lease、未知停止拒绝证据、Worker 独立 watchdog 调用及路由契约。其 authority/backend 是 AsyncMock，明确不充当真实 HTTP driver。聚焦 mypy 1 源文件通过；聚焦 Ruff 通过。

当前增量另运行 `.venv/bin/python -m pytest tests/unit/test_download_supervisor_authority.py tests/unit/test_download_execution_admission.py tests/unit/test_download_supervisor_server.py -q -m unit`：通过。覆盖 SQL authority 的一次 claim、精确 Task 引用、错误 epoch、重复 claim、已消费 epoch 重验及 lease nonce 回放拒绝；使用 SQLite 离线 fixture，不证明 PG 原子并发或任何 OS 事实。`supervisor_authority.py` 与 Admission 仓储聚焦 mypy、Ruff 通过；迁移链静态检查通过，未应用迁移到真实数据库。

全仓提交门禁未运行；本轮不提交。原九场景 fixture 仍明确 skip，未再次用 skip 的零退出码创造 PASS。

## 设施 EG01–09

| ID | 设施 | 当前结论 |
|---|---|---|
| EG01 | 独立 Supervisor / mTLS | CODE_PARTIAL，listener 实现，真实 TLS/审计未验 |
| EG02 | 启动前 cgroup/net/mount/user | INTERFACE_ONLY，prepare 顺序隔离验证 |
| EG03 | 唯一出口/IPv4 IPv6/DNS/逐跳 | NOT_IMPLEMENTED，真实强制 BLOCKED |
| EG04 | 跨连接同步硬 RX | NOT_IMPLEMENTED，只有后端契约 |
| EG05 | 全可写域 blocks/inodes quota | NOT_IMPLEMENTED，只有后端契约 |
| EG06 | 先断出口/停止整 scope/可信回执 | CODE_PARTIAL，编排隔离验证；真实停止未知 |
| EG07 | Worker 死亡与 Supervisor 重启 lease | CODE_PARTIAL，watchdog/recovery 编排；持久后端/常驻运行缺失 |
| EG08 | 原 Task/Admission/CLI/Registry/SHA | PARTIAL_CODE：离线 SQL authority、Supervisor/Worker seam 可用；待默认运行装配及 Registry/SHA 真实链 |
| EG09 | 真实九项认证 | BLOCKED，0/9 |

## 真实场景单独列账

| 原场景 | 本轮状态 |
|---|---|
| small_file | BLOCKED / NOT_RUN |
| unauthorized_address | BLOCKED / NOT_RUN |
| unauthorized_redirect | BLOCKED / NOT_RUN |
| unknown_length | BLOCKED / NOT_RUN |
| network_over_budget | BLOCKED / NOT_RUN |
| disk_quota_exhausted | BLOCKED / NOT_RUN |
| cancel | BLOCKED / NOT_RUN |
| worker_sigkill | BLOCKED / NOT_RUN |
| partial_reconciliation | BLOCKED / NOT_RUN |

这九项与 EG 设施编号不同，亦不把隔离测试计为真实场景。没有受授权环境 ID、专用 PG/Redis/Worker、cgroup/netns/mount/quota 权限、自有 allow/deny/redirect 端点、CPU/Mem/RX/blocks/inodes/时长限额和清理负责人。本轮没有请求 root/sudo/docker.sock、没有创建 OS scope/挂载/网络策略/下载，没有故障注入。

网络计量目标仍为穿过可信出口进入 Task 的所有 RX（响应头/错误/重试/Range/并发），放行前共享原子扣减；上游观察及 dropped 单列。当前无数据面实现，无法证明零超界。磁盘目标是所有 writable paths 的 allocated blocks 与 inode 双硬限，非文件长度。

## 回滚与下一步边界

没有新增运行资源，故无需停服务/清理挂载。源代码回滚仅审查并移除本轮新增 supervisor_server.py 与 test_download_supervisor_server.py，保留报告和证据；禁止整仓 reset/clean，禁止动其他会话的 dirty。若以后运行服务，先断出口、停止所有 scope 并取可信空 scope 证据，再保留原 Task/FileRecord/预算及部分文件供对账，不自动退款或删用户文件。

下一步需将数据库 authority 与受信部署配置装配到独立 Supervisor，并由原 Worker 从持久 Task 引用构造边界请求；经独立非生产授权后实现真实 Linux 后端和持久 scope fencing，补签名/单调序号、可信审计与 watchdog 常驻部署；最后复用原九项真实 driver 与 Registry/SHA 链。任何一个真实设施缺失都不得启动 CLI，更不解除 HTTP/其他协议、人类下载或 Agent 写门禁。

后续离线增量复核：加入 `tests/unit/test_download_registration_contract.py`、`test_download_worker_supervisor.py`、listener 缺少 trusted backend/非 mTLS 的拒绝测试、lease nonce 数据库约束及 `execution_id` 幂等/缺失身份回归后，原联合 Supervisor/P0-A/Worker 套件为 127 项，最新 P0-A/G3 定向集合为 77 项通过；覆盖 lease nonce 的单次消费/回放拒绝、持久表拒绝空 supervisor/非正 epoch、Worker 请求构造器绑定拒绝、相同 start 重试复用 Admission claim、started/unknown/非法 scope 状态、Worker 未知状态不续租、不同或缺失 execution identity 拒绝、Supervisor `start/observe/renew/evidence` 顺序、listener 未装配或 TLS 不合规时不绑定，以及 HTTP 直链缺少受信 Supervisor 时不回退 aria2c。带 Admission 绑定时，FileRegistry 路径现调用回执结算入口；`scripts/check_migrations.py`、相关源码 mypy 与 Ruff、`git diff --check` 通过。该结果仍是 SQLite/AsyncMock 隔离证据，未应用 `dwnlease03`/`dwnexec04` 到真实 PG，真实 OS、Worker 生命周期、HTTP 九场景和运行镜像仍 BLOCKED。
