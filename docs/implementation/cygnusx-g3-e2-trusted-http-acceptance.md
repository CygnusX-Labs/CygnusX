# G3-E2 Trusted HTTP acceptance

本轮结论：PARTIAL_CODE / PASS_ISOLATED / RUNTIME_BLOCKED。真实 HTTP 场景 0/9；没有运行认证。DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED、WRITE_RUNTIME_ACCEPTED 及 Agent 写开关未改动，S6/S7 仍 NO-GO。

## 基线与范围

基线见 evidence/g3-e2-runtime/baseline.json：主仓 HEAD e78fd1efa1df3ebfcb098be973e81e193b1db224，递归子仓 HEAD/dirty、主仓 dirty/diff SHA、核心代码和锁文件 SHA、内核、UID 已固化。当前共享树有其他会话变化，不能将旧审计 HEAD 当本轮 HEAD。工具/镜像 digest UNKNOWN；没有读取凭据或联系生产。先读架构 README、download as-built、03 实施/提示和最新审计 G3 章节。

## 源码与事实

新增 src/cygnusx/infrastructure/download/supervisor_server.py，未修改现有客户端、DTO、Worker、Task、FileRegistry 或 P0-A 数据库文件。

- 独立 HTTP/1 TLS listener 要求 CERT_REQUIRED 和 TLS >=1.2；caller 从 TLS peer certificate SHA-256 固定映射派生，不能由 HTTP header/JSON 指定。固定路由、请求头/体界限、超时、不接受 chunking/压缩，连接完成后关闭。真实握手未运行。
- SupervisorService 默认 authority/backend 均空，拒绝启动；启动服务前必须成功 default-deny recovery。start 先受信 authority 重查/claim，再 prepare 全隔离边界，最后 exec_once。Task+epoch 派生固定 scope；跨进程持久唯一性由真实后端负责，此轮未证明。
- VerifiedAdmission 含原 Task/owner/admission/budget/attempt/execution/epoch/protocol、project、source/destination/policy/tool digest、environment/caller、expiry/lease、RX/disk blocks/inode 上限。它仅是可信适配接口，不能凭构造该对象取得运行认证；当前没有 P0-A 实例适配。
- 启动失败和取消同样进入先 revoke_egress、再 kill_and_wait_empty、最后 observe/quiescence 流程；停止不释放业务预算。lease 每次重查 authority；撤销/过期/异常保守停止。watchdog_once 与独立循环不依赖 Worker finally；常驻 daemon、故障隔离和重启清理尚未部署/运行。
- EnforcedScopeBackend 仍为 Protocol，**没有**实际 cgroup/netns/mount/quota/RX 数据面。没有 shell/CLI 启动实现，没有真实下载驱动或部署配置。没有用内存后端代替内核强制。

现有 lease DTO 无 nonce/epoch 参数，接口虽通过持久 scope resolve 间接绑定旧 epoch，但并未闭合 renew nonce 防重放契约；在改 DTO/client 前需与主工作包协调。实际服务端日志/审计落盘、证据单调序号、签名 key 管理、固定 CLI digest 校验和 durable scope journal 都仍待真实后端实施。

## 验证与证据

原始日志及退出码：evidence/g3-e2-runtime/isolated-tests.txt/.exit、mypy.txt/.exit、ruff.txt/.exit。命令均 UV_CACHE_DIR=/tmp/cygnusx-g3-uv-cache uv run --offline --no-sync。第一次默认 uv cache 因只读缓存失败，改用 /tmp；未安装依赖/改锁文件。

pytest tests/unit/test_download_supervisor_server.py tests/unit/test_download_supervisor_client.py tests/unit/test_download_trusted_execution_contract.py -q：54 passed（其中新增 11 项），仅隔离控制契约，不能与别的套件相加。涵盖默认拒绝、恢复先于启动、固定 scope、错误 caller/Task/lease/预算零启动、失败启动停止顺序、撤销 lease、未知停止拒绝证据、Worker 独立 watchdog 调用及路由契约。其 authority/backend 是 AsyncMock，明确不充当真实 HTTP driver。聚焦 mypy 1 源文件通过；聚焦 Ruff 通过。

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
| EG08 | 原 Task/Admission/CLI/Registry/SHA | BLOCKED，待 P0-A 可信适配与原 Worker 接线 |
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

下一步需主工作包稳定 P0-A 服务端 revalidation/claim 接口；经独立非生产授权后实现真实 Linux 后端和持久 scope fencing，补 lease nonce、签名/单调序号、可信审计与 watchdog 常驻部署；最后复用原九项真实 driver 与 Registry/SHA 链。任何一个真实设施缺失都不得启动 CLI，更不解除 HTTP/其他协议、人类下载或 Agent 写门禁。
