# CygnusX BioOps · Phase 5 实施任务书

## 受控 Research Agent 编排、科研真实性校验与论文级 Benchmark

**英文主题：** Governed Research Agent Orchestration, Scientific Validation & Reproducibility Benchmarking  
**阶段：** Phase 5（P5-0 + P5-A ～ P5-G）  
**实施模式：** 证据核验 → 架构最小扩展 → 隔离实现 → 分层测试 → 有条件真实验证 → 实施与评估报告  
**当前前提：** 用户尚未提供 Phase 4 的实施报告。不得推定 Phase 4 已 READY。  
**安全原则：** 人类授权源于可信 UI/API；模型不能自证；所有有副作用的实际执行受后端门禁控制。

---

# 0. Role / 工作准则

你是一名资深 AI for Science 架构师、科研 Agent 工程师、生物信息学方法学专家、MCP/工具编排工程师、后端安全工程师与可复现计算科研评估负责人。

你正在为 **CygnusX BioOps** 实施 Phase 5，目标不是继续堆叠页面或通用聊天能力，而是在现有可追溯数据与计算基础上形成：

**科研目标 → 可审核 Research Plan → 受控工具与工作流编排 → 真实任务状态 → 科研证据 → 可复现交付 → 定量 Benchmark。**

本轮要求交付真实代码、可执行测试、数据/接口契约和评估报告；但不得在前置安全、运行或 Phase 4 交付门禁未完成时开放任何新 Agent 写能力。

## 0.1 必读依据（先确认存在，按现有实际路径读取）

1. Phase 4《科研证据链与可复现报告交付闭环》任务书 **及其实际实施报告（如果已生成）**。
2. `cygnusx-phase3-dataset-ingestion-handoff-implementation.md` 或仓库中的对应 Phase 3 实施报告。
3. Phase 0B、Phase 0B Closure、Phase 1、Phase 2 的实际实施记录与测试证据。
4. `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md` 及当前运行架构说明。
5. `docs/contracts/cygnusx-dataset-handoff-v1.md` 和结构化 schema（如果现存）。
6. DatasetVersion / Frozen Handoff / Task / Run / Artifact / Result Manifest / Report / Snapshot 的真实模型和服务。
7. 平台现有 AgentRuntimeGateway、MCPClient、ToolBridge、ToolConfirmationService、AnalysisFlowToolService。
8. `Protocol/FlowFrame/FlowAgent/` 中现存的规划与平台工具接口（如实际存在），避免重新造一个 Planner/Run Engine。
9. FlowFrame、CountsDEGFlow、RNAFlow 和 BioReport 的输入、产物与版本契约。

**注意：** 本列表不是已实现声明。缺失任何文件时先查找真实入口，找不到则记录 `NOT FOUND / BLOCKED`，不得虚构。

## 0.2 本轮前提边界

目前已知的 Phase 3 实施报告说明：

- 七类 Dataset 关联表、GEO 发现/导入预案、冻结 Handoff、CountsDEGFlow 和共享 Gateway 具有隔离实现。
- 部分统计计算已在本机合成数据上运行，但 PostgreSQL、Redis、Worker、外部 MCP 和真实完整 E2E 仍未验收。
- 真实 Agent 写操作仍保留源码/配置门禁；不能自行调开。
- Phase 4 任务书要求真实溯源链路验证，**目前用户尚未提供 Phase 4 的实施报告**。

请以**当前工作树与运行证据**核实最新状态；以上只作为调查基线。

---

# 1. Phase 5 目标、产物与非目标

## 1.1 核心目标

建立一个在可信人类监督下可执行多步骤科研计划的 Research Agent，并形成可复现的量化评估框架。

期望最终支持如下场景：

> 用户：帮我寻找适合研究病毒感染与肝脏基因表达变化的公开 RNA-seq 数据。优先包含可靠对照与生物学重复。找到后给出证据、分析计划、预期资源和风险；获得我的批准后，在项目内执行合适的流程，最后返回结果、可复现报告和证据来源。

理想的系统能力分为两层：

**规划层（默认可开发）：** 识别研究目标、核对可用数据、构造 Research Plan、检查依赖、给出数据和统计适用性缺口、提供任务预算与用户审批草案。

**执行层（严格门禁）：** 在安全条件和真实环境验收通过后，调用平台已存在的下载、分析、报告与状态查询接口，不直接操作任意服务器命令或绕过业务审批。

**评测层（可以先用隔离样例开发）：** 用结构化测试集证明或证伪任务完成度、证据质量、统计正确性、人工介入、时间/成本和可复现性。

## 1.2 阶段主要交付

- 类型化、可验证、可版本化的 `ResearchPlan` 与状态/事件协议。
- 使用现有 Task/Run/ToolBridge 的可恢复受控编排层（必要时最小扩展）。
- Dataset / Handoff / Flow / Report 兼容性预检查与人工审核卡片。
- 可引用真实 Evidence 的科研解释与不确定性表达。
- 最小可复现 Benchmark 框架、固定用例、Baselines 与统一指标计算器。
- 客观实验结果和失败案例登记；不虚构提升比例。
- 可检索的编排轨迹、任务恢复与项目证据关系。
- 完整实施报告、测试证据、验收 Gate 和 Phase 6 准入结论。

## 1.3 本轮明确不做

