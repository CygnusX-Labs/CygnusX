# G3 可信下载执行安全验收 — BLOCKED 判定依据

判定时间: 2026-10-17T08:30Z · 判定人: iat 验收操作者 (zj)

## 结论

**G3 = BLOCKED**（不运行真实下载，不把普通 Docker 网络/cgroup 可见性当作认证）

## 逐项前置条件核查（runbook §10.1）

| 前置条件 | 实际状态 | 结果 |
|---|---|---|
| 实际实现并审查的 `TrustedExecutionAdapter`（非 Protocol-only）+ 独立 OS Supervisor | `src/cygnusx/infrastructure/download/trusted_execution.py` 文件头明确声明 "S3-E1 interface only. No runtime implementation or admission authority."；`TrustedExecutionAdapter` 是 `typing.Protocol`，只有类型签名，无任何可执行实现 | 缺失 |
| 每 Task scope 下载 CLI 启动前建立；cgroup/namespace 或等价经审计边界；非 root、无 NET_ADMIN/NET_RAW、无 Docker socket、无 DB/Broker/云凭据 | 全仓库 grep `TrustedExecutionAdapter|ExecutionBoundaryRequest|trusted_http_driver` 仅命中 Protocol 定义、单元契约测试（test_download_trusted_execution_contract.py）与默认 skip 的集成 harness，无 supervisor/cgroup/netns 实现 | 缺失 |
| 唯一受控网络出口（IPv4/IPv6/DNS/重定向逐跳约束；代理故障禁止直接回退） | `policy.py` 的 `verify_resolved_addresses`/`verify_redirect` 仅为源码级验证函数，注释明确 "this does NOT pin a CLI connection or enable execution"；无出口执行设施 | 缺失 |
| 同步强制网络 RX 硬额度（原子计量层覆盖响应头/失败包/并发/Range/重试） | `ExecutionBoundaryObservation.rx_admitted_bytes` 仅为 Protocol 字段定义，无计量层 | 缺失 |
| 真实块/inode 硬配额 + Supervisor 故障停机/租约过期/子进程清空/出口撤销证明 | 无实现 | 缺失 |
| 自有 HTTP 测试源 + 明确额度；开始前证明禁止未授权直连 | 未搭建 | 缺失 |
| 受审查的真实 `trusted_http_driver` pytest 插件覆盖 `tests/integration/test_download_trusted_http_boundary.py` | 该文件的 `trusted_http_driver` fixture 硬编码 `pytest.skip("NOT_TESTED: authorized OS supervisor and real HTTP driver unavailable")`；本次运行确认 9 个场景全部 SKIPPED（exit 0，见 04-isolated-regression/p1-g3-boundary.log） | 缺失 |

## 支撑证据

- `src/cygnusx/infrastructure/download/policy.py:18` — `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED: Final = False`；`require_download_runtime()` 对 sra/direct_link/cloud_storage 全部抛 `DOWNLOAD_TRANSPORT_UNVERIFIED`（运行时复核见 03-env-runtime/env-07-frozen-gate.log）
- AG-16 复核：12 类 Download Capabilities 全部 `execution_allowed=false`（含 geo_metadata/ncbi_sra/ena_fastq/geo_supplementary/http_direct_link/https_direct_link/ftp/oss/tos/obs/cloud_drive/existing_dataset_assets），Cloud Drive 未冒充实现
- `tests/integration/test_download_trusted_http_boundary.py:38-39` — skip 硬编码，注释明确 default is explicitly NOT_TESTED

## 责任方与下轮建议

- 阻断责任：G3 需要先实施受信 OS Supervisor + TrustedExecutionAdapter 真实实现、独立受控出口、原子 RX 计量、块/inode 硬配额，并完成单独安全审查与授权（runbook §12.3 "后续独立安全工作"）
- 在上述设施落地前，任何对 G3-01..09 的执行尝试都应保持 BLOCKED；不得使用带 Docker socket 的普通 Worker 模拟（runbook 原则 4）
