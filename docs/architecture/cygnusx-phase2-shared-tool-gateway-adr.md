# Phase 2 ADR：主进程受控 Gateway 与双 Runtime

状态：源码实现；写能力运行准入 BLOCKED。现状权威见
[共享工具架构](../../ARCHITECTURE_DESIGN/CygnusX_agent_tool_gateway.md)。

1. 保留 Node/TypeScript 科研检索与 Python Agent Runtime，不新增网关微服务。
2. 共享 capability 来自 Pydantic 契约；Node 与 MCP preset 投影同一 schema，业务落到
   AnalysisFlowToolService / DownloadService / TaskService，不复制执行器。
3. Node 使用 BFF 创建的有限 JWT 委托，仅 read/prepare；固定 audience/issuer、TTL、
   user/project/session/token_version、Redis callback nonce；服务 static Key 不成为用户授权。
4. 复用 ToolConfirmationService；人工 JWT 才能 approve。关键 owner/project/session/
   operation/normalized parameters 全部参与摘要；没有布尔自证或前端确认状态库。
5. 原 Task 没有可信 Project 关联，既有 MCPLog/MessageEvent 不满足 durable dedupe 与
   project 查询。新增最小 AgentToolInvocation 表，保留原 Task 执行状态权威，不做 Dataset。
6. Phase 0B/1 运行证据不足，当前源码门恒关；环境变量仅表达请求，不能自证 READY。
   独立 download/analysis/cancel 开关默认 false，取消没有执行实现。
7. 模型/客户端超时视为结果未知。先持久 SUBMITTING，再触及业务，失败需人工对账，
   不宣称跨 Redis/SQL/queue exactly-once。下载未经运行配额和规模验收仍不允许启用。
8. 回滚关闭读开关/callback、保留关联与 Task。先保全审计再考虑迁移 downgrade，禁止
   reset 其他阶段未提交代码或暴露旧 Node 公共入口。
