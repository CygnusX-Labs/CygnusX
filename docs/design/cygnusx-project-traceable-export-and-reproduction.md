# CygnusX 项目可追溯导出、报告溯源与归档分析复现实施说明

日期：2026-10-16。性质：实施提案与验收任务书，**不是 as-built，不代表功能已经完成或允许开启执行门禁**。适用现有项目管理、科研寻宝鼠、任务中心与报告中心。本文中的新增接口、模型、状态及配置均为建议，落地前应与代码契约核对。

## 1. 目标与范围

用户在项目页选择交付范围，预览缺口并生成一份可离线检查的项目交付包；在任一报告中能够追到实际输入、分析定义、参数、环境、人工决策、结果和生成版本；对于满足条件的已归档分析，用户发起预检、确认成本和范围后，创建新的受控任务，再取得原运行与新运行的比较报告。

三个能力分开交付：

1. **可追溯导出**：整理授权的既有事实与文件，不触发分析，也不因文件存在而认定实验可复现。
2. **报告追溯**：说明“这份报告依据哪些事实生成”，事实快照与报告文件都有固定身份及摘要。
3. **归档复现**：使用可核验的历史执行定义和输入启动新任务，并按预先约定的标准比较结果。

“一键”是统一入口，不省略必要的人类确认；导出批准不授权分析，整份研究计划批准也不替代具体执行批准。下载、重建环境和分析均不得由点击普通导出按钮顺带触发。

## 2. 当前实现与差距

以下结论来自当前工作区静态核对，不能代表线上镜像版本。

| 区域 | 已有能力 | 待补能力 |
|---|---|---|
| 项目历史运行 | ProjectOverviewService 扫描 runs；显示 AGENTS.md、README、environment 是否存在、文件数与体积 | 与实际 Task/版本/快照的可信关联、内容校验、项目聚合导出 |
| 单任务交付 | ReportService.build_delivery_package、ResearchDeliveryBuilder、EvidenceManifest、报告中心生成交付包与鉴权下载 | 真实环境验收；不能直接作为项目全量导出 |
| 报告证据 | 不可变 ReportSnapshot、摘要、独立报告 Job、科学报告/执行证据报告、完整性校验 | 更细的结论到表格单元/结果文件映射、完整执行时环境证据 |
| Dataset 交付链 | 受保护的 DatasetVersion/Handoff/Task/ResultObservation/Report 查询 | 开关和真实 Worker 验收，覆盖不同提交入口与历史缺失关联 |
| 分析提交 | AnalysisFlowToolService、TaskService、FlowFrame 验证与人工确认底座 | 安全保存并按历史版本执行、复现预检、新旧任务关系与比较 |
| 寻宝鼠 | 原卡片核验、Prepare、读取已有任务/报告关联 | 项目导出入口、复现入口及其状态投影 |

截图中的“历史分析运行”“科研计划与审阅”“科研执行与交付链”都是相关基础。文件存在标记不等于 SHA 校验通过；页面请求不可用不等于记录不存在，应分开显示未启用、无权限、请求失败和空记录。

现有 EvidenceManifest 绑定单个 task_id/snapshot_id，因此项目包应有独立的项目级聚合契约，引用既有单任务清单，不将多个任务强塞进旧字段。现有 execution_binding 中 workflow_release_digest 尚未提供可信历史发布证据；worker_paths_verified 也不能据此改成 true。

## 3. 必须复用与不可突破的边界

- 身份、项目权限与工具调用：现有 AgentToolGateway、MCPClient/ToolBridge；React Island 只传意图和受控引用，不携带 owner、JWT、服务器目录或可执行命令。
- 数据发现与导入：DatasetImportService、DownloadService；项目导出不启动下载，复现缺失输入需另行走下载准备与确认。
- 分析：AnalysisFlowToolService、TaskService、FlowFrame 与既有调度队列；不新增分析执行引擎，不让 Agent 写 Shell/流程 YAML/DB。
- 审批：ToolConfirmationService；审批绑定当前用户、规范化请求摘要、一次性凭证和过期时间，Worker 启动前再查事实。
- 报告：ReportService、已有快照/Job/文件登记/存储适配和报告中心。BioReport 只渲染完成结果，不判断科研正确性或授权执行。
- 路径：沿用 StoragePathFactory、file_protocol 和 FileRegistry，用户可见目录不使用裸 UUID；API 内可保留稳定对象 ID。
- 现有开关、源码级门禁、模块权限与镜像发布规则全部保留。没有真实验收不得解除 BLOCKED。

