# CygnusX BioOps · Phase 4 实施任务书

## 受控科研执行、证据链与可复现报告交付闭环

**英文主题：** Provenance-Aware Execution, Evidence & Reproducible Research Delivery  
**阶段：** Phase 4（P4-0 + P4-A ～ P4-G）  
**日期：** 2026-10-15  
**模式：** 前置准入核验 → 受控实施 → 隔离集成测试 → 运行验收 → 交付报告  
**核心原则：** 复用既有系统；保持来源证据真实；安全失败关闭；禁止把隔离测试冒充真实部署验收。

---

# 0. Role / 工作方式

你是一名资深 AI for Science 平台架构师、科研数据溯源工程师、生物信息分析工作流工程师、后端安全工程师与测试负责人。

请基于当前 **CygnusX BioOps 主仓库真实工作树**，以及此前 Phase 0A、0B、0B Closure、Phase 1、2、3 的代码和实施证据，完成 Phase 4。

**本轮是实施任务，不是只写设计方案；但不得在前置运行门禁未通过时启用真实写操作。**

请按“检查 → 最小方案 → 实施 → 自动化测试 → 运行证据 → 准入判定”的顺序执行。遇到缺乏隔离环境、权限、真实服务或可信版本证据的情况，允许继续完成不依赖危险运行能力的契约、只读服务、合成测试与 UI 工作，但必须将相应真实执行门禁标记 `BLOCKED`，不得绕过。

## 0.1 必读材料

在实际代码中搜索并阅读（以实际文件位置为准）：

- `cygnusx-phase3-dataset-ingestion-handoff-implementation.md`：最新 Phase 3 实施报告。
- `cygnusx-phase0b-runtime-integration-implementation.md`：Phase 0B 验收报告。
- Phase 0B Closure 最终记录（如存在）。
- Phase 1、Phase 2 实际实施报告（如存在）。
- `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md`：Phase 3 报告给出的活动数据架构文档入口。
- `docs/adr/phase3-dataset-provenance-and-handoff.md`。
- `docs/contracts/cygnusx-dataset-handoff-v1.md` 及关联 JSON Schema。
- 现有 RNAFlow / CountsDEGFlow 的 Flow Schema、Result Manifest，以及执行证据报告设计与实现。

如果某文件不存在，不得猜测或据此伪造已实现内容。请报告缺失并查找权威替代入口。

## 0.2 Phase 3 已有基础：需核实而非重建

此前报告称已实现：

1. `datasets`、`dataset_versions`、`dataset_sources`、`dataset_assets`、`dataset_samples`、`dataset_ingestions`、`dataset_analysis_links` 七类关联表。
2. GEO/ENA 查询 Adapter、原始 FASTQ 和 processed data 导入预案、数据安全校验。
3. 冻结 Data Handoff Manifest、基于 FileRecord 的资产关联以及校验摘要。
4. RNAFlow 既有 FASTQ 工作流的 prepare，及新增 `CountsDEGFlow` / `flows/counts_deg.yaml` 的本机合成数据运行测试。
5. 共享 Gateway、Dataset UI、人工审核、异步任务记录与对账基础。
6. Phase 3 所有 Agent 写入口默认关闭，且 `WRITE_RUNTIME_ACCEPTED=False` 的源码门禁没有解除。
7. Phase 3 结论为 **CONDITIONAL（隔离）/ BLOCKED（真实运行与发布）**。

上述均为报告中的既有陈述。请从当前代码及测试重新核对；不要把本轮计划当作已经完成。

---

# 1. Phase 4 目标与范围

## 1.1 最终科研链路

```text
科学问题 / Discovery Proposal
        ↓
GEO/ENA 检索证据 + 用户确认
        ↓
Dataset → DatasetVersion → Asset / Sample / Source
        ↓
Frozen Data Handoff Manifest
        ↓
Analysis Prepare → 可信批准 → Task / Execution
        ↓
FlowFrame Worker → Result Manifest → Artifact Registry
        ↓
科学 BioReport + 可复现执行证据报告
        ↓
Project Research Delivery / Provenance Trace
```

**核心成果不是“能够生成报告”，而是能够证明报告对应的是哪一份输入数据、哪次受控计算和哪组实际产物。**

## 1.2 本轮必须解决的系统断点

- DatasetVersion 与真实分析 Task 的关联不能只停留在 prepare 或计划记录。
- 执行结果登记后，必须核对它是否来自对应输入版本/Flow/Task。
- Result Manifest、FileRecord、ReportModel 与现有执行证据报告之间的关系需要稳定且可查询。
- 科学 BioReport 和执行证据报告职责不同，必须并列关联而非相互替代。
- 存在部分执行、产物缺失、checksum 不符、报告失败时，平台应给出真实的状态而不是虚假的成功。
- 任务与报告之间的异步投递可能产生重复事件或未知状态，不得自动重复运行昂贵分析。
- 寻宝鼠与 AI 助手应能查询证据与状态，但不能仅凭模型陈述制造“已验证科研结论”。

## 1.3 绝对排除

