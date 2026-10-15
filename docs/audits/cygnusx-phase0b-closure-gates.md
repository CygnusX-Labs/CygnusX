# Phase 0B Closure G-01～G-13 验收矩阵

状态含义：PASS 已执行且通过；FAIL 已执行但不满足；BLOCKED 环境或外部证据缺失；
NOT TESTED 本轮未执行。层级：Unit / Contract / Integration / Runtime Smoke / E2E。

| Gate | 验收项 | 证据 | 层级 | 状态 |
|---|---|---|---|---|
| G-01 | Git、子模块、dirty state 封存 | Manifest repositories；HEAD `c68ea9e0` | Contract | PASS |
| G-02 | Treasure build SHA/tag/digest/container 一致 | Compose context `88dae95e` vs default tag `1ea2f79`；Docker socket拒绝 | Runtime Smoke | FAIL |
| G-03 | Treasure chat/web 命令、健康检查、路由闭合 | Dockerfile、Compose、nginx 静态检查 | Contract | PASS |
| G-04 | Worker EBIDownload/Polariseq 真实版本与 digest | 宿主机 EBIDownload 1.4.0；Worker 不可 inspect | Runtime Smoke | BLOCKED |
| G-05 | RNAFlow/ATACFlow 来源、Snakefile、挂载一致 | `/home/zj/pipeline` HEAD/摘要；容器不可 inspect | Contract/Runtime Smoke | BLOCKED |
| G-06 | Redis 双进程 CAS、TTL、重放、故障恢复 | `test_phase0b_redis.py`；本机无 redis-server/socket | Integration | BLOCKED |
| G-07 | MCP STDIO/HTTP/SSE initialize、auth、tool call | 进程内 Client 4 PASS；真实 STDIO/HTTP/SSE 4 SKIPPED（socket/transport 受限） | Runtime Smoke | BLOCKED |
| G-08 | 双用户 owner、人工确认、参数绑定、无副作用拒绝 | `test_phase0b_http.py` + service tests，DB/Redis 为 doubles | Integration | BLOCKED |
| G-09 | RNA/ATAC 最终验证、任务幂等、状态查询 | `test_phase0b_services.py`，repo/queue doubles | Integration | PASS |
| G-10 | Download owner/path/file registration | download service/task tests，DB doubles | Integration | PASS |
| G-11 | 审计关联 request/tool/task/error 字段 | 代码字段盘点；未运行真实落库链 | Contract | BLOCKED |
| G-12 | Docker Compose、Worker、依赖健康与权限 | synthetic `docker compose config`；daemon 不可用 | Runtime Smoke | BLOCKED |
| G-13 | Manifest、Runbook、回滚与准入结论可复核 | 本矩阵、Manifest、Runbook、Closure 报告 | Contract | PASS |

Closure 结论：**BLOCKED**。G-02/G-04/G-05/G-06/G-07/G-08/G-11/G-12 未完成前，禁止
开放有副作用的寻宝鼠 Agent 工具。G-03/G-09/G-10/G-13 的 PASS 仅表示静态或隔离层级
证据，不表示生产运行通过。