## 4. 项目一键可追溯导出

### 4.1 用户流程

项目页增加“导出可追溯交付包”：选择范围 → 服务端列出实际关联对象与缺口 → 用户确认 → 后台冻结清单与打包 → 下载并校验。寻宝鼠可跳转同一项目入口，不创建第二套导出界面和业务服务。

提供三种明确范围：

| 范围 | 默认内容 | 体积策略 |
|---|---|---|
| 证据包，默认 | 项目摘要、计划/审批的授权摘要、数据版本与来源、任务记录、报告、证据快照、清单、复现指南 | 不默认复制 FASTQ/BAM，不包含密钥、完整聊天/Prompt/敏感日志 |
| 结果包 | 证据包 + 用户勾选的已登记结果文件 | 预估体积，按配额与上限限制 |
| 复现材料包 | 结果包 + 允许导出的流程发布描述、环境锁、参考资源描述、输入引用 | 原始数据是否随包单独明确；受限资源只给授权引用，不夹带凭据 |

“引用已记录”和“文件已包含”必须分别列出。含外部引用的包不能宣称完全离线可复现。首次实现建议只支持 owner-only，协作者导出在有明确项目授权策略后单独验收。

### 4.2 内容组织示例

```text
项目名-交付-时间戳/
  README.md
  project-manifest.json
  checksums.sha256
  verification-guide.md
  project/project-summary.json
  research/plan-review-summary.json
  datasets/数据集名/版本名/{metadata.json,handoff.json,sources.json}
  executions/分析名-时间戳/{execution.json,execution-definition.json,environment.json}
  reports/分析名-时间戳/{scientific.html,evidence.html,ReportSnapshot.json}
  results/分析名-时间戳/用户选择的文件
  reproduction/{readiness.json,instructions.md}
```

仅写入实际存在且授权的内容；缺失 PDF、旧快照或环境证据记录在缺口列表，不生成伪装成真实产物的空文件。JSON 里的逻辑路径不能是服务器绝对路径。相同显示名称用服务端安全规则消歧。

### 4.3 项目清单最小字段

建议新增版本化 `cygnusx.project_delivery_manifest.v1`：package_id、project_id、scope、selection_digest、schema_version、冻结时间、来源水位、included/excluded 对象、每个 DatasetVersion/Handoff/Task/Run/Report/Snapshot 的引用与摘要、文件逻辑路径/大小/SHA-256/授权来源、缺口列表、包内容状态和验证器版本。

清单采用明确的规范化摘要规则；清单不把自身摘要递归纳入计算，checksums 文件也不自哈希。ZIP 文件自身 SHA-256 由包外的已鉴权下载元数据提供。摘要证明内容一致性，不能替代可信签名；如后续需要签名，应定义密钥轮换和验证策略，不能将普通 hash 标成数字签名。

并发期间不承诺跨数据库和文件系统的全局原子快照：先冻结选择与版本引用，再读取并核验具体字节；读取前后发生变化则拒绝该文件或标记明确缺口，不悄悄用新版本替换。最终产物先写 staging，完整校验后原子发布；对象存储使用版本引用/发布标记和可恢复登记策略。

### 4.4 作业、幂等与安全

后台导出 Job 与分析 Task 分离，建议状态 queued/collecting/validating/packaging/published/failed/cancelled，内容状态 complete/partial 与作业状态分开。采用现有 Celery 和持久化 Job 模式；大文件有界流式处理，不把项目文件全部读进内存。ResearchDeliveryBuilder 的既有 512MiB/2000 文件限制不能直接当全项目容量方案，应明确首版限制或新增受限流式适配。