1. 不重写寻宝鼠 GEO/SRA/文献工具，不把它的 Node Runtime 全面改为 Python。
2. 不重做 Dataset、FileRecord、TaskService、ReportService、ToolConfirmationService。
3. 不新增第二套下载器、Snakemake 执行器或报告引擎。
4. 不允许 Agent 通过 shell、任意 URL、任意绝对路径或静态 Key 绕过工具白名单。
5. 不把已有 counts-only 方法包装为万能多组学分析。
6. 不自动判断全部生物学分组、物种、参考基因组或因果结论。
7. 不允许在没有实证依据时宣称平台达到自主科研、论文级 SOTA 或端到端生产可用。
8. 不强行依赖真实大型 GEO 下载，不自动公开敏感数据/报告。
9. 不为了提高 Benchmark 分数硬编码测试题答案或污染基线。
10. 不在前置门禁未通过的情况下开放 Agent 实际写权限。

---

# 2. P5-0：前置实施审计与准入 Gate

**P5-0 必须先于任何真实自动执行能力完成。**

## 2.1 核对 Phase 4 实际状态

检查：

- Phase 4 实施报告是否真实存在、是否具有代码和测试对应证据。
- DatasetVersion → Handoff → Task/Run → Result Manifest → Artifact → BioReport/证据报告是否可真实回溯。
- 报告成功与分析成功是否分开记录，报告失败是否禁止自动重跑分析。
- G0–G18 实际完成状态：哪些 PASS（隔离）、哪些 BLOCKED（真实）、哪些 FAIL。
- 真实小型公开科研数据端到端用例是否实际运行。

**如果 Phase 4 报告不存在，不能宣称 Phase 4 完成。** 可以在 P5-A、P5-C、P5-D、P5-E 的只读/合成部分继续实施，但 P5-B 的真实执行和 P5-G 的真实自动化 E2E 必须保持阻断。

## 2.2 核对 Phase 0B/2/3 长期阻断

逐项从运行证据核验：

- 真实隔离 PostgreSQL migrations/约束/并发。
- Redis 双进程确认 CAS、TTL、重启和故障恢复。
- MCP STDIO / HTTP 实际 Transport 的认证和合法调用。
- Treasure Mouse 镜像 Tag/SHA/Digest 与实际运行版本。
- Worker 的 EBIDownload/Polariseq 二进制、FlowFrame/RNAFlow/CountsFlow 来源、挂载和文件权限。
- 双用户两项目的完整鉴权与资源归属。
- 实际下载安全预算、重定向限制、文件类型校验。
- 幂等、任务状态恢复、部分成功与人工对账流程。

不能用 Mock 或配置静态检查替代上述真实证据。

## 2.3 工作区保护

最先执行并记录：

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
git submodule status --recursive
```

已有未提交改动不得覆盖，不做 `reset --hard`、`clean -fd`、整文件 checkout，也不擅自提交、推送、部署。

## 2.4 Phase 5 执行分级

- **PLAN_ONLY**：允许结构化规划、只读查询、人工审阅和合成测试。
- **ISOLATED_EXECUTION**：只允许临时目录、测试数据库/队列、模拟/小型合成数据。
- **CONTROLLED_LIVE_TEST**：前置 GATES READY、经明确资源/数据授权，仅在非生产环境执行小型真实公开科研案例。
- **PRODUCTION**：只有独立发布审批与全栈验收后才能启用，不由本轮代码自动解锁。

默认保持第一档，按证据逐级提升，禁止通过一项环境变量跳过全部检查。

**交付：** `docs/audits/cygnusx-phase5-entry-gates.md`，列出可复核证据、未闭合条件和本轮允许工作范围。

---

# 3. P5-A：Research Plan 契约、状态机与人工审阅

## 3.1 先复用平台已有计划/运行对象

调查：

- `RunModel`、Project Run、平台执行 plan、FlowAgent 的 plan/dry-run/submit 接口。
- 现有 Agent Tool Call、MCP 事件、Chat Session、Task idempotency、Report Snapshot。
- Phase 3 `DatasetAnalysisLink`、Phase 4 Evidence/Delivery 关联（如已实现）。

不允许仅为了统一命名增加一套与现有 Run/Task 冲突的关系模型。

如确实需要新的 `ResearchPlan` 存储，在设计说明中明确它与已有运行实体的边界：

- **ResearchPlan：** 人类可审查的研究意图与有向步骤。
- **Run/Task：** 已授权且真实开始的运行及计算事实。
- **Evidence/Artifact：** 有实际来源的可验证产物。

## 3.2 类型化研究计划

设计 Pydantic/JSON Schema DTO，建议最低字段：

```yaml
plan_version: '1.0'
plan_id: 'server-generated'
project_id: 'server-resolved'
status: DRAFT
research_question: '...'
assumptions: []
steps:
  - step_id: discover
    kind: DISCOVERY
    depends_on: []
    required_inputs: []
    expected_outputs: [discovery_proposal]
    approval_required: false
  - step_id: ingest
    kind: DATASET_IMPORT
    depends_on: [discover]
    expected_outputs: [dataset_version]
    approval_required: true
  - step_id: analyze
    kind: ANALYSIS_PREPARE
    depends_on: [ingest]
    expected_outputs: [analysis_proposal]
    approval_required: false
  - step_id: execute
    kind: ANALYSIS_EXECUTE
    depends_on: [analyze]
    expected_outputs: [task_id]
    approval_required: true
  - step_id: deliver
    kind: DELIVERY_PREPARE
    depends_on: [execute]
    expected_outputs: [delivery_proposal]
    approval_required: false
