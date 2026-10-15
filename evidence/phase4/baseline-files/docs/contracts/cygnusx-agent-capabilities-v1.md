# Shared Agent Capabilities v1

代码权威：`src/cygnusx/application/schemas/agent_tools.py`。
生成 schema：`cygnusx-agent-capabilities-v1.schema.json`；执行
`.venv/bin/python scripts/export_agent_tool_contracts.py` 更新，禁止手工维护 Node 副本。
schema_version 为 `1.0`，input extra forbid。identity/scopes 均来自 backend context。

| Capability | Input | 真实业务层 | Side effect / Scope |
|---|---|---|---|
| downloads.describe_capabilities | 空 | 下载运行证据 Adapter | none / read:discovery |
| downloads.prepare | accession, ftp/aws | DownloadRequest + 现有路径规范 | confirmation / prepare:download |
| analysis.list_workflows | 空 | AnalysisFlowToolService.discover | none / read:workflows |
| analysis.get_workflow_schema | flow_id | AnalysisFlowToolService.describe + 原 Compiler | none / read:workflows |
| analysis.prepare | flow_id, arguments | AnalysisFlowToolService.prepare + 原 Validator | confirmation / prepare:analysis |
| tasks.get_status | task_id UUID | TaskService.get_task + 真实 Invocation link | none / read:tasks |
| tasks.list_related | 空 | Invocation owner/session/project query | none / read:tasks |
| downloads.submit | proposal_id UUID | 受控适配器 → 原 DownloadService | task / execute:download，恒关 |
| analysis.submit | proposal_id UUID | 受控适配器 → 原 TaskService | task / execute:analysis，恒关 |
| tasks.cancel | proposal_id UUID | 未实现 | task / execute:cancel，恒关 |

Node/Python names 为 `bioops_` + capability 点替换下划线。写工具不进入发现列表，直接调用
返回 WRITE_GATE_BLOCKED。原生只读 discovery engine 保留，未重命名或复制。

REST：`/api/v1/agent-tools/sessions/{session}/capabilities|invoke|related`；invoke 接收
`{capability_id, arguments}`，返回 `{schema_version, invocation_id, result}`。
每个 Schema 描述 version/scope/side_effect/input/result/errors/approval/idempotency/agents。
Flow describe 返回实际版本和原 Compiler input_schema；prepare arguments 由原 Validator
二次校验。未注册工具、非法 Schema 不进入 TaskService。

Proposal 返回 operation、project、conversation、parameters_hash、完整 normalized_parameters、
preview、confirmation_id、expires_at、state、write_enabled=false、gate。审批端点只接收
proposal_id，不接收可变参数。完整绑定 payload 的 digest 包括 server owner、project、
conversation、operation、proposal 和 normalized parameters；卡片展示参数及这一 digest。
approve/reject 使用人类 JWT，分别写 CAS 状态；approve 不提交任务。

主要错误：401 缺认证/委托过期；403 FEATURE_DISABLED/FORBIDDEN/WRITE_GATE_BLOCKED；
404 无资源/无关联；409 审批冲突或 RECONCILIATION_REQUIRED；422 参数/路径错误；
503 Redis/依赖不可用。旧 SSE/tool/cards 兼容保留，新增 platform_tool 事件；AI result
继续使用 llm_payload/ui_payload 双通道，ui_payload.bioops 承载共享预案卡。

SRR/PRJNA 仅为源码候选、运行支持 Unknown；GSE/GSM NEEDS_METADATA_RESOLUTION，
任意 URL、processed-data、matrix、Dataset 创建不在范围。prepare 不创建目录/任务/队列，
确认与审计记录是允许的元数据副作用。unknown 规模、progress 或报告不编造数值/链接。
