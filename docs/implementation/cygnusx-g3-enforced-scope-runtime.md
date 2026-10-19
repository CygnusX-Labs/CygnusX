# G3 Enforced Scope Runtime

## 状态

本轮实现了 `LinuxEnforcedScopeBackend` 的持久 scope 和进程生命周期编排，
但 G3 仍为 **NO-GO / BLOCKED**。运行门禁保持：

```text
DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False
WRITE_RUNTIME_ACCEPTED=False
```

当前环境没有可授权的 PostgreSQL、cgroup v2 写权限、网络策略服务或独立
Supervisor 主机，因此没有启动实际下载，也没有把隔离单元测试计为运行通过。

## 调用链

现有链路仍为 `Task -> Admission/Budget -> DatabaseAdmissionAuthority ->
SupervisorService -> EnforcedScopeBackend`。新增 backend 位于
`src/cygnusx/infrastructure/download/linux_scope_backend.py`，不创建新的 Task、
队列或下载系统。scope 事实落在 `download_execution_scopes`，由
`dwnscope05_add_supervisor_scopes.py` 创建。

`prepare` 使用服务端已验证的 Task/attempt/epoch/execution_id 创建唯一 scope；
`start_state` 读取持久状态和 PID，`starting`、`unknown`、已停止状态全部返回
`unknown`，因此 Supervisor 不会在状态不确定时再次启动。`exec_once` 只接受
部署时注入的可信 command factory，不接受 Worker argv、URL、环境或路径。

## OS 边界

子进程通过 `bwrap --clearenv --die-with-parent --new-session --unshare-pid
--unshare-net` 启动，工作目录是 scope 私有目录，`/usr`、`/bin` 只读绑定，
并挂载独立 `/proc`、`/dev`。默认无网络出口，因而不会错误地宣称受控 HTTP
出口已经完成。启动前必须发现 bwrap、可写 cgroup v2 和 command factory，
否则 fail-closed。生产接线仍需运维提供真实网络代理/白名单、磁盘块/inode
配额和 Supervisor 签名密钥。

`revoke_egress -> kill_and_wait_empty -> observe` 的停止顺序由既有
`SupervisorService` 执行。scope 在进程死亡或清理失败时保留 `unknown`/
`RECONCILIATION_REQUIRED` 所需的持久事实，watchdog 通过 `expired_scopes`
独立回收，不依赖 Worker 的 finally。

## 验证结果

- `scripts/check_migrations.py`: 通过，迁移链单 head。
- P0-A/Supervisor/trusted execution 隔离测试：通过；新增
  `tests/unit/test_linux_scope_backend.py` 的 4 个 fail-closed 检查，覆盖
  cgroup 不可用、恢复前无副作用、可信 command factory 缺失和 Supervisor
  签名密钥缺失。
- `tests/integration/test_download_trusted_http_boundary.py`: 九项仍为
  `NOT_TESTED`/skipped；没有真实 HTTP、PG、Redis、Celery、OS quota 或
  FileRegistry 对账证据。
- 当前容器 `CapEff=0`、`NoNewPrivs=1`，cgroup 根不可写；不能进行 Phase B/F
  的真实强制设施验收。

## 未实现与回滚

受控 HTTP 的 DNS/IPv4/IPv6/redirect 白名单、连接级 RX 计量、Range 重试预算、
磁盘块/inode 硬配额、可信签名停止回执仍未实现；本 backend 不会用文件大小
或 AsyncMock 替代这些事实。部署回滚是移除 Supervisor backend 接线并保持门禁
关闭，保留 scope 记录用于对账；不得删除 scope 或直接恢复普通 Worker 下载。

## 结论

源码层面的持久 scope、启动幂等状态机、默认拒绝的 Linux 进程边界和独立
watchdog 接口已落地。真实 OS 隔离、受控 HTTP、九项运行测试仍 **BLOCKED**，
因此 G3 不放行。