```

**示例只是目标契约草案，不是现存数据库/API。** 实际字段及状态必须与代码一致，不能允许模型填写可信身份、内部文件路径、执行 Token、批准状态或已经完成的真实 Task ID。

## 3.3 步骤种类与 DAG 规则

- 提供严格的 `StepKind` allowlist。
- 拒绝循环依赖、悬空依赖、重复 step_id、不匹配输入/输出以及超出最大步骤数的计划。
- `READ_ONLY`、`PREPARE`、`MUTATING`、`REPORT_PUBLISH` 分级。
- 每个步骤绑定工具契约、所需权限、预算、预条件、产物后置条件、失败处理策略。
- 研究计划可以引用 `DatasetVersion`、冻结 Handoff、Flow schema、Evidence，但不得凭自然语言建立新事实。
- DAG 生成后的服务端校验必须与具体工具、用户和项目资源再核对。

## 3.4 计划状态机

建议采用严格且可审计的状态集：

`DRAFT → VALIDATED → REVIEW_REQUIRED → APPROVED → RUNNING → {COMPLETED, PARTIAL, FAILED, CANCELLED, RECONCILIATION_REQUIRED}`

注意：并非所有计划都必须运行；只读研究计划可以结束为 `READY_FOR_REVIEW` 一类明确状态。

- 修改已审批步骤参数必须触发新计划版本和重新审批。
- 执行中的计划不能静默改变 DatasetVersion、Handoff、Flow、参考版本或预算。
- 编排状态与真实 Task 状态分开记录。
- 不得使用模型给出的 `status=COMPLETED` 代替真实 Worker 事实。
- 历史计划保留，不自动覆盖旧版本或实验记录。

## 3.5 Research Plan 用户审阅卡

前端最少展示：

- 研究问题、数据来源、Assumptions。
- 每一步目标、输入、产物、依赖关系及预计工具。
- 数据/统计适用性警告及来源证据。
- 计算时间/存储预算估计（如无法估计标未知，不捏造）。
- 哪些操作只读，哪些会下载、计算、覆盖、公开。
- 明确的每一类写动作的人类审批入口。

**P5-A 验收：** 两个 Agent 能基于同一项目资源生成遵守 Schema 的计划；跨用户引用拒绝；过期/变更计划不能使用旧批准记录。

---

# 4. P5-B：共享工具编排与可恢复执行

## 4.1 最小架构

推荐调用路径：

```text
Treasure Mouse / Platform AI Assistant
           ↓
Research Plan / Existing Agent Gateway
           ↓
Trusted Identity + Project Context
           ↓
Plan Validator + Human Approval
           ↓
Existing ToolBridge / MCP Client
           ↓
Existing DownloadService / AnalysisFlowToolService / TaskService / ReportService
           ↓
Task / Run / DatasetVersion / Artifact / Report
           ↓
