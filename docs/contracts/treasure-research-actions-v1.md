# Treasure ResearchAction v1

权威类型：子仓 `src/island/contract.ts`；父仓 `frontend/src/types/treasureIsland.d.ts` 同步副本。React 只提交 intent，不含认证 token、owner/project、Redis key 或可执行路径。Vue useResearchWorkflow 持有网络和已认证 session，Gateway 每次重新推导 project/user/scopes。原 DatasetCard 通过 PresentationContext 发布动作；不改原 Node 工具或建立新执行系统。

| Intent | 平台映射 | 副作用边界 |
|---|---|---|
| dataset.inspect(discoveryRef) | Gateway dataset.discover(accession) → DatasetImportService.discover → GeoMetadataAdapter.resolve | 无项目允许公开元数据核验；没有下载 Task |
| dataset.prepare_import(mode,selectedIds,maxBytes,requestKey) | Gateway dataset.prepare_import → DatasetImportService.prepare | 项目必须来自会话；权威来源再查；持久预案与确认，无 Task/队列/数据文件 |
| dataset.list / dataset.version | Gateway list_project_assets / inspect / list_compatible_workflows；复用 Dataset detail REST | 只读真实版本、Handoff、资产、已注册兼容 Flow；Gateway inspect附加handoff_frozen，不将未冻结manifest的digest误认冻结证明 |
| analysis.prepare | Gateway analysis.prepare_from_dataset → DatasetAnalysisService → AnalysisFlowToolService | 冻结 hash、样本/数据类型与统一 validator；无 Task |
| proposal.decide | Dataset Import/Analysis 原 REST JWT-only approve/reject | 人工操作；下载与分析独立；不发 execute |
| records.refresh | Gateway related | 恢复持久预案、真实 Task；不是 ToolTrace |
| delivery.read | Gateway research.project_delivery → ResearchProvenanceService / 现有报告记录 | 只读 Task/报告引用；无报告为 NOT_GENERATED |
| task.open / report.open | 平台任务中心与 `/reports?reportId=...` | UUID 校验；目标页面再授权 |
| workflow.close | 清除当前展示并增加 generation | 不取消已排队业务任务 |

下载与导入采用同一个 DatasetImportService 预案：下载运输由其复用 DownloadService 处理，不叠加第二个 downloads.prepare 确认。准备时 requestKey 由模块生成，选择/预算变化重建；请求期间阻止重复点击；同参数重试由现有服务幂等保证。分析 Prepare 复用现有服务，可能创建独立预案，不声称具备下载预案同样的幂等键。

React 接收的 WorkflowView 仅含已筛选的来源 URL/响应摘要、样本信息、候选标识、版本/资产类型/hash、预案状态/摘要/有效期及真实任务/报告引用，不传内部 normalized_request 或 confirmation token。源 URL 仅公开科学来源 allowlist + HTTP(S)；服务端下载来源继续 HTTPS 精确主机白名单、无重定向。
