# ADR：受控研究计划与既有执行事实的边界

状态：实施中，PLAN_ONLY；真实执行未准入。

已检查 `RunPlanService`/`RunModel`：它们表达一个已选 Flow 的 Snakemake plan、单个 Task 和 dry-run 后确认，不表达数据发现、版本化 Dataset、独立审批及报告交付 DAG。FlowAgent 的 `src/tools/platform.ts` 也只提交同一单 Flow 计划；本地 shell/composed/ledger 不应搬入平台科研 Agent。`AgentRuntimeGateway` 是对话运行入口，并非跨对话持久科研计划。保留两个 Agent Runtime，不增加 LLM loop、下载器或 Snakemake 执行器。

同时检查既有 MASPlan/MASRun/MASNode：MASPlan 使用全局唯一 plan_hash，记录 created_by，但没有项目隔离及研究计划版本语义；MASRun/MASNode 表达可执行 Agent 图。直接复用会混合科研审阅意图与既有 Agent 执行状态，因此保留原模型，并以受限 ResearchPlan 引用既有执行事实。

因此新增最小的 ResearchPlan 文档/版本与步骤状态协调层，表示可审阅意图，**不创建占位 Run/Task**。实际执行与产物仍取既有 Gateway/Invocation、TaskService、Dataset/Handoff、FileRegistry、ResultObservation、Report/Snapshot。每个副作用需要原工具独立人类审批；整份计划的人类审阅不等于未来工具无限授权。

模型只能建议研究问题、假设、白名单步骤、资源引用、依赖和预算。owner/project/id/version/status/审批/Task 完成事实由服务器决定，拒绝额外字段。参数变化创建新版本，旧版只保留历史；不能转移审批。SUBMITTING 或未知提交状态只对账，不自动重放。

先实施严格 DAG/工具契约、只读/prepare 和可测状态机，再接持久化及 UI。新增迁移必须单独记录真实 PG 演练结果；SQLite 通过不能当作 PostgreSQL 验收。默认功能关闭，源码 Agent 写门禁不变；不提供单环境变量解锁 live 的通路。