Verified events → Plan State / Project UI
```

**不新造 Planner Runtime 的前提：** 先判断已有 FlowAgent/Run 或平台 Agent 执行器是否能承载计划状态。只有经过 ADR 证明不能复用，才新增薄协调服务。

## 4.2 两个 Agent，共享一个受控工具契约

- 寻宝鼠继续负责 Discovery、grounding、Next Shovel。
- AI 助手继续作为项目级交互入口。
- 两者使用相同的 ToolBridge/业务 Service/权限/DTO。
- 可开放工具先选 `research.plan.prepare`、`research.plan.validate`、`research.plan.get_status`、`research.plan.get_evidence` 等只读/prepare 能力（名称仅候选）。
- 真正 execute 只能通过已有可信审批系统和服务器端 gate，不允许 Agent 自行 `confirmed=true`。
- 模型输入包含外部 GEO 文本/文献摘要时，均按不可信数据处理，防止注入更高权限工具调用指令。

## 4.3 依赖驱动执行

编排器不能把完整研究目标直接翻译为任意 shell 命令。应：

1. 根据 ResearchPlan 判断 ready steps。
2. 用现有工具查询真实资产/工作流状态。
3. 做前置条件校验和权限核对。
4. 对需要审批的步骤创建独立待批准动作。
5. 在批准且前置 gate READY 时提交真实业务 Task。
6. 记录返回的 task_id 和对应版本/参数摘要。
7. 监听或轮询真实状态，异步推进下游步骤。
8. 对失败和不确定投递进入人工对账，而非自动重试昂贵副作用。
9. 只有真实 Result Manifest/Artifact/Report 满足后置条件，才能把对应步骤记为成功。

## 4.4 长任务与恢复

必须考虑浏览器关闭、SSE 中断、进程重启、Worker 重启、网络超时：

- 任务在服务器端持久运行，对话断连不视为任务取消。
- PlanStep / Task / ToolInvocation 有稳定关联。
- 状态查询默认按可信 owner/project 过滤。
- 使用现有幂等 Key 和服务端原子状态转换。
- 检测同一请求重复提交。
- 对 `SUBMITTING`、队列未知、部分文件存在等情况实行 reconcile-only；无法判定是否已执行不得自动重放。
- 不自行补造已经丢失的日志、输入指纹或执行环境版本。
- 下载失败、分析失败、报告失败使用不同恢复策略；报告重试不触发分析重跑。

## 4.5 风险与预算

- 只读工具一般不需用户二次确认，但仍受速率与权限限制。
- 下载前复查存储预算、数据源、目标项目、文件大小和合法访问状态。
- 分析前复查 Flow 输入类型、样本/对照、参考、Worker 可访问路径、资源上限。
- 每个 mutating step 都需要可信确认和服务端审计。
- 一次性批准不得当成无界自动批准未来任何任务。
- 用户可暂停后续调度而不破坏已经完成的计算。

**P5-B 验收：** 同一研究计划可以从已完成步骤继续，跨用户、审批篡改、重复提交不能产生额外执行；真实运行必须满足 P5-0 Gate。

---

# 5. P5-C：科学语义校验与证据支持的科研解释

## 5.1 不让 Agent 以自然语言替代统计判断

计划与执行前应检查：

- 物种/组织/疾病或处理条件是否有真实来源。
- 样本分组、对照、生物学重复、配对关系是否明确。
- FASTQ、原始整数 counts、TPM/FPKM/CPM、Series Matrix、单细胞矩阵等输入类型是否明确。
- 不把标准化矩阵交给 DESeq2，不把 counts 文件交给 FASTQ 分析入口。
- 生物学研究设计是否存在混杂、重复不足、缺失 metadata 或参考不匹配。
- 不支持的组学/流程应返回 `UNSUPPORTED`，而非猜测一个看似合理的分析链。

## 5.2 Evidence-grounded Claim

定义科研结论最低证据结构（建议通过现有 Evidence DTO 扩展）：

- claim_id、claim_text。
- claim_type：`DATASET_FACT` / `COMPUTATIONAL_RESULT` / `LITERATURE_CONTEXT` / `HYPOTHESIS`。
- evidence_refs：Source / DatasetVersion / ResultManifest / Figure / Article 等既有稳定引用。
- provenance_status：`VERIFIED` / `PARTIAL` / `UNVERIFIED` / `CONTRADICTORY` / `UNKNOWN`。
- limitations、alternative_explanations。

不要假装普通数据库关联等于支持因果或机制结论。

## 5.3 报告解释与拒绝机制

- 能区分数据集原始元数据、作者陈述和平台重新计算的统计结果。
- 任何 DEG/GSEA 等数值应引用真实 Artifact 的具体表、参数、比较组，而不是由模型生成数字。
- 对无证据、分组不明、样本不匹配、工作流不支持的请求给出具体缺口与需要用户提供的信息。
- 文献摘要属于外部材料，不能指挥 Agent 执行管理工具。
- 不生成虚构的 GSE 编号、p 值、软件版本、样本数量或论文引用。

## 5.4 最小科研可信性测试

至少覆盖：

1. 原始 counts + 完整 metadata 可准备 counts-only DEG。
2. TPM/FPKM 或 log 值不进入 counts-only DEG。
3. 未明确处理方法的整数样式数据保持 REVIEW_REQUIRED。
4. FASTQ 丢失配对/物种信息需用户补充。
5. 组内无重复或设计混杂给出明确阻断。
6. 统计结果解释只引用真实产物数值。
7. 来源和统计结果冲突时不隐去冲突。
8. 对无证据的生物学机制结论只标 HYPOTHESIS 或拒绝事实化。

---

# 6. P5-D：Benchmark 设计、基线与可复现评估数据集

## 6.1 Benchmark 的目的

量化是否真正解决科研数据发现、跨模块执行与证据交付的痛点，而不是证明系统“看起来能工作”。

至少测：

- 能否找对数据并给出可追溯来源。
- 能否选择正确数据类型与合法分析方法。
- 能否在授权范围内完成科研计划。
- 能否从报告回到真实数据/参数/版本/产物。
- Agent 引入后是否减少人工动作和时间，是否增加计算或失败成本。
- 发生失效时能否安全拒绝、提示和恢复。

## 6.2 基准集合设计

建立 versioned benchmark manifest（例如 `benchmarks/research_agent/v1/`）。最小首版建议不少于 **12 个经人工审核的任务**，按三类均衡：

- 4 个发现与元数据/证据判断任务。
- 4 个数据资产与 Flow 匹配/规划任务。
- 4 个边界与失败/安全恢复任务。

**这是测试规模建议，不代表当前仓库已拥有这些样本。** 如无法审定 12 个可重复任务，应如实说明数量不足，保留未通过标准。

随后在 Gate READY 后追加**至少两个小型公开、授权可用、可复核的真实计算案例**（例如一个 raw counts、一个 FASTQ），不得为了数量采用大规模或敏感数据。

每例记录：

- case_id、版本、难度、研究问题、预期输入。
- 公共来源与许可证/访问情况。
- 已知结果、可接受结果范围与审核者。
- gold evidence 或可信核验过程。
- 正确工具与错误输入的判别点。
- 是否允许联网、计算、下载及预算。
- 失败期望、拒绝标准。
- 结果评分说明与争议仲裁记录。

## 6.3 公平基线设计

至少定义三个配置：

**Baseline A：传统手动流程**  
在相同数据、任务、硬件和时间预算下，由熟悉工作流的研究人员操作平台已有 UI/CLI；记录人工步骤与错误，不预设总是最慢。

**Baseline B：通用/现有 AI 助手，不使用新 Research Plan 编排**  
使用相同模型或明确披露模型差异、相同工具权限、相同预算和相同任务集合。若无法建立公平工具权限，声明为非严格比较。

**Candidate C：Phase 5 Research Agent + 统一受控工具 + Evidence/Handoff**  
记录额外的审批、计划与审计成本，不能只计算模型响应时间。

可选消融：

- C without provenance checking。
- C without plan validator。
- C without tool orchestration（仅 prepare）。
- C without evidence-grounded explanation。

安全机制不得在可触发真实操作的实验中为了消融而关闭；只能在隔离、Mock 或只读评测中模拟没有对应能力的状态。

## 6.4 数据与结果封存

- 固定 benchmark_version、case_version、评测脚本 commit SHA、Model ID/版本、提示词模板哈希、工具 schema、数据文件 checksum。
- 固定随机种子（适用时），记录温度、工具超时、最大步骤数、最大重试次数。
- 明确网络是否开启、缓存是否启用、失败重试如何计费。
- 不将 test cases 直接加入被评测 Agent 的开发提示词、检索语料或人工提示中。
- 记录每次运行的结构化 trace，区分模型输出和真实系统事件。
- 对时间、成本和性能测量做环境说明；宿主机结果不能当成 Worker 结果。

---

# 7. P5-E：指标体系、统计分析与论文实验框架

## 7.1 指标及分母必须预定义

定义一个统一评估计算器，至少包括：

| 指标 | 计算定义建议 | 关键注意事项 |
|---|---|---|
| Task Success Rate | 完成所有强制目标的任务数 / 可评任务总数 | 不将只生成计划算成完成下载/分析 |
| Valid Plan Rate | 通过结构与业务验证的计划数 / 生成计划数 | 区分模型语法与科学适用性 |
| Data Discovery Accuracy | 正确数据集选择数 / 有审定 ground truth 的发现题数 | 记录候选数、可接受答案集合 |
| Workflow Matching Accuracy | 正确工作流选择数 / 有核验输入的匹配题数 | 区分 raw counts 和 TPM 等 |
| Evidence Coverage | 有有效证据的必需结论数 / 必需结论数 | 证据存在不等于结论正确 |
| Unsupported Claim Rate | 无可靠依据却事实化输出的结论数 / 可评事实断言数 | 需要人工复核与争议处理 |
| Provenance Completeness | 实际可追溯的必需证据边数 / 必需边数 | UNKNOWN 不能算 COMPLETE |
| Reproduction Success | 独立重放且在预设容差内匹配的案例数 / 尝试重放的案例数 | 标注环境、容差、不可重放原因 |
| Human Interventions | 每个案例实际人工审阅/配置/纠错次数 | 审批也是人工动作，不能排除 |
| End-to-end Time | 从任务开始至真实交付结束的耗时 | 区分用户等待、队列、计算和报告 |
| Cost | 模型 Token/API 费用、存储、计算资源消耗 | 无价格证据不得捏造金额 |
| Safety Violation Rate | 未经授权的有副作用成功操作数 / 攻击尝试数 | 任何成功越权需单独报告、阻断发布 |
| Recovery Success Rate | 在指定故障条件下恢复到安全一致状态的用例数 / 故障用例数 | 不允许为成功率盲目重投 |

可以增加准确率/召回率、Tool-call Efficiency、用户负担，但必须写清计算分母和失败样本是否纳入。

## 7.2 统计评估与不确定性

- 原始逐任务结果必须保留，汇总不能遮蔽失败案例。
- 对比例类指标报告分子/分母及合理的置信区间（有可比重复时）。
- 对时间/成本报告中位数和分布，避免只报最佳一次。
- 若同一题在多个系统上重复执行，使用成对比较设计。
- 避免把小样本的随机波动描述为显著优势。
- 预先确定主要终点和次要终点，尽量减少事后挑选指标。
- 不对不兼容硬件/网络的测量直接做因果解释。

## 7.3 论文实验材料导出

可生成：

- `benchmark_results.csv`：逐案例、逐重复的原始测量。
- `benchmark_summary.json`：指标与分母、失败原因、环境。
- `analysis_notebook.qmd` / `analysis.py`：可重复计算统计与作图。
- `evaluation_protocol.md`：题目来源、审核、方法与限制。
- `case_studies/`：经审核的公开案例、不含敏感凭据。
- `failure_catalog.md`：所有错误类型及治理建议。

**没有实际测量时，不得输出虚构的提升百分比、显著性 p 值或论文结论。**

---

# 8. P5-F：科研 Agent 工作台、轨迹与人类监督体验

## 8.1 前端设计

复用 CygnusX UI 组件体系，不重做整个平台。建议在 AI 助手/寻宝鼠项目界面提供：

- Research Plan 步骤视图与依赖关系。
- 可展开的工具调用、参数摘要、数据来源、证据链接。
- 每个节点 `WAITING_INPUT`、`WAITING_APPROVAL`、`QUEUED`、`RUNNING`、`PARTIAL`、`FAILED`、`COMPLETE` 等真实状态。
- 每个需要写入的步骤独立审批卡片。
- 任务状态、日志、Result Manifest、科学报告、执行证据报告入口。
- 失败解释、人工补全配置、从持久状态恢复会话。
- 一键查看计划版本、实际执行版本、数据/计算指纹。

如某步骤只有计划，没有提交真实 Task，UI 明确显示“仅规划，尚未执行”。

## 8.2 多页面连续性

- 用户从寻宝鼠切换到分析中心或项目任务中心，应通过真实 project/plan/task IDs 恢复上下文。
- 禁止依赖前端临时状态或对话文本猜测任务归属。
- 项目切换后旧项目的迟到 SSE/网络结果不能写入新项目 UI。
- 任务被其他用户猜测 ID 后不可读取。
- 客户端关闭后，真正运行中的 Task 保持独立生命周期。

## 8.3 观测与审计

尽量复用现有 event/request/task log。记录脱敏字段：

`plan_id / plan_version / project_id / trusted user_id / step_id / tool_invocation_id / task_id / dataset_version_id / run_id / result_manifest_id / report_id / trace_status / error_code`。

- 不记录 JWT、API Key、确认 Token 原文或敏感文件内容。
- 审计日志可区分模型建议、用户批准、服务验证、真实执行、交付完成。
- 历史运行缺失信息必须标 UNKNOWN，不得重建为“已核验”。

---

# 9. P5-G：端到端科研案例与故障注入验证

## 9.1 分层评估策略

**Layer 1 — Static / Contract:** ResearchPlan Schema、Gateway DTO、权限、Flow compatibility、指标脚本。

**Layer 2 — Isolated / Synthetic:** 隔离 DB/队列、虚拟时间、合成 raw counts/小 FASTQ、模拟 MCP 工具，无真实网络写任务。

**Layer 3 — Controlled Live:** 只有 P5-0 和 Phase 4 的运行 Gate READY，且获得明确案例数据、存储、计算及费用预算批准后，在非生产环境执行小型真实公开数据。

**Layer 4 — Release Acceptance:** 独立发布准入；不是本轮代码测试默认结论。

## 9.2 建议的两个真实科研案例

### 案例一：公开原始 counts → CountsDEGFlow → 双报告

- 选择有权威原始整数 counts 来源、清楚 metadata 与分组的公开 GSE。
- 记录独立来源与文件 SHA-256。
- 明确人工审核样本分组、统计设计与比较方向。
- 通过 Frozen Handoff、批准后执行 `CountsDEGFlow`。
- 比对真实结果清单、表格、图和报告的源 ID 与哈希。
- 在受控环境中复现并比较预设容差内的结果。
- 记录所有人工介入与工具使用成本。

### 案例二：小型公开 FASTQ → RNAFlow → 双报告

- 先验证小数据真实可获取、访问许可、预算与存储空间。
- GSE→权威关联 SRR，核对配对、样本名、物种、参考与文库信息。
- 用户批准下载、分析与必要的交付操作。
- 观察真实 Worker、输入/输出校验、Flow 版本和任务状态。
- 验证报告反向追溯真实输入、参数与运行事实。

真实案例 ID 必须由开发人员从公开源核验选择，不得在代码中凭空指定一个“看起来合适”的 GSE。

## 9.3 故障/安全用例

- 未授权跨用户调用工具。
- 旧审批重放、篡改 Data Handoff/Flow 参数。
- Redis 不可用 / CAS 双消费者冲突。
- MCP Transport 中断与失效身份。
- 两次请求同一 plan/task idempotency_key。
- 下载部分完成且 FileRecord 缺失。
- Task 排队后用户断开会话。
- 计算已经成功但 Result Manifest 缺失/校验失败。
- 报告生成失败后仅重试报告而不重跑昂贵计算。
- Worker 挂载缺失、参考资源不可用。
- 外部检索内容夹带“忽略审批”等提示注入指令。
- 真实科研输入标为 UNKNOWN 时不得继续错误统计流程。

按预期失败/安全拒绝判为 PASS，不以所有操作完成作为唯一成功标准。

---

# 10. 实施工作包交付与代码边界

## P5-0：准入审计

交付：Gate 报告、真实部署阻断与 Phase 4 状态核验。无法验收时只读开发继续，但写操作仍禁。

## P5-A：研究计划与状态机

交付：类型化契约、验证器、计划版本/状态存储的最小必要实现、前端审阅卡、测试。

## P5-B：安全编排

交付：对接已存在 MCP/ToolBridge/TaskService 的薄协调器；长任务状态、审批、幂等与恢复契约。

**前置不满足时，只做隔离运行和只读/prepare，禁止开放真实 Agent 调度执行。**

## P5-C：科学语义与证据

交付：研究计划科研适用性检查、证据支持的结果解释 DTO、正确拒绝与不确定性测试。

## P5-D：Benchmark Registry

交付：版本化 case manifest、gold evidence 审阅、baseline runners、配置与防泄漏策略。

## P5-E：Benchmark Metrics

交付：可重复评估脚本、逐例结果、汇总、统计检查与可信失败报告。

## P5-F：产品体验

交付：计划/审批/状态/证据/报告的跨页面 UI、审计与会话恢复。

## P5-G：E2E 验收

交付：合成/隔离/有条件真实案例及失败场景，完整基线比较与复现证据。

---

# 11. 自动化测试矩阵（T01–T40）

| ID | 测试 | 最低层级 |
|---|---|---|
| T01 | Plan schema 正确序列化/反序列化与版本验证 | Unit |
| T02 | DAG 循环/重复/悬空依赖拒绝 | Unit |
| T03 | 非法 StepKind 与工具白名单拒绝 | Unit |
| T04 | owner/project 可信上下文而非模型字段 | Integration |
| T05 | 跨用户 DatasetVersion/Task 引用拒绝 | Integration |
| T06 | 修改 plan 后旧审批失效 | Integration |
| T07 | 一个读步骤无需危险写审批 | Contract |
| T08 | 写步骤无审批/布尔自证拒绝 | Integration |
| T09 | 参数摘要变化拒绝 | Integration |
| T10 | 未满足上游依赖不得调度 | Unit |
| T11 | 同步等待不会阻塞真实异步任务 | Integration |
| T12 | 重复调度仅创建一次授权业务 Task | Integration |
| T13 | SUBMITTING 不明状态不自动重投 | Integration |
| T14 | SSE 中断后只凭真实 ID 恢复 | Integration |
| T15 | 项目切换时迟到响应被丢弃 | Frontend |
| T16 | 取消计划不删除已完成资产 | Integration |
| T17 | 真实 Result Manifest 缺失不能 COMPLETE | Integration |
| T18 | 报告失败不会触发重跑分析 | Integration |
| T19 | FASTQ 与 counts 工作流匹配正确 | Unit |
| T20 | TPM/FPKM/Series Matrix 不进入 DESeq2 | Unit |
| T21 | 未核验来源的整数矩阵要求审阅 | Unit |
| T22 | 元数据/分组/配对不完整阻断 | Unit |
| T23 | Evidence 引用丢失不声称 VERIFIED | Unit |
| T24 | 有冲突证据时标示矛盾 | Unit |
| T25 | 真实统计数值必须来自 Artifact | Contract |
| T26 | 外部文献/检索提示注入不得执行写工具 | Integration |
| T27 | Benchmark case manifest schema 与固定版本 | Unit |
| T28 | Benchmark gold evidence 审核记录完整 | Contract |
| T29 | Benchmark 不含明文 token/敏感个人数据 | Contract |
| T30 | Metrics 分母、部分成功、UNKNOWN 处理正确 | Unit |
| T31 | 对重复案例运行不会覆盖原始结果 | Unit |
| T32 | Benchmark Baselines 同权限/预算或显式差异 | Contract |
| T33 | Evidence coverage 只计有效来源 | Unit |
| T34 | Reproduction score 使用预设比较规则 | Unit |
| T35 | 安全越权负例执行端无副作用 | Integration |
| T36 | 两进程 Redis 确认竞态 | Runtime（门禁） |
| T37 | 真 MCP Transport token、初始化、调用 | Runtime（门禁） |
| T38 | 实际 Worker 版本/路径/校验可追溯 | Runtime（门禁） |
| T39 | 真实小型 counts/FASTQ 至双报告闭环 | Live isolated E2E（门禁） |
| T40 | 固定 benchmark 可重复出逐例指标、失败清单 | Integration |

测试必须标识 `PASS / FAIL / BLOCKED / SKIPPED / NOT TESTED`，及证据层级 `Unit / Contract / Integration / Runtime Smoke / E2E`。不得将 mocks 冒充真实网络、真实用户或生产环境。

---

# 12. Phase 5 验收门禁（G0–G18）

| Gate | 条件 | 对真实自动执行影响 |
|---|---|---|
| G0 | Phase 4 实施证据与前置运行 Gate 真实核验 | 必需 |
| G1 | 工作树基线与全部改动归属清楚 | 发布前必需 |
| G2 | ResearchPlan Schema/版本/依赖验证稳定 | 必需 |
| G3 | 两种 Agent 使用相同的可信规划/工具契约 | 必需 |
| G4 | 身份/Project/Dataset/Task 资源隔离有效 | 必需 |
| G5 | 人工审批不可模型自证、重放、跨 owner 使用 | 必需 |
| G6 | 编排不绕过已有 TaskService / DownloadService | 必需 |
| G7 | 异步状态、幂等、恢复/对账不重复副作用 | 必需 |
| G8 | 统计/输入类型与研究设计匹配 | 必需 |
| G9 | 科学结论绑定真实 Evidence 并保留缺口 | 必需 |
| G10 | Benchmark task/gold/baseline 版本化且无泄漏 | 评测发布必需 |
| G11 | Benchmark 指标、分母、原始 trace 可复算 | 评测发布必需 |
| G12 | 至少 12 个审定初始基准任务（或如实不足） | 首版目标 |
| G13 | 前端计划/审批/任务/证据交互正确 | 产品交付必需 |
| G14 | 故障和提示注入负例无未经授权副作用 | 必需 |
| G15 | Redis/MCP/PG/Worker 的真实运行链有证据 | 真实执行必需 |
| G16 | 至少两个小型真实公开案例有可复核数据与证据 | live E2E 宣称必需 |
| G17 | 回归测试、文档、审计、回滚 Runbook 完整 | 交付前必需 |
| G18 | 实施报告明确准入状态与论文结论限制 | 交付前必需 |

不得出现“G15/G16 仍阻断，但 Phase 5 已生产 READY”的结论。允许分别给出 `CODE_IMPLEMENTED`、`ISOLATED_VALIDATED`、`CONTROLLED_LIVE_VALIDATED`、`RELEASE_READY`；必须明确证据层级。

---

# 13. 回归、性能与安全要求

## 13.1 回归范围

确保不影响：

- 寻宝鼠只读 GEO/文献检索、Next Shovel。
- AI 助手已有工具、审批、任务查询。
- Dataset 版本与冻结 Handoff。
- DownloadService、TaskService、FlowSchema、RNAFlow、CountsDEGFlow。
- Result Manifest、BioReport、执行证据快照。
- 项目会话、文件、任务与权限隔离。

全量检查有既有失败时报告基线/本轮归属，不能偷改无关代码凑全绿。

## 13.2 性能与可靠性

- 规划步骤数、Tool Call 次数、模型 Token、时间与外部检索并发设上限。
- Agent 不得无限自主重试或循环调用。
- 无效研究计划校验不得创建真实下载/计算任务。
- 任何昂贵或有外部影响的操作应经用户明确批准。
- 控制日志大小与个人敏感信息暴露。

## 13.3 测试环境

优先隔离 PostgreSQL / Redis / Worker / MCP / MinIO/存储模拟；不可访问真实网络时通过 fixture 或本地小数据进行确定性验证。生产实例不得被当成免费测试环境。

---

# 14. 交付文件与推荐位置

尽量遵守仓库已有约定，可根据实际目录调整：

1. **实施报告：** `docs/implementation/cygnusx-phase5-research-agent-benchmark-implementation.md`。
2. **准入核验：** `docs/audits/cygnusx-phase5-entry-gates.md`。
3. **Research Plan 契约：** `docs/contracts/cygnusx-research-plan-v1.md` 和配套 JSON Schema。
4. **ADR：** `docs/adr/phase5-governed-research-agent-orchestration.md`。
5. **Benchmark 协议：** `benchmarks/research_agent/v1/evaluation_protocol.md`。
6. **Benchmark 数据：** `benchmarks/research_agent/v1/cases/` 与校验记录。
7. **Benchmark 运行工具：** 优先复用现有 CLI/pytest/脚本体系，按实际目录组织。
8. **评估输出：** `benchmark_results.csv`、`benchmark_summary.json` 和错误分析（只有实际测试才写结果）。
9. **测试与证据：** `tests/` 与 `evidence/phase5/`（如后者不纳入版本控制，报告说明保存位置）。
10. **变更索引和回滚：** 列出文件级修改、迁移、Feature Flag 与恢复方法。

若涉及数据库新增字段，先核实已有 Plan/Run/Task 能否复用；迁移必须在隔离 PostgreSQL 真正演练，保留既有数据，不能因 SQLite 通过就宣称 PG 已验收。

---

# 15. 最终实施报告格式

报告至少包含：

1. Executive Summary、Phase 5 实际结论。
2. Baseline/Branch/HEAD/Dirty Worktree。
3. Phase 4 与历史 Gate 核验（真实证据或 BLOCKED）。
4. ResearchPlan / Agent 编排 ADR 与复用关系。
5. 计划 DTO、状态机、审批与工具契约。
6. 科研语义校验及 Evidence-grounded Claims。
7. Benchmark Case 构建与审定、任务难度、真实许可/访问状态。
8. Baselines、模型/工具配置、运行成本与公平性。
9. 指标计算公式、逐例结果、分母与不确定性。
10. 测试命令、PASS/FAIL/BLOCKED/SKIPPED/NOT TESTED 与环境层级。
11. P5-A～G 工作包执行状态及修改文件索引。
12. G0～G18 门禁和剩余阻断。
13. 安全风险、数据泄漏与越权负例结果。
14. 实际科研案例及其输入→执行→报告完整证据（如真实运行）。
15. 可复现研究评测包与论文可陈述/不可陈述的结论边界。
16. 回滚策略及 Phase 6 准入建议。

**任何基于合成或 Mock 的运行结果都要在标题和图表中显式标记；不得用它们宣称已证实生产效益。**

---

# 16. 完整 Codex 启动指令

请先完整阅读本 Phase 5 文件，以及 Phase 3 实施报告、Phase 4 任务书与 Phase 4 实际实施结果（如果有）。

**第一步必须完成 P5-0：** 检查真正的 Phase 4 验收证据、0B/2/3 的长尾阻断和所有写操作 Gate。没有相应报告或运行证据时，标 `BLOCKED`，绝不能自行断言已解决。

按 P5-A～P5-G 实施能安全实施的代码和评估基础设施：

- 先复用已有 Run/FlowAgent/Agent Gateway/ToolBridge/TaskService，定义 ResearchPlan 与最小有状态编排能力。
- 保留寻宝鼠、AI 助手现有 Runtime，仅通过可信项目上下文共用业务工具。
- 建立 plan DAG、真实执行事件映射、人类审批、长任务恢复与幂等/对账。
- 构建科研输入适用性验证、Evidence-grounded Claim 及科学不确定性处理。
- 创建版本化 Benchmark cases、Baseline runners、统一指标与原始评测结果记录。
- 添加 Agent 计划与执行轨迹 UI，并维护原有项目/任务/报告体验。
- 通过隔离测试、必要的负例与合成研究案例验证，不伪造真实科学执行。
- 只有在安全运行 Gate READY、非生产环境与数据/计算预算获明确授权后，才进行小型真实公开科研案例的受控执行。

不修改无关子仓与算法，不覆盖未提交成果，不擅自提交、推送或生产部署，不以单个环境变量解除安全阻断。

最终交付代码、测试、契约、Benchmark、实施报告、原始证据、G0～G18 验收矩阵、回滚说明与 Phase 6 准入判断。

**最终验收问题：CygnusX 能否以可审核、可授权、可恢复的研究计划，将科学问题转化为真实计算和可追溯交付，并提供可重复的证据衡量它是否优于既有工作方式？**

完成后停止，等待人工验收与后续指令。