- 不重写科研寻宝鼠检索 Agent。
- 不新建第二套 Dataset、FileRecord、TaskService、ReportService 或运行引擎。
- 不重做 Phase 3 的 GEO Adapter、矩阵分类器或 counts-only 统计方法。
- 不以新表替换现有不可变 Dataset Handoff。
- 不允许自动将 TPM/FPKM/Series Matrix 当成 raw counts 分析。
- 不修改既有 RNAFlow 或 CountsDEGFlow 的统计结果以迎合展示。
- 不擅自改变镜像、运行二进制、生产 DB、已有数据卷或参考库。
- 不为达到 READY 直接把源码安全门禁改成 true。
- 不自动对外发布报告或将含受控数据的报告设置为公开。
- 不用模拟任务生成虚假的生产溯源记录。

---

# 2. P4-0：前置 Gate 核验与运行阻断闭环

**P4-0 是进入 Phase 4 实际执行与发布的强制门禁。**

Phase 3 报告明确列出：真实 PG 迁移/并发、Redis CAS/TTL/恢复、实际 Worker 挂载/二进制、寻宝鼠镜像 SHA/digest、外部 MCP transport、双用户全栈和下载安全预算均未通过运行验收。

## 2.1 先执行只读基线探针

记录：

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git submodule status --recursive
git diff --stat
```

核实：

- Phase 0B Closure 是否有真正的最终 READY 证据。
- Phase 1 / 2 的身份、Gateway 与确认契约是否已发布或仅在隔离代码中存在。
- Phase 3 源码门禁、运行开关以及菜单/工具隐藏状态。
- 所有受控写入口在不满足门禁时是否可由后端拒绝，而不只是按钮禁用。
- 运行镜像、Worker binary、参考资源、挂载和 Flow 版本是否能在实际测试实例中证明。
- 数据库迁移是否在真实隔离 PostgreSQL 完成。
- Redis 多进程/跨实例确认 CAS、TTL、重启及故障恢复是否完成。
- 外部 MCP STDIO/HTTP、用户身份与受控 Tool 调用是否完成真实传输验证。
- 非生产双用户、两项目权限与审计能否完成端到端验证。

## 2.2 Gate 判定

采用：

- `READY`：所需真实依赖与跨模块验证完成，可执行批准范围内的受控端到端测试。
- `CONDITIONAL`：只允许只读契约、隔离实现、合成分析及 UI；不得开放真实 Agent 写操作。
- `BLOCKED`：存在 P0 安全或执行链路阻断，不得宣称发布就绪。

**不得将本轮 P4 功能代码完成自动推导为 P4-0 READY。**

## 2.3 在本轮内允许修复的阻断

仅限最小、可证明必要的变更：

1. 隔离 PostgreSQL migration / 并发与约束测试。
2. 真实隔离 Redis CAS、TTL、跨消费者确认与故障恢复。
3. 真实 MCP Transport 的工具发现、身份与审批验证。
4. 从真实测试 Worker 读取镜像 digest、EBIDownload/Polariseq 摘要、Flow 路径、Snakemake/R 版本、文件挂载与权限。
5. 模拟恶意 URL、重定向、超出预算的下载负例。
6. 双用户/双项目合法与越权调用的隔离测试。

如果执行环境不能启动这些服务，提供**可复跑的隔离验收脚本和操作清单**，标记 BLOCKED，不允许虚构结果，也不允许接入生产服务作为替代。

---

# 3. P4-A：Dataset → Execution → Result Manifest 的可信链路

## 3.1 首先复用现有对象

检查并记录真实 ORM、DTO、Service 入口：

- ProjectModel / Dataset / DatasetVersion / DatasetAnalysisLink。
- FileRecord / Sample / DatasetAsset / Frozen Handoff。
- TaskModel / RunModel / execution event。
- Result Manifest / RNAFlow 输出清单 / CountsDEGFlow 输出清单。
- ReportModel、ReportFileModel、ReportSnapshot、ReportGenerationJob。
- TaskService / FileRegistry / ReportService / analysis worker callback。

**不要假设所有任务都有 RunModel，也不要因为存在 TaskID 就虚构独立 Run。**

## 3.2 执行前冻结分析关联

建立（或补齐）最小、可持久化的关联：

```text
Project ID
Dataset ID + DatasetVersion ID
Frozen Handoff SHA-256
Analysis Proposal / Link ID
Flow ID + Flow Version / Digest
Normalized Parameters Digest
Authenticated Actor / Approved Confirmation
Task ID（实际创建后）
```

实际开始计算前要求：

- 同一 owner / project 的权限重查。
- DatasetVersion 仍为可信冻结版本，所有必要 FileRecord 存在。
- 输入文件实际摘要与冻结 Handoff 匹配。
- 资源、样本与组别满足相应 Flow Schema 和科学检查。
- 输入到 Worker 的路径经过现有 ManagedFileResolver/路径权限检查。
- 镜像、Worker 挂载与下载门禁属于真实验收过的配置。
- 最终执行前校验由 TaskService 执行，不能只依赖 UI/Agent prepare。

## 3.3 Task 创建后建立稳定关联

- 使用业务权威的 Task ID，不能从 Agent 生成一份假的任务编号。
- 如果 Task 创建失败，不允许 DatasetAnalysisLink 记录为 RUNNING。
- 若在 DB/queue 交界发生不确定状态，记录 `SUBMITTING` / `RECONCILIATION_REQUIRED`，等待对账。
- 幂等键与参数摘要绑定，同一请求不得重复创建昂贵任务。
- 避免反向关系只靠用户路径或自由文本。
- 不改变原 TaskService 的业务执行语义。

## 3.4 Result Manifest 验证

在分析任务报告成功后：

1. 获取由实际 Worker/Flow 生成的 manifest。
2. 核验 Task、Flow、执行版本与当前绑定是否一致。
3. 验证 declared files 在受控范围内存在，路径可解析。
4. 验证文件真实 SHA-256/大小/类型（使用合理的 Worker 预算）。
5. 对每个产物分配稳定 FileRecord/Artifact 引用。
6. 记录成功、缺失、校验不符、不确定的区别。
7. 不允许自行补造缺失产物或依据文件名凭空推导科学结果。

如果现有 manifest 缺少输入引用，优先通过有版本的、兼容旧内容的扩展字段或关系链接补充。不能无证据修改历史运行记录。

## 3.5 执行状态与科研状态分离

至少区分：

- `COMPUTE_SUCCEEDED`：分析引擎报告成功。
- `RESULT_VERIFIED`：关键产物和 manifest 验证成功。
- `EVIDENCE_COMPLETE`：按预定要求可回溯必要输入与执行信息。
- `DELIVERY_READY`：可交付物已成功生成并登记。

可按现有模型命名实现，不要求机械创建四个状态表；但不能把 Task success = evidence complete = report ready。

---

# 4. P4-B：Artifact / Evidence / Provenance 关联

## 4.1 数据来源与证据的最低要求

构建可以回溯的最小结构：

```text
SourceAccession / RetrievalEvidence
  → DatasetVersion / FrozenHandoff
    → Input FileRecord / SHA-256
      → AnalysisLink / Task / Flow Config
        → Verified Result Manifest
          → Output Artifact / SHA-256
            → Scientific Report / Execution Evidence Report
