# CygnusX ResearchPlan v1

实施状态：PLAN_ONLY，功能默认关闭；不授予科研执行或发布权限。权威模型在 `application/schemas/research_plan.py`，生成命令 `.venv/bin/python scripts/export_research_plan_contracts.py`。输入与服务器视图分别发布，禁止把输出 Schema 作为模型可写参数。

## 模型建议

`ResearchPlanDraft` 接受固定 schema_version、research_question、assumptions、steps、budget。拒绝 owner/project、plan_id/version、状态、审批、Task 完成事实和额外字段。步骤只允许白名单 StepKind，工具/effect/预期产物由服务器映射；模型不能更换 shell 或任意 URL/路径/命令。嵌套参数拒绝身份、凭证、确认自证及路径覆盖。

最多 20 步、单步参数 16KiB、层级 8、列表/对象 100 项；服务器另有总 payload、calls、time、events 上限。max_retries 固定 0。未知存储/计算预算为 null；max_model_tokens 是计划声明，当前没有新增 LLM 调用/计费，不能当成已有 Runtime token 的跨轮实测预算。

`bindings` 仅指定 argument/from_step/output。必须来自直接依赖且类型兼容；拒绝循环、重复/悬空节点、覆盖 literal 参数和不兼容端口。模型不能填写 output 值。只读 Dataset 端口可从已核验上游引用解析；缺少实际导入/任务输出时 WAITING_INPUT/冲突，不能从自然语言补造 ID。写步骤必须绑定独立 prepare 端口，不能直接传 proposal_id 自证执行。

## 服务端版本和状态

服务端分配 plan_id/series/version、可信 owner/project、规范 JSON SHA-256、状态、步骤调用与实际 Task/报告引用。新增 ResearchPlan 只表示意图，绝不创建 Run/Task 占位。版本文档不可原位修改，修订生成新行、旧行 superseded_by；旧审阅不能转移。ORM/PG guard 保护文档字段；真实 PostgreSQL 迁移尚待验收。

状态集 DRAFT/VALIDATED/READY_FOR_REVIEW/REVIEW_REQUIRED/APPROVED/RUNNING/PAUSED/COMPLETED/PARTIAL/FAILED/CANCELLED/RECONCILIATION_REQUIRED。当前 prepare 校验后为 READY_FOR_REVIEW。JWT review 只审阅意图，900 秒默认 TTL，**不批准任何具体写动作**。只读步骤全部结束仍是 READY_FOR_REVIEW，不宣称完成真实科研任务。写步骤显示 WAITING_APPROVAL，运行门禁未准入时不派发。

每次访问复核 active user、项目 owner、模块与所引用 Dataset/Task。Digest 不是签名，不代表防数据库管理员篡改。实际 input/output SHA 与环境证明仍由 Phase3/4 原业务链负责。

## 协调、恢复与实际证据

一次 advance 最多一个 ready 的只读/prepare 调用，复用 Gateway 并保留其 ToolInvocation/request digest；调用前持久 SUBMITTING。存在 in-flight reservation 不并行调度；异常保留 RECONCILIATION_REQUIRED，不自动重放。对账仅查询已有 invocation/Task/provenance，缺失工具响应后置条件仍要求人工审核。暂停/取消只停止后续计划，不取消或删除业务 Task/资产。

Task 状态来自实际 provenance。success 但无 manifest/产物核验仍 PARTIAL；报告不完整单独标记 REPORT_DELIVERY_INCOMPLETE。双报告链接与 manifest SHA 来源于既有真实投影，不把模型的 COMPLETED 当成 Worker 事实。没有新增分析重试或报告生成引擎。

## HTTP 和共享工具

REST 前缀 `/api/v1/projects/{project_id}/research-plans`：list/create、get、`/{id}/versions`、review、advance、control、reconcile、events。prepare/revise 只写计划元数据；review/advance/control/reconcile 只接受人类 JWT。review body 只有 expected_digest；advance 只有 session_id，必须同 owner/project。客户端不可注入批准字段。

两种 Agent 共用 `research.plan.prepare/validate/get_status/get_evidence/assess_claim/artifact_cell`。只读工具不需要写审批，但每次都复核权限；不提供 Agent approve/advance/execute 能力。Gateway、MCP preset、ToolBridge 和平台 Agent schema 同源，真实外部 Transport 未验收。

科研证据接口 `/projects/{project_id}/research-evidence/tasks/{task_id}/claims` 与 `artifact-cells`。Claim 引用存在最多 PARTIAL，任意自由文本不自动 VERIFIED；数值须从已核验 deg.tsv 固定 gene_id/列单元格读取，NA 保留 null。返回 Task/FileRecord/manifest 关联、SHA、行列和参数，不接受模型填写统计值。物种/配对/分组/重复/输入类型和混杂预检查不替代原 Flow 最终校验或 DESeq2 统计程序。

## 对账并发边界

SUBMITTING 的稳定 request_id 绑定本版本 digest 和 step_id。最新 STEP_RESERVED 在工具超时窗口内时，手动对账保留调用进行状态；窗口过期或保留记录缺失才转入待人工对账，不推断未执行，也不重投。人类暂停/取消在异常路径保留。锁定读刷新数据库当前状态，不能用 ORM 旧缓存判断是否仍获准推进。计算完成仅接受既有服务的 success/completed；未知状态即使报告 READY 也要求人工核验。真实 PostgreSQL 并发锁与多进程验证仍待门禁解除。

## 项目与版本链接

前端使用 `/projects/{project_id}?planId={plan_id}` 读取指定持久版本；服务端仍验证 owner/project，不从路由 ID 推定授权。指定版本通过 get API 加载，避免最近计划列表的数量上限隐藏历史版本。版本/项目变化会清理当前结果和轨迹；迟到响应不能覆盖新视图。superseded_by 仅作为服务器提供的后继版本链接，不能继承旧审阅。