请求键按 owner/project/selection_digest 绑定；重复请求复用同一冻结版本，不把新增文件混入旧包。取消不删除原数据，失败重试不重跑分析。下载每次复核当前权限和文件完整性；授权撤销后旧链接无效，已下载到用户本地的副本无法撤回，应在界面说明。

拒绝路径穿越、符号链接逃逸、任意 URL/本地路径注入、ZIP 重名覆盖、超配额和未授权引用；不要直接递归压缩项目根目录。外部源地址去除凭据，敏感字段采用字段级白名单。

## 5. 生成的报告如何追溯

### 5.1 核心证据链

```mermaid
flowchart LR
  S[公开来源与核验记录] --> D[DatasetVersion]
  D --> H[冻结 Handoff 与输入指纹]
  H --> A[规范化参数与人工审批]
  A --> T[实际 Task / 可选 Run]
  T --> E[执行定义与实际环境观察]
  E --> O[结果文件及 ResultObservation]
  O --> F[不可变 ReportSnapshot]
  F --> R[科学报告 / 执行证据报告]
  R --> P[项目交付清单与 ZIP]
```

历史缺少任一边时显示缺口，不按目录名、相近时间或报告标题自动认领关系。后来补录的证据注明采集时间与补录来源，不冒充当时自动采集的事实。

### 5.2 报告中的可见信息

每份报告固定展示 report_id、版本、生成时间、Task/Run、DatasetVersion、snapshot_id/digest、模板版本、BioReport/转换器版本、关联结果观察、证据覆盖与缺口。提供“查看证据链”“下载证据快照”“查看实际任务”“查看输入版本”。离线版本保留相同标识及文件对应关系，不能只依赖登录后的网页链接。

科学报告回答“得到什么结果”；执行证据报告回答“以哪些输入和操作得到，哪些证据缺失”。两者可以关联同一个冻结证据上下文，但不得将审计报告当作科学有效性认证。

对差异基因数量、QC 指标等关键结论，逐步增加可核验映射：claim_id → result_observation_id → file_record_id/SHA → 表格行键/列名 → 转换公式与版本。首版可定位到文件/表；无法定位到单元的结论必须写明追溯粒度。AI 解释标记为解释，记录其实际引用；没有实际保存的模型/提示词证据不补写。完整私密 Prompt 不默认导出。

### 5.3 修改、补证和状态

输入、分组或阈值变化创建新的 DatasetVersion/分析任务；补证生成新的快照/报告版本，不覆盖旧文件。仅更换排版模板也保留模板版本及原事实快照。报告渲染失败只重试报告 Job，不重新计算分析。

分别展示：计算状态、输入完整性、结果完整性、证据覆盖、报告生成状态、交付内容状态、复现验证状态。报告成功 ≠ 分析成功；SHA 一致 ≠ 科研正确；归档完整 ≠ 已复现。现有 not_run 必须在真实复现与比较完成前保留。

## 6. 已归档分析的一键复现

### 6.1 两种操作必须区分

| 操作 | 含义 | 页面名称 |
|---|---|---|
| 按历史定义复现 | 输入、参数、流程发布、参考库、环境和比较政策固定且可取得 | 复现原分析 |
| 使用当前流程重新分析 | 历史定义不可用或用户主动变更版本/参数 | 基于此分析新建任务 |

不能在历史镜像缺失时静默切当前镜像并标成复现。无法复现的旧目录仍可导出已有证据和结果，不能用当前环境文件补作历史快照。

### 6.2 最小可复现执行描述

建议新增不可变 `ExecutionDefinition`，与执行时观察记录分开：

