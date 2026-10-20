# 可观测性

CygnusX 的可观测性由四个面组成：**事件流**（用户可见的过程）、**审计事实**（谁做了什么）、**运行日志**（排障细节）和**运行证据**（一次验收为何通过）。它们服务不同问题，不能互相替代。

> **当前状态**：事件、审计、日志与 trace 均已接入；运行证据按 Run ID/提交/镜像/环境归档，不纳入普通业务日志。历史证据不自动适用于当前源码。

## 四个面

| 面 | 数据 | 回答的问题 | 保留 |
| --- | --- | --- | --- |
| 事件 | SSE / `chat_message_events` | 用户看到了什么、任务到哪一步 | DB 持久化，可重放/续传 |
| 审计 | `audit_logs` + JSON 日志备份 | 谁在何时对什么执行了写操作 | 审计保留策略 |
| 日志 | 五域日志文件 + `tasks.logs` 摘要 | 为什么失败、堆栈与上下文 | 轮转/保留 |
| 运行证据 | `evidence/`、验收报告 | 某次运行在何环境、何版本通过 | 按验收流程归档 |

## 事件流

统一事件包含生命周期事件和工具事件链：

```text
request_started → agent_started → token/delta …
  → agent_tool_call → agent_tool_started → agent_tool_result
  → approval_required → …
  → agent_finished / error / done
```

- 工具事件由 `tool_call_id` 贯穿，前端按 ID 归并调用过程。
- `llm_payload` 给模型，`ui_payload` 给前端；事件展示以后者为准。
- Chat 事件持久化到 `chat_message_events`，支持会话恢复、断点续传和取消；信封含 `payload_hash`，产物含 SHA-256 对账。
- 事件是用户可见事实，不等于执行成功证明；最终状态仍以业务表为准。

## 审计

- HTTP 写操作由 `AuditMiddleware` 记录到 `audit_logs`。
- Studio、Chat、AgentTeams、科研交付等关键路径有显式审计调用。
- DB 写入成功后以 `service="audit"` 写结构化应用日志作为文本备份。
- 审计只记录必要元数据；不写 Token、确认 secret、完整私有对话。

查询示例：

```bash
jq 'select(.record.extra.service == "audit")' ${CYGNUSX_LOG_DIR}/cygnusx.json.log
```

## 日志与 trace

- 日志域、目录、轮转与排障见[日志架构](logging)。
- `core/logging.py` 向每条日志注入 `trace_id`、`span_id`、`request_id`、`session_id`（OpenTelemetry 上下文可用时）。
- DB 连接池、路由决策、记忆结算等有独立指标；指标缺失时不能推断“没有发生”。
- 任务实时进度走 Redis Pub/Sub → WebSocket；数据库只保留截断后的摘要日志。

## 运行证据与成熟度

平台用以下口径区分证据等级：

```text
implemented ≠ isolated-tested ≠ runtime-verified ≠ end-to-end-verified ≠ production-approved
```

运行证据必须绑定：

- Run ID / 验收记录；
- 源码提交或工作树状态；
- 镜像 tag/摘要；
- 环境（隔离 Docker/PG/浏览器、数据集、配置）；
- 通过项与未通过项。

已知证据：

- RI09.5 历史隔离运行：项目汇总 HTML/PDF、V2 ZIP、完整性校验、JWT 下载；
- RC04 审计（2026-10-18）：Core **PARTIAL / NOT ACCEPTED**，浏览器断言 31/34，缺当前源码冻结与 FI01–FI06 新验收；
- 科研交付/寻宝鼠：隔离测试与浏览器预览部分通过，真实科研记录/ZIP 因 corpus 门禁 BLOCKED。

不要把“有一条历史 PASS”写成“当前已支持”，也不要把“隔离测试通过”写成“生产可用”。

## 排障顺序

1. 看任务/会话的最终状态与错误码；
2. 看 SSE 事件或 `chat_message_events` 的过程；
3. 看 `tasks.logs` 摘要与 Worker 日志；
4. 看对应域文件日志与 trace_id；
5. 查 `audit_logs` 确认是否有权限/门禁拒绝；
6. 若涉及验收，查证据报告而非应用日志。

## 关联文档

- [日志架构](logging) · [安全模型](security-model) · [科研能力与证据边界](../research/evidence-boundaries)
- [问题排查](../operations/troubleshooting) · [流程监控面板](../features/workflow-monitor)
- 权威基线：[`CygnusX_agent_execution_framework.md`](../../ARCHITECTURE_DESIGN/CygnusX_agent_execution_framework.md)、[`CygnusX_log_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_log_architecture.md)