```

优先复用已有 DatasetSource、FileRecord、RunEvent、CaseArtifactVersion、ReportSnapshot 和 Manifest，而不是再建立一整套相互竞争的表。

## 4.2 Provenance DTO / Graph

设计只读聚合接口（命名仅为候选，需先查看项目惯例）：

- `GET /projects/{project_id}/datasets/{dataset_id}/versions/{version_id}/provenance`
- `GET /tasks/{task_id}/provenance`
- `GET /reports/{report_id}/provenance`

DTO 至少包括：

- 主体资源 ID / owner / project。
- 输入 DatasetVersion、冻结 Handoff hash。
- 数据来源证据（GEO、ENA、URL、检索时间、证据摘要及可信程度）。
- 样本与分组的来源/人工审阅记录。
- 下载或导入 Task、时间、实际文件指纹。
- Flow 标识、版本、配置摘要及已观察的运行环境。
- 分析 Task、执行时间、真实状态。
- 结果 manifest 与输出资产完整性状态。
- 科学报告与执行证据报告链接。
- 缺失项、未验证项、证据状态。

不要将 W3C PROV 或 RO-Crate 的部分字段直接宣称为标准完全兼容；可优先提供项目内部规范化结构，未来再实现标准映射。

## 4.3 数据不可变与校验语义

- 冻结版本不允许原地静默修改。
- 用户审阅产生独立审阅记录或新 DatasetVersion。
- 文件变更 → 指纹不符，必须标记并阻断依赖该输入的自动执行。
- SHA-256 用于内容完整性与变化检测；**不等于防恶意管理员篡改的数字签名**。
- 输出缺失 → 明确 `MISSING`；尚未检查 → `UNKNOWN`；验证失败 → `FAILED`。
- 不自动删除或覆盖历史报告和输出。
- 显示内容和下载链接必须继续实施 Project/owner 授权。

## 4.4 Evidence Capsule（如已有应复用）

调查平台已有 evidence capsule、artifact manifest、ARDP、RunEvent 与 Snapshot 的真实实现：

- 如果已经存在统一聚合层，在其上补充 DatasetVersion 输入引用。
- 如果只在有 Run 的路径支持 evidence capsule，不得假定网页直接 Task 一定有 Run；应该做可选关系。
- 如需要新增表或字段，说明为什么当前模型无法表达、迁移与回滚风险。

---

# 5. P4-C：BioReport 科学报告交付链路

## 5.1 查清现状

首先检查：

- RNAFlow / CountsDEGFlow 是否生成报告输入和 Result Manifest。
- BioReport 实际执行形式：CLI、Python import、Docker 或已有任务规则。
- 平台 ReportService / FileRegistry 是否已负责报告登记。
- 科学报告生成是否是 Snakemake 工作流的一部分还是下游独立服务。
- 本地 `../bioreport` 与部署实际版本是否一致。
- 是否存在生成成功但 ReportModel 登记失败的情况。

不要凭 README 假设 BioReport 有独立 REST API。

## 5.2 交付契约

建立可查询关联：

```text
DatasetVersion → Analysis Task → Result Manifest
                                  ↓
                          Scientific Report
                                  ↓
                           Report FileRecord