- 原 Task、可选 Run、项目与 DatasetVersion，冻结 Handoff 摘要。
- 经规范化的分析参数、已确认样本设计、物种、比较组、参考版本、随机种子与线程等影响结果的设置。
- Flow catalog/schema 摘要、FlowFrame 协议与子流程 commit、实际发布包 SHA；仅有 commit 不足以覆盖未提交代码，需受信构建发布包和实际产物摘要。
- 受信镜像 digest、平台/架构、执行器及工具依赖锁，参考 FASTA/GTF/索引的版本和 SHA。
- 输入 FileRecord/对象版本、大小与内容摘要；运行时路径由服务端重新解析，不保存可直接执行的任意历史路径。
- 输出角色、关键表结构、预先批准的比较策略和容差。

保存描述不授予其执行权限。历史可执行代码只可来自受信流程发布仓库/登记表；用户上传 ZIP 中的脚本、Snakefile、YAML、命令不可直接执行。

### 6.3 预检到执行

1. 用户选择一个实际 Task 或已可信关联的归档运行，点击“复现预检”。仅有目录、无可信任务身份时先返回历史关联缺失。
2. 服务端复核当前用户/项目/模块权限、原记录关系与快照完整性。
3. 校验输入字节/对象版本、参考库、历史发布包、镜像 digest、CPU 架构与执行能力、存储/资源预算；缺失输入不得自动从网络补齐。
4. 输出 READY/BLOCKED/REQUIRES_NEW_ANALYSIS 及逐项依据和有效期。READY 仅指预检范围通过，不能表示复现成功。
5. 用户确认输入、参数、资源与预计成本；服务端以现有 Prepare/ToolConfirmationService 绑定规范化复现请求。
6. 执行前重检摘要、权限和预算；审批后内容变化则使凭证失效。通过 AnalysisFlowToolService 的渐进扩展复用统一 validator 和 TaskService，新建 Task、运行目录及审批记录。
7. 记录 reproduction_of_task_id、原快照/定义摘要、新审批与新任务；Worker 在计算前核验实际挂载、输入、镜像与发布包，不能只相信 web 预检。
8. 使用现有调度路径执行，生成新的产物/观察/报告。投递结果不明时对账，不自动重投导致重复计算。
9. 独立比较 Job 按预先冻结的策略比对，生成 comparison 报告，保留两次执行和产物。取消聊天不取消 Task。

首版推荐从已获运行认证的单一 RNAFlow 发布开始。Counts、ATAC、Studio、普通聊天沙箱分别验收；不能因为 RNA 通过就宣称所有归档均可一键复现。沙箱归档还原和声明式 Flow 重执行是不同适配器，未审查的历史 Shell 不可回放。

### 6.4 结果比较与宣称边界

| 等级 | 检查 | 可以声明 |
|---|---|---|
| L0 | 有来源引用、存在缺口 | 可追溯到记录，未复现 |
| L1 | 授权文件/快照 SHA 校验通过 | 归档完整性已核验 |
| L2 | 复现预检通过，尚未完成新任务 | 具备本次预检范围内的执行条件 |
| L3 | 新 Task 成功，关键输出结构和 QC 可检查 | 复现执行完成，尚需比较或比较不通过 |
| L4 | 预先定义的比较策略通过 | 指定范围的结果一致性已验证 |

比较策略分字节一致、表格语义一致和数值容差一致；记录排序、缺失值、浮点容差、关键指标、QC规则和排除项。时间戳/压缩头/HTML生成时间可能不同，不以此误判整个科学结果。也不能通过无限放宽容差掩盖差异；随机种子和软件版本不相同应先报告条件差异。某几项通过不能提升为全输出一致或科学结论必然正确。

## 7. 建议的最小增量设计

以下为待实现接口，非当前可调用事实；路径命名在接口评审时冻结。

| 用例 | 建议入口 | 约束 |
|---|---|---|
| 项目导出预览 | POST /projects/{id}/exports/prepare | 只读枚举，返回范围/缺口/估计体积，不创建分析 Task |
| 创建/查询导出 | POST /projects/{id}/exports；GET /projects/{id}/exports/{job_id} | 人类JWT、request_key、持久 Job、同项目校验 |
| 下载项目包 | GET /projects/{id}/exports/{job_id}/download | 当前权限复核、校验后下载、过期策略 |
| 复现预检 | POST /tasks/{id}/reproductions/prepare | 只读重检，返回定义摘要/预算/阻塞项 |
| 审批/受控执行 | 沿用或渐进扩展现有确认与分析服务 | 禁止“一次批准全部未来执行” |
| 查询复现关系/比较 | GET /tasks/{id}/reproductions | 返回真实任务/比较作业引用，不生成虚拟进度 |

