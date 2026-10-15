# CygnusX Dataset Handoff v1

活动架构权威为 `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md`；本文件定义公共传输契约，不替代 ORM 或迁移。生成器：`python scripts/export_agent_tool_contracts.py`。严格 schema：同目录 `cygnusx-dataset-handoff-v1.schema.json`；源码 `application/schemas/dataset.py::DataHandoff`，extra 字段拒绝。

| 字段 | 含义 |
|---|---|
| handoff_schema_version | 固定 `1.0` |
| project_id / dataset_id / dataset_version_id | UUID；owner 来自认证上下文，不接受工具自报 |
| source | repository、accession、parent、可信 URL、access 状态与响应证据 |
| ingestion | ingestion/job ID、真实 download Task IDs、真实或待对账状态 |
| assets | asset_id、FileRecord UUID、用途、科学类型、格式、字节数、实测 SHA-256、校验及可用性 |
| samples | 既有 Sample ID、稳定 sample_key、源 accession、关联 FileRecord、源原文、独立人工分组及审阅状态 |
| validation | dataset_ready、compatible_flow_ids、blocking_reasons、worker_paths_verified |
| provenance | 发起人、原 invocation/session 关联、人工审阅历史、输出请求状态 |
| manifest_hash | SHA-256：`json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)`；计算时该字段为 null |

科学类型枚举：RAW_FASTQ、RAW_INTEGER_COUNTS、NORMALIZED_EXPRESSION_TPM、NORMALIZED_EXPRESSION_FPKM、NORMALIZED_EXPRESSION_CPM、TRANSFORMED_EXPRESSION、MICROARRAY_EXPRESSION、SINGLE_CELL_COUNT_MATRIX、SAMPLE_METADATA、UNKNOWN。用途 `raw_counts` 不构成科学类型证明。不能把未知数据转为高置信分类；保存原 gene ID，不静默去重、转置、四舍五入、改样本名。

冻结把 manifest 保存在 DatasetVersion；之后 GET 返回相同快照并重查文件/样本归属，不能用随后编辑的 live 投影替代批准的输入。更正创建带原因的新版本。哈希不是签名，DB 管理员可修改事实；执行时还须校验当前文件摘要和权限。

未知 assay 显式阻塞（ASSAY_REVIEW_REQUIRED）；RNAFlow/counts 的兼容性要求 bulk_rnaseq，不因 FASTQ/counts 文件类型跨越实验类型边界。

Readiness 分层：文件存在/校验、科学类型与映射、流程参数、Worker 挂载是不同事实。当前 `worker_paths_verified=false`；`dataset_ready=true` 仅说明有界本地资产检查通过，绝不表示生产可执行。冻结未通过检查的版本可留审阅证据，但不能准备兼容流程。

REST 前缀 `/api/v1/projects/{project_id}`：datasets list/create/detail；datasets/{id}/versions create；versions/{version}/assets、samples、verify、review、handoff、handoff/freeze、provenance、analysis-prepare；样本 review、资产 review/expand；import-proposals list/prepare/get/approve/reject/execute/reconcile；analysis-proposals get/approve/execute。人工登记、审阅、批准和执行使用 JWT，服务 API key 不能代替人类批准。

ImportPrepare：可选既有 dataset_id（必须同owner/project；新导入创建空白新版本，不覆盖历史）、accession、raw/processed、selected_ids、name、UUID request_key、max_bytes；禁止 owner、路径、URL 替换或 user_confirmed。返回真实 proposal/ingestion ID、project/version、规范化下载参数、参数哈希、TTL、预算/未知项、Task状态及 errors；批准不提交任务。相同 owner/project/key/内容复用；内容改变冲突。SUBMITTING 歧义禁止重放。

错误分层：FEATURE_DISABLED/WRITE_GATE_BLOCKED、NOT_FOUND/FORBIDDEN、CONFIRMATION_MISMATCH/SOURCE_CHANGED、IMPORT_LIMIT/QUOTA_EXCEEDED、PATH_ESCAPE、VERSION_SEALED、RECONCILIATION_REQUIRED。UNKNOWN/UNAVAILABLE 不是成功。无进度来源时 progress=null，不合成百分比。结果和报告未建立关联时返回 UNKNOWN / NOT_REQUESTED，不虚构 Run 或已交付报告。

Agent schema 与 REST 复用 DTO，完整投影见 `cygnusx-agent-capabilities-v1.schema.json`。默认隐藏 Dataset 能力，开启只读目录也不开放 execute；模型不能自证确认。UI 显示来源和摘要、审批失败及到期状态，始终禁用尚未准入的执行按钮。