```

科学报告需要可回溯：

- 分析任务和输入版本。
- 用到的结果文件及其指纹。
- 生成器版本（可核实者）。
- 参数/配置摘要。
- 报告生成状态及失败原因。
- 归属项目与用户。

报告可包含图表与分析解释，但不能自动把研究假设写成经过生物学实验验证的结论。

## 5.3 最小兼容方式

- 优先复用现有 BioReport/Quarto 任务，不改变既有分析脚本。
- 如果流程已输出 HTML，优先进行校验、登记、关联；不要重复生成。
- 如已有 PDF 输出接口，才可添加 PDF 交付；不能凭扩展名假装 PDF 已存在。
- 报告生成失败，不要自动重跑上游差异表达或 FASTQ 分析。
- 报告错误与分析执行错误保持不同状态。
- 支持针对已有有效产物进行单独的交付重试与对账。

---

# 6. P4-D：可复现执行证据报告

## 6.1 与科学报告职责分离

**Scientific BioReport：** 展示 QC、统计结果、差异表达、富集及科研图表。  
**Execution Evidence Report：** 展示输入/输出指纹、任务、参数、流程版本、环境、事件与证据完整性。

两者可在统一“科研交付”页面呈现，但不得混成一份缺乏溯源边界的报告。

## 6.2 复用既有快照与异步 Job

调查并优先复用：

- ReportSnapshotModel。
- ReportGenerationJobModel。
- ReproducibleReportService。
- SnapshotBuilder。
- Archive/HTML 生成逻辑。
- 现有 ReportModel/ReportFileModel。

让快照包含可证实的 DatasetVersion/Handoff/Input/Result 信息，不覆盖其他阶段原有记录。

## 6.3 缺失信息必须显式标记

例如：

```yaml
provenance:
  input_dataset_version: verified
  input_sha256: verified
  workflow_release_digest: unknown
  conda_environment: not_observed
  result_manifest: verified
  report_generator_version: verified
```

上例只是契约说明，不能自动填入生产数据。

禁止：

- 用当前环境版本回填历史 Task 的环境版本。
- 把构建配置值说成实际运行容器 digest。
- 用缺失的 input checksum 推导数据确实未改变。
- 用现有报告快照倒推不存在的证据。
- 在报告中展示用户秘密、服务 Token 或无权限原始文件路径。

## 6.4 快照不可变及报告重建

- 一个报告快照绑定具体 Task/数据版本/输入输出证据。
- 同一快照允许幂等重新生成交付文件，但不能悄悄改变快照事实。
- 需要更新证据时建立新快照版本或新增审计记录。
- 失败 Job 可在不重新运行分析的前提下安全重试。
- 文件在失败后部分存在，应对账并复用，而不是重复占用存储。

---

# 7. P4-E：交付状态、异步事件与故障恢复

## 7.1 状态模型

可以使用既有 Task/Report 状态及少量聚合 DTO，不强制建立新的状态机表。

但 UI/API 必须区分：

1. 数据准备完成。
2. 分析任务已提交。
3. 分析计算成功/失败。
4. 结果文件登记及完整性验证成功/失败。
5. 科学报告成功/失败。
6. 执行证据报告成功/失败。
7. 整体交付 READY/PARTIAL/BLOCKED。

**PARTIAL 不是失败的别名，而是已经有可保留成果但存在未完成交付。**

## 7.2 事件触发原则

- 能复用既有 Celery 与任务完成事件就复用。
- 注册 Result Manifest 与报告 Job 必须具有幂等性。
- 不重复执行已经成功的科研计算。
- 发布下游 Job 失败时留下可恢复记录与异常原因。
- `Task success` 发生，但 FileRegistry 报错时，必须能够补登记而不是重新执行分析。
- Report 生成失败只重试交付阶段。
- 对 Queue/DB/Redis 不同事务的未知状态采取对账优先。

## 7.3 Reconcile-only 机制

审查 Phase 3 已有 reconciliation job / Celery Beat：

- 优先扩展已有轻量对账，而不是再建另一套轮询循环。
- 每次限制扫描范围/批量大小。
- 必须依 owner、task_id、dataset_version 和状态审计进行关联。
- 如果存在投递不确定状态，不允许自动重放下载或计算。
- 对账仅修复已存在产物、记录、链接或交付状态。
- 不自动删除用户数据，不自动重新下载大文件。

## 7.4 关键异常场景

至少处理：

- Task 已成功但 Result Manifest 缺失。
- Manifest 存在但 checksum 不符。
- Task 成功、报告失败。
- Report 文件存在、ReportModel 缺失。
- 数据集被冻结后，原输入文件被更改。
- 生成报告时项目权限被撤销。
- Celery 重复投递报告 Job。
- Worker 中断后存在部分输出。
- 用户刷新页面、切换项目后出现迟到事件。
- 有结果产物但 RunModel 缺失。

---

# 8. P4-F：前端、寻宝鼠与 AI 助手的交付体验

## 8.1 项目内“科研执行链”

优先利用现有 Vue 页面、数据卡片、任务列表和报告中心，新增或扩展“科研执行与证据”视图：

```text
科研问题
  ↓