建议新增 ProjectExportJob（项目范围、冻结选择、产物FileRecord、状态、摘要、错误）、ExecutionDefinition（受信发布和输入绑定）、ReproductionLink（新旧Task及定义/审批引用）、ComparisonJob/Result（策略版本与差异）。先核查现有 durable Job/RunPlan/ResearchPlan 模型能否复用，避免平行审批、重复 Task 或重复 Dataset；新增表必须带 Alembic 迁移、约束、索引、保留与删除策略。

历史 Run 可空，不能伪造 Run 关联；项目包包含多个 Task 时采用关系表/明确引用集合。导出包登记复用 FileRegistry 和存储适配；是否在报告中心增加项目级交付类型需确认现有 Report.task_id 约束，禁止塞入虚假的 Task。

## 8. 实施工作包与每包交付

| 包 | 实现范围 | 验收与回滚 |
|---|---|---|
| P0 基线与契约 | 逐入口核查任务归档/现有报告/权限；确定三类导出范围、状态和模型迁移 | 输出真实差距矩阵；仅文档无需运行回滚 |
| P1 单任务交付现场验收 | 复用现有打包器/API/UI，真实报告→ZIP→下载校验；验证PDF缺失partial | 未通过保留原下载路径，关闭新入口，不动原报告 |
| P2 项目聚合导出 | 预览、范围冻结、Job、清单、安全打包、项目页下载 | 多任务隔离/幂等/权限撤销/变更检测通过；关入口并停止新Job，保留已登记包 |
| P3 报告深度追溯 | 报告身份与版本、来源链、关键结论映射、历史缺口 | 随机挑结论追到具体结果文件；回滚投影，不改冻结快照 |
| P4 执行定义与复现预检 | 未来执行时采集、历史可用性检查、预算与版本差异展示 | 缺输入/镜像/参考时可靠BLOCKED；关闭预检入口不删除定义 |
| P5 RNA受控复现 | 新审批、新Task、Worker重检、实际状态追踪 | 原记录不变，重复点击不重复提交；关闭新提交，对在途Task按已有取消/恢复策略处理 |
| P6 结果比较与项目交付整合 | 比较政策、差异报告、新旧链路进入项目包 | 真实运行与差异样例通过；停新比较Job，保留结果与历史 |
| P7 扩域 | Counts/ATAC/Studio逐一适配和认证 | 每域独立证据；不继承RNA的READY |

每包输出：变更文件与契约、测试命令与日志、真实/隔离证据分类、通过/未通过项、运行门禁、回滚步骤。不得把源码测试通过写成真实科研E2E通过。

## 9. 测试与发布门禁

以下 EX/RP 编号用于本提案补充验收，**不替代**既有任务书 W0–W8、T01–T45、RG-01–RG-12；同类测试应复用原用例，新增覆盖映射写入验收报告。

| 编号 | 必测场景与预期 |
|---|---|
| EX01 | 多Task/多Dataset项目导出，选择范围准确，未选资源不夹带 |
| EX02 | 无数据/历史目录无法关联/缺科学或证据报告：明确partial或blocked，不伪造完整 |
| EX03 | 跨owner、撤权、伪造project/file/report引用：prepare、发布、下载全部拒绝 |
| EX04 | 路径穿越、符号链接、重名覆盖、超大小/数量：拒绝且无越界读写 |
| EX05 | 枚举后文件变化/消失、对象版本变化：检测漂移，不混合快照 |
| EX06 | 同request_key并发、任务重试、发布中断：一个可信版本，可恢复不重复分析 |
| EX07 | ZIP解压逐文件SHA与manifest一致，包外摘要可查；篡改拒绝 |
| EX08 | 项目切换/晚到响应/取消：不泄露旧项目结果，不误取消分析 |
| EX09 | 图表/关键结论→结果文件→实际Task→输入与定义可逐级核对 |
| EX10 | 模板更新/证据补录生成新版本，旧快照与文件保持可校验 |
| RP01 | 历史缺输入/镜像digest/流程发布/参考索引：blocked且有原因，不自动用当前版本 |
| RP02 | 不可信归档脚本、任意URL/路径和身份注入：拒绝执行 |
| RP03 | 批准后输入/参数/权限/预算变化：旧批准失效，Worker重检再次阻断 |
| RP04 | 并发执行/重复点击/投递不明：幂等对账，不重复Task和计算 |
| RP05 | 新Task/目录/输出/报告与旧Task关联正确，旧文件与批准不复用、不覆盖 |
| RP06 | 预先定义的字节/语义/数值比较：一致、真实差异、不可比较分别正确分类 |
| RP07 | 失败/取消/超时：独立状态、可解释缺口，报告失败不重跑分析 |
| RP08 | 当前流程重分析明确另标，不能获得“历史定义复现成功”状态 |
| LIVE01 | 真实PostgreSQL迁移/锁/并发、Redis/broker、Worker路径、对象存储和权限验收 |
| LIVE02 | 固定RNA发布与镜像、真实输入、实际执行证据、双报告、项目ZIP下载完整链路 |
| LIVE03 | 实际浏览器项目页/寻宝鼠/任务/报告互跳、导出下载、窄屏、键盘与错误恢复 |

发布顺序：静态契约/迁移检查 → 单元与隔离集成 → 授权环境真实组件 → 已批准小规模真实RNA → 下载校验与比较 → 逐门签署证据。既有RG门禁未通过时不打开相应写能力；新增能力不复用无关功能开关作为捷径。

## 10. 真实验收需要提供的环境与证据

需要独立授权测试数据库/队列、可用Worker、固定流程与镜像digest、允许分析的真实公开输入及资源预算、可访问参考库、BioReport渲染器和存储、浏览器。凭据通过既有安全配置注入，不写报告或日志。

首个RNA验收至少保存：原Task/输入指纹/发布与镜像/参考摘要、预检与批准记录、新Task、Worker实际观察、关键结果摘要、两份报告、比较报告、项目manifest和下载ZIP摘要。失败案例同时保留，不能只展示成功截图。

当前只能确认代码基础，尚无上述完整运行证据。建议实施顺序为 **先验收已有单任务交付，再做项目聚合导出与报告溯源，之后开放RNA复现预检和受控重执行**。这能尽早交付可用的导出，同时避免把证据不全的旧归档包装为可一键复现。

## 11. 当前参考与实现入口

现状依据（落地时需重新核对版本）：

- `ARCHITECTURE_DESIGN/CygnusX_report_architecture.md`：快照、单任务交付、权限与运行验收限制。
- `ARCHITECTURE_DESIGN/CygnusX_research_delivery_architecture.md`：Dataset到双报告链及受保护状态。
- `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md`、`CygnusX_flow_architecture.md`：冻结输入、分析准备与提交。
- `src/cygnusx/application/services/report_service.py::build_delivery_package`、`research_delivery_service.py::ResearchDeliveryBuilder`。
- `src/cygnusx/application/schemas/report_delivery.py`、`report_snapshot.py`：现有单任务契约。
- `src/cygnusx/application/services/research_execution_binding.py`：执行绑定与现存缺口。
- `frontend/src/views/ProjectDetailView.vue`、`components/ResearchDeliveryChain.vue`、`components/report/ReportPreviewModal.vue`。
- `docs/implementation/CygnusX_TreasureMouse_End_to_End_Implementation_2026-10-16.md`：既有工作包与门禁。
- `docs/audits/reproducible-report-phase2-implementation.md`：旧测试证据，仅作当时验证记录，不当作本轮实测。

本说明仅新增设计文档，不改业务代码、数据库、开关、子模块，不提交、推送或部署。