发现的数据集 / GEO accession
  ↓
Dataset vN（来源、样本、文件）
  ↓
下载与验证（Task / checksum）
  ↓
分析（Flow / 参数 / Task）
  ↓
结果清单（Artifact / 校验）
  ↓
科学报告 + 执行证据报告
```

要求：

- 支持点击进入 DatasetVersion、Task、Artifact、Report。
- 显示证据缺口和人工审阅信息。
- 显示真实 Task/Delivery 状态，不使用伪造进度。
- 明确标注版本和已验证/未知/不适用。
- 不重复做一套独立的文件管理器。
- 遵守平台既有设计系统与响应式布局。
- 前端无权限时不泄露敏感路径及来源信息。

## 8.2 寻宝鼠与 AI 助手

在共享 Gateway 上增加**只读查询能力**（名称是候选，先比对现有工具表）：

- `research.get_dataset_provenance`
- `research.get_analysis_delivery_status`
- `research.list_verified_artifacts`
- `research.get_report_links`
- `research.get_evidence_gaps`

要求：

- 两种 Agent 共享相同的后端 DTO 与鉴权。
- 工具不允许模型决定可信 owner / project。
- Agent 回复中将 VERIFIED、PARTIAL、UNKNOWN 区分呈现。
- 不能在未实际运行时说“分析已完成”。
- 不能依据报告文件名谎称文件存在或有权限访问。
- 不增加能够绕过 Phase 0B/Phase 2 Gate 的写工具。

## 8.3 仅在 Gate READY 时考虑受控交付命令

如 Phase 0B / Phase 2 真实门禁已经通过，可把“请求生成报告”等操作接到既有可信审批与 Job 服务；要求真实人工确认、参数摘要、配额、权限、幂等与状态恢复。

**否则只实现 prepare / preview / read-only，并保持服务端写入口关闭。**

---

# 9. P4-G：真实科研案例验收（先合成、后小型公开数据）

## 9.1 场景一：GEO 原始 FASTQ

前置条件：P4-0 READY、明确授权使用小型公开数据、Worker 存储与网络预算可靠。

候选案例应具有：

- 官方 GEO/SRA/ENA 来源可验证。
- 清晰物种、组织、实验与对照组。
- 明确生物学重复和样本映射。
- 无需受控访问或特殊许可。
- 数据量小，资源配额与参考库明确。

运行：

```text
Discover → Import Proposal → Approval → Download Task
→ DatasetVersion / Handoff → RNAFlow Prepare → Approval
→ Task → Result Manifest → BioReport → Evidence Report
```

每一步都保留真实状态、调用证据、输入输出指纹。任何环节缺证据都不能宣称全链路 PASS。

## 9.2 场景二：GEO 原始整数 counts matrix

前置条件：真实 raw-counts 来源证据、样本 metadata/人工审阅、CountsDEGFlow Worker 认证完成。

运行：

```text
Processed File → 内容识别 → raw-counts 证据
→ DatasetVersion → CountsDEGFlow
→ 实际 DESeq2 → Result Manifest → 双报告交付
```

要求：

- 非负整数、样本与分组一致。
- 至少满足已实现的每组重复数和设计矩阵条件。
- TPM/FPKM/CPM/log/来源不明整数拒绝自动 DESeq2。
- 不擅自改变差异分析的统计设计。
- 对照与实验组、Batch、Reference 均需显式确认。

## 9.3 失败路径与审计

必须包含：

- 数据源不可用或变化。
- 磁盘配额不足。
- 下载部分成功。
- 样本 metadata 不匹配。
- Flow 不兼容。
- 原始文件 SHA 变化。
- Result Manifest 缺失或不一致。
- 报告生成失败。
- 用户失去项目权限。
- 请求重复、Agent 重试、网络断开及恢复。

**不得在真实运行环境不能验收时使用合成流程“冒充”公开数据 E2E。**

---

# 10. 安全、隐私与科研真实性要求

## 10.1 安全边界

- 服务端权威 owner / project / file ID，不信任模型传递的 user_id/path。
- 有副作用执行必须走 Phase 0A 人工确认契约。
- Phase 0B 的 Redis/MCP/Worker P0 未通过时，后端写操作继续禁用。
- 源 URL/附件/外部模型回复属于不可信内容。
- 禁止 SSRF、外部重定向绕过 allowlist、路径逃逸、符号链接、压缩炸弹。
- 文件归属不能仅由路径名称猜测。
- 报告访问和分享必须单独验证权限。
- 不输出密钥、JWT、API Key、完整确认凭证和受限数据。

## 10.2 科研真实性

- 数据发现证据 != 生物学结论。
- Metadata 自动识别 != 实验设计已得到人工核实。
- FASTQ 下载 != 可运行比对。
- 整数矩阵 != 经证明的 raw counts。
- 统计计算成功 != 生物学发现已经验证。
- 报告生成 != 计算过程可复现。
- SHA-256 != 防管理员恶意修改的完整可信签名。

使用 `VERIFIED / PARTIAL / UNKNOWN / NOT_APPLICABLE / FAILED` 等明确状态，不使用绝对表述覆盖缺口。

---

# 11. 数据库与兼容策略

1. 先检查现有 Dataset/Task/Report 关系是否足够；优先加关系与索引，不另建平行核心表。
2. 任何新增表/字段必须列出主外键、唯一约束、owner/project 隔离、级联规则、事务边界。
3. 迁移链保持唯一 head，提供可回滚策略。
4. 首先在 SQLite 快速验证，再在**真实隔离 PostgreSQL**执行 upgrade/downgrade、并发、索引与锁测试。
5. 不删除已有 FileRecord、Sample、Task、Report 或用户文件。
6. 旧 Task 没有 DatasetVersion 关联时保持可读，显示 `unknown provenance`，不得强制补造。
7. 报告新旧 Schema 变化必须支持历史读取或提供显式兼容策略。
8. 不擅自执行生产 DB migration。

---

# 12. 自动化测试矩阵

按照仓库现有测试规范落地。不得把多个重叠子集的 PASS 数简单相加。

| ID | 测试目标 | 最低证据层级 |
|---|---|---|
| T01 | DatasetVersion 与任务提案正确关联 | Integration / DB isolation |
| T02 | 冻结 Handoff 之后修改源文件被拒绝 | Integration |
| T03 | Task 创建失败不记录 RUNNING | Integration |
| T04 | 同参数重复请求仅创建一次任务 | Integration |
| T05 | 参数变化不能复用旧确认或幂等键 | Integration |
| T06 | Task 成功但无 manifest → 非 DELIVERY_READY | Integration |
| T07 | manifest 文件丢失 → MISSING | Integration |
| T08 | manifest 文件 SHA 不符 → FAILED | Integration |
| T09 | 合法 manifest 正确关联 FileRecord | Integration |
| T10 | 输出属于其他用户时拒绝登记 | Integration |
| T11 | 报告登记使用真实 Task 与 DatasetVersion | Integration |
| T12 | 不存在 RunModel 时不虚构 Run | Unit / Integration |
| T13 | 已有 Run 可正确引用证据 | Integration |
| T14 | 输入来源证据缺失显式 UNKNOWN | Contract |
| T15 | 旧历史 Task 可读但溯源缺口可见 | Contract |
| T16 | BioReport 已存在时幂等登记、不重复生成 | Integration |
| T17 | BioReport 失败不重跑计算任务 | Integration |
| T18 | 执行证据报告 Job 失败可以单独重试 | Integration |
| T19 | 快照不可变，修订产生新版本或记录 | Integration |
| T20 | 报告文件丢失或登记失败可 reconcile | Integration |
| T21 | 重复 Celery 交付事件不重复报告 Job | Integration |
| T22 | Task/DB/queue 模糊状态不自动重跑 | Integration |
| T23 | 跨用户 Dataset/Task/Report 链路拒绝 | ASGI / Integration |
| T24 | 跨项目对象 ID 枚举拒绝 | ASGI / Integration |
| T25 | Project 权限撤销后旧报告链接拒绝 | ASGI / Integration |
| T26 | Agent 只读工具不带真实 owner 注入也不越权 | Integration |
| T27 | Agent 不得以自身参数声明已验证状态 | Contract |
| T28 | Agent 未过 Gate 时不能执行写操作 | Integration |
| T29 | 输入内容含恶意路径/重定向拒绝 | Integration |
| T30 | 报告敏感字段脱敏 | Contract / Integration |
| T31 | 旧 Report 与 Task API 回归 | Regression |
| T32 | RNAFlow 真实配置与 manifest 契约 | Contract |
| T33 | CountsDEGFlow 原始 counts 类型约束 | Contract / R negative |
| T34 | TPM/FPKM/log 数据不得进入 DESeq2 | R negative / Integration |
| T35 | Python/TS 前后端 DTO 契约一致 | Contract |
| T36 | 刷新/切换项目不展示迟到状态 | Frontend DOM |
| T37 | 科研交付页面链接与状态正确 | Frontend DOM |
| T38 | PostgreSQL upgrade/downgrade 与并发 | Runtime Integration |
| T39 | Redis CAS、TTL、断连、双进程消费 | Runtime Integration |
| T40 | MCP STDIO/HTTP 鉴权与工具调用 | Runtime Integration |
| T41 | Worker 镜像/二进制/挂载/环境可回读 | Runtime Smoke |
| T42 | 合成 RNA/counts 产物交付闭环 | E2E isolated |
| T43 | 小型真实公开 RNA 或 counts 案例完整闭环 | Live isolated E2E |
| T44 | 失败后对账不重跑原始科研计算 | Integration / E2E |

如果 T38–T43 由于环境不足无法执行，标记 BLOCKED 或 NOT TESTED，不得将 T01–T37 的通过结果转述为生产准入。

---

# 13. Phase 4 验收 Gate（G0–G18）

| Gate | 验收标准 | 是否阻断 Agent 写入/发布 |
|---|---|---|
| G0 | Phase 0B/1/2/3 前置安全与运行证据完成 | 是 |
| G1 | 工作树基线、版本与变更归属记录完整 | 交付前必须 |
| G2 | 冻结 DatasetVersion → Task 关联正确 | 是 |
| G3 | Handoff/输入指纹执行前核验有效 | 是 |
| G4 | Flow/Task 版本与执行参数可追溯 | 是 |
| G5 | Result Manifest 的来源/文件真实性核验 | 是 |
| G6 | 受控 Artifact / FileRecord 登记与权限 | 是 |
| G7 | Provenance DTO 可回溯且缺口明确 | 是 |
| G8 | BioReport 科学报告与 Task/Result 关联 | 发布前必须 |
| G9 | 执行证据快照真实、独立可查询 | 发布前必须 |
| G10 | 科学报告失败不触发计算重跑 | 是 |
| G11 | Delivery 状态明确，PARTIAL/UNKNOWN 不装 READY | 是 |
| G12 | 幂等/对账/故障恢复不重复下载与计算 | 是 |
| G13 | 两用户两项目的跨资源隔离 | 是 |
| G14 | Agent 只读工具一致，受控写入仍有审批门禁 | 是 |
| G15 | 前端可展示来源→分析→证据→报告 | 交付前必须 |
| G16 | PostgreSQL、Redis、MCP、Worker 真实运行验证 | 是 |
| G17 | 小型真实科研案例的端到端执行与交付证据 | 是（宣称 live E2E 前） |
| G18 | 回归测试/实施报告/运行证据/回滚策略齐备 | 交付前必须 |

**不可用“G17 BLOCKED，但 Phase4 READY”作为最终生产结论。**

允许分别给出：

- `CODE_IMPLEMENTED / ISOLATED_PASS`
- `RUNTIME_BLOCKED`
- `LIVE_E2E_BLOCKED`
- `PRODUCTION_READY`（只有门禁全部满足才能宣称）

---

# 14. 工作包执行顺序与提交检查点

## P4-0：准入核验（必须首先进行）

**检查点：** 基线、环境、版本、门禁清单；写能力是否保持关闭。

若无法具备真实运行环境，继续执行不依赖写入的 P4-A～F，但 G0/G16/G17 始终 BLOCKED。

## P4-A：可信 Execution/Result 关系

**交付：** DatasetVersion→Task→Result 绑定、严格 manifest 核验、任务状态/产物状态区分。

**检查点：** 输入变化、manifest 缺失/伪造、Task 成功但产物失败均正确阻断 READY。

## P4-B：Provenance 查询

**交付：** 复用现有模型的 Evidence 聚合 DTO、只读 API、owner/project 安全检查。

**检查点：** 从 Report 反向找到真实输入与 Flow；未知字段不伪造。

## P4-C：BioReport 科学交付

**交付：** 现有报告入口与 Task/Result/Artifact 关联，失败与幂等处理。

**检查点：** 科学报告失败不重算，旧报告仍可用。

## P4-D：执行证据报告

**交付：** Snapshot/Job 补充真实 DatasetVersion/Handoff/Result 证据，冻结与重试语义。

**检查点：** 缺历史数据明确 UNKNOWN，无伪造 Worker 版本。

## P4-E：异步交付与对账

**交付：** 交付状态聚合、失败恢复及 reconcile-only 扩展。

**检查点：** 重复事件不产生重复大计算；遗失 FileRecord 可从可信已有输出补登记。

## P4-F：平台 UX 与 Agent 只读能力

**交付：** 统一科研执行链页面、两个 Agent 的只读证据查询、访问隔离。

**检查点：** 不打开写 Gate，不虚构报告已生成。

## P4-G：真实科研案例

**仅在 G0/G16 已满足，且用户批准小型非生产运行预算与数据源时执行。**

**交付：** 公开来源、实际任务、输出、双报告、链路反查和故障案例。

**检查点：** 从科学报告反向找到 DatasetVersion、来源证据、校验输入、参数、Flow 版本、真实运行环境、Result Manifest 与 Artifact。

---

# 15. 建议代码定位与变更原则

请先通过搜索定位实际路径，不要把下列候选路径当作现成文件：

- `src/cygnusx/application/services/`：Dataset、Task、Report、Provenance 服务。
- `src/cygnusx/infrastructure/celery_app/tasks/`：分析与报告异步交付事件。
- `src/cygnusx/domain/flow/`：Flow Schema / 验证。
- `src/cygnusx/api/v1/`：只读 Provenance/Delivery API。
- `src/cygnusx/infrastructure/mcp/`：受控只读工具 schema/registry。
- `frontend/src/`：项目数据、分析、报告和科研寻宝鼠入口。
- `pipelines/RNAFlow/`、`pipelines/CountsDEGFlow/`、`flows/`：manifest 与 Flow 适配。
- `docs/contracts/`：Delivery / Provenance DTO 契约。
- `docs/adr/`：架构决策。

变更要求：

1. 优先复用既有 Provider/Repository/Service，避免多层重复抽象。
2. 对遗留脏工作树做局部修改，不进行无关格式化。
3. 不自动 `git reset --hard`、`git clean -fd` 或替换他人改动。
4. 数据库迁移与业务代码分批验收，明确状态。
5. 新增真实 Runner 触发路径必须独立权限审查并受 Gate 保护。
6. 每次修改后运行局部测试，然后运行可行的整体回归。
7. 不以全量存量 Ruff/mypy 失败为由忽略新增代码的严格检查。
8. 不擅自提交、推送或部署；如已有未提交成果，保留原状。

---

# 16. 最终交付物

请尽可能按照仓库现有文档规范生成：

## 16.1 实施报告

`docs/implementation/cygnusx-phase4-provenance-report-delivery-implementation.md`

报告应包括：

1. Executive Summary：实际代码完成度、运行准入与是否可开放写操作。
2. Baseline：分支、HEAD、dirty 状态、各模块版本。
3. P4-0 Gate 核验：阻断及真实运行证据。
4. 数据链路架构图：现状与本轮完成后的已验证链路。
5. DatasetVersion→Task→ResultManifest 具体实现。
6. Provenance DTO、Evidence/Artifact 关联。
7. BioReport 与执行证据报告关联。
8. 异步交付状态、对账和幂等策略。
9. Frontend/Agent 只读查询能力。
10. 安全权限模型与审计行为。
11. 数据库 migration / schema compatibility。
12. 测试命令、通过数、失败数、阻断数、超时与真实服务范围。
13. G0–G18 验收矩阵。
14. Changed Files 与变更归属。
15. 剩余风险 / P0、P1、P2。
16. 回滚、数据保全和人工对账 Runbook。
17. 后续 Phase 5 准入结论。

## 16.2 契约与架构材料

建议根据实际需要新增：

- `docs/contracts/cygnusx-research-delivery-v1.md`
- `docs/contracts/cygnusx-provenance-v1.schema.json`
- `docs/adr/phase4-execution-evidence-report-contract.md`
- `docs/runbooks/cygnusx-delivery-reconciliation.md`

**如已有同等有效契约，直接扩展并版本化，勿创建重复文档。**

## 16.3 自动化测试

优先覆盖 T01–T44，并提供实际使用的测试运行命令和机器可读摘要（如项目已具备 evidence 体系则复用）。

区分：

- UNIT
- CONTRACT
- ISOLATED INTEGRATION
- RUNTIME SMOKE
- LIVE E2E

每条测试结果只按实际执行证据汇报。

## 16.4 运行证据

记录真实测试环境的：

- 工作流二进制和 Worker 版本/摘要。
- PostgreSQL 版本、migration 状态和结果。
- Redis 双消费者、TTL、故障恢复结果。
- MCP Server/Client 实际 Transport 验收。
- 镜像 Digest / Release SHA。
- Task/Report/Artifact 实际 ID 与脱敏关联。
- 文件指纹校验。
- 真实小数据案例的数据来源和许可/访问状态。

不得包含密钥、私人文件或用户敏感数据。

---

# 17. 最终判定与 Phase 5 准入

最后必须回答：

1. Phase 4 哪些工作包已经真实完成？
2. 哪些功能只通过合成/Mock 或隔离测试？
3. P4-0 已闭合还是仍有 BLOCKED？
4. DatasetVersion→Task→Result→Report 是否真实贯通？
5. 科学报告和执行证据报告是否分别可查询？
6. 是否存在伪造历史版本/任务/来源的风险？
7. AI 助手和寻宝鼠能否在真实权限下只读查询？
8. Agent 写操作是否仍然关闭？为什么？
9. 本轮是否出现数据迁移/历史兼容风险？
10. 是否完成了至少一个真实小型公开科研案例的完整溯源交付？
11. 下一阶段最应先解决的三个未闭合问题是什么？
12. Phase 5 是否 READY / CONDITIONAL / BLOCKED？

**如果关键运行门禁仍被阻断，最终结论必须是 `CODE_IMPLEMENTED / RUNTIME_BLOCKED` 或对应准确状态；不得仅因为文档和测试通过就宣称生产可交付。**

---

# 18. Codex 最终启动指令

请先完整阅读本文件和 Phase 3 实施报告，核实当前仓库实际代码后开始执行 Phase 4。

- **先 P4-0，后 P4-A～G。**
- P4-0 未 READY 时，不开放下载、分析、报告发布等真实 Agent 写操作，不绕过源码门禁。
- 尽最大可能完成安全可执行的服务、契约、UI、合成测试与隔离验证，禁止仅交付设计文档。
- 复用现有 DatasetVersion / Frozen Handoff / TaskService / Result Manifest / FileRegistry / ReportService / BioReport / 快照系统。
- 对所有无法核实的历史或环境事实，明确保留 UNKNOWN。
- 保证报告失败不触发已经成功的生信计算重新执行。
- 所有外部数据和 Agent 工具调用都必须遵守身份、权限、项目和可信审批边界。
- 最后输出实施报告、契约、测试证据、G0–G18 矩阵、回滚 Runbook、Phase 5 准入结论。
- 不覆盖旧工作，不自动提交、推送或部署生产环境。

**终极验收问题：科研人员从某份报告出发，能否真实且安全地反向追溯到输入数据、采集来源、实际计算及完整性证据？**

实现后停止，等待用户验收与下一阶段指令。
