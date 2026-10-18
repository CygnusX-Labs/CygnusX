# RI09.5 项目综合科学报告设计

日期：2026-10-16。**正式项目报告为设计阶段**。附带已实现只读HTML原型，PASS_CODE/PASS_ISOLATED；不是已发布科学报告，没有正式Report/生成Job/PDF/FileRecord/ZIP新版本，没有真实渲染或浏览器验收。

## 定位和既有复用

Project Scientific Summary组织跨Dataset/Task的已有成果与证据缺口，不能把原RNA模板直接当作跨任务报告，更不能在渲染阶段隐藏联合分析。科学结果仍来自已有Scientific Report、ResultObservation、已核验ArtifactCell/Claim；实验设计、方法、参考文献缺失则NOT_RECORDED，研究意图须标为意图，不能据聊天/LLM补事实。

当前权威源码已核查：

| 能力 | 可复用路径 | 限制 |
|---|---|---|
| BioReportAdapter | 受控bioreport run -c -o、single布局、AI关闭、无平台凭据、已有HTML复用与依赖检查 | BioReportRenderRequest仍要求Task/Snapshot，不能伪造Task套项目 |
| scientific_report_job.render_counts | 固定仓库custom模块、复制核验输入、module_definitions和Quarto | Counts模板仅展示完成DESeq2输出，不适合直接跨项目/多Task |
| BioReport源码 | 本地../bioreport，pyproject 2.0.0、HEAD 2d5ea98；_quarto-single.yml.j2、主题及pdf/print-style.typ等可评审复用 | 是本地源码身份，不是运行Worker/生产镜像认证；旧报告的cb2911a/351e4654不能当当前部署版本 |
| 审计HTML renderer | 原表格/转义/CSP/样式，新增只读项目原型函数，共享CSS后旧审计HTML逐字节不变 | 原型不替代BioReport正式项目科学模板 |
| render_audit_pdf | 原受控Pandoc+Typst、冻结HTML输入、清洁env | 未运行正式项目PDF；失败必须保留HTML，不制造空PDF |
| ReportService/ReportFile/存储 | 版本、SHA、FileRegistry、私有发布与鉴权下载 | ReportModel.task_id及ReportGenerationJob.task_id非空，项目源需显式契约/迁移评审 |
| ProjectDeliveryManifest/Job | 既有冻结范围、digest、owner/project与保留关系 | 不修改已存在Job.manifest；不能每次报告读取扩展当前项目内容 |

本轮只读取本地BioReport模板和代码，没有修改旁仓、运行Quarto/BioReport、重做统计或渲染PDF。机器上的bioreport命令来自Conda Python入口，与平台/Worker版本是否一致仍未知。

## 冻结来源与报告元数据

正式报告优先引用现有ProjectExportJob ID及其immutable manifest_digest，复用已冻结项目事实引用，不复制全部Task、Dataset或Report数据。明确source_manifest_digest、owner/project、选择范围、redaction_policy、template_version、render_version、生成时间、实际HTML/PDF文件ID/SHA/大小、缺口及运行状态。

ProjectManifest v1未记录项目目标正文、全部Workflow方法、QC决策和通用科研结论；不得拿当前catalog或Task目录填回这些空白。需要新增事实时，对经过审核的选择生成新版本manifest或单独的冻结事实引用版本，原Job和摘要不变。只有跨版本长期索引/不可变保留确实不足时才评审ProjectReportSnapshot模型，本轮不建表。

Claim输入采用RI10已绑定的Task/Observation/File/SHA/行列值，逐一匹配冻结选择。自由文本解释分列AI_INTERPRETATION/NOT_VERIFIED，不混入VERIFIED_VALUE；SUPPORTED_CLAIM首版只承载有限数值陈述。跨表变换必须记录可复核transformation及版本，不在模板中自由计算新统计量或合并p值。

## 模板结构及来源

| 章节 | 来源和缺失策略 |
|---|---|
| 1 Project Overview | 冻结Project身份、范围；安全名称须预先采集，不能用任意当前字段补历史 |
| 2 Research Objectives | 明确选择的用户/ResearchPlan意图及版本，标注非事实；缺失留空 |
| 3 Dataset Inventory | 指定DatasetVersion/Handoff引用 |
| 4 Data Provenance | FileRecord/来源声明及核验状态，不自动补下载 |
| 5 Analysis Workflows | 冻结ExecutionDefinition/受信发布声明，缺环境标NOT_OBSERVED |
| 6 Execution Summary | 明确Task/Run/Observation及冻结状态水位，不能由文件时间推造步骤 |
| 7 Scientific Results | 已发布科学报告及已纳入范围的小型产物，原报告字节不改 |
| 8 Key Findings | 经上述身份/SHA核验的有限Claim；未核验解释分列 |
| 9 Quality Control | 原QC测量与明确规则/决策分别展示；QC文件存在不等于通过 |
| 10 Evidence Coverage | 缺失、未核验、排除与截断，非科学质量评分 |
| 11 Report Inventory | 各Report版本、Snapshot、EvidenceManifest及文件SHA |
| 12 Reproducibility Readiness | 依赖可得性及明确NOT_RUN；不能显示FULLY_REPRODUCIBLE |
| 13 Limitations | 缺少定义/历史环境/报告/原始数据等限制 |
| 14 Appendix | manifest摘要、文件清单、checksums与方法版本引用 |

正式BioReport首版应在原模块机制中增加受版本控制的项目模板与样式，继续使用Quarto/single布局和既有导出器，不另建引擎。输入仅受控JSON和复制的核验小文件，AI模块关闭，无任意Shell/模板路径、网络或凭据。RNA专属PDF封面/样式不能无审查直接套用，优先评审通用print样式与Pandoc/Typst转换。

## Job、权限及幂等设计（未实施）

报告生成是用户明确请求的独立操作，不能由项目ZIP收集或GET预览隐式调用。优先扩展现有ReportGenerationJob/Report的source kind为task/project：旧Task源默认语义保持；project源引用owner/project/manifest source job，Task为空，并有互斥CHECK/FK和owner范围约束。现有大量Task-first API/仓储/唯一键/下载须先审查和做独立迁移验证，**本轮没有进行该迁移**。

这比伪造分析Task更合理；若现有模型难以安全泛化，需先说明恢复/保留所需的最小独立项目报告Job职责，再评审，不能先做一套平行报告数据库。原ReportSnapshot保持Task源，不构造假的项目Task快照。

生成key应绑定owner+project+source_manifest_digest+template/redaction/render版本+format。复用原queued outbox、独占Worker锁、有限尝试、原子发布、回读SHA、FileRegistry和ReportFile登记；恢复始终使用原冻结输入，不重新采集新项目范围。HTML与PDF分别记实际可用性，PDF失败保留有效HTML与缺口，可只重试渲染，绝不重算分析。当前权限及模块在prepare/确认/生成/下载重复核验；Agent只能只读查询或准备建议，不能自批准。

## HTML/PDF与ZIP的非循环关联

报告引用已有source_manifest_digest M0，生成实际HTML/PDF及其SHA。用户随后选择这些已有制品，创建**新的**交付范围/Manifest M1及新ProjectExportJob；M1引用报告ID/文件SHA以及M0。报告自身不要同时内嵌包含其自身文件SHA的M1，避免摘要循环。

不覆盖旧ZIP/Job，不修改旧Manifest。项目导出Job只收集已生成制品，不调用BioReport或报告Job。PDF未产生时M1可partial，并且不创建空文件。在线下载复核当前权限，离线内容不含Token或需要登录的脚本；哈希校验不证明科学复现。

## 本轮只读原型范围

在原report_audit_renderer增加render_project_summary_prototype，复用原表格、转义、CSS和CSP。GET /projects/{id}/exports/{job}/summary-preview 验证当前权限、原导出开关、Frozen Manifest身份/摘要及关联后渲染，无新Job或持久化。X-Report-Status=prototype，no-store，明确PDF_NOT_GENERATED；前端在项目现有卡片的空sandbox iframe预览，不另建报告中心。

该HTTP入口不接受客户端Claim/数值，只显示冻结清单已有事实与缺口。纯renderer为未来接线提供可选Claim投影输入，但必须匹配同project/Task、Manifest实际包含FileRecord及其SHA、Observation；自由文本不被当成科学发现。API目前不自动枚举或生成Claim，因为现有ClaimService没有持久化的、经选择的项目结论列表。

原型显示14章的已有身份/文件/缺口，未知科学目标、方法、QC和结论明示NOT_RECORDED，不假装完成了跨任务科学总结。正式HTML/PDF、Report登记、生成失败恢复及ZIP版本整合仍是后续工作，不能用原型测试称完成。

## PR矩阵与下一阶段

| ID | 当前状态 |
|---|---|
| PR01/02 | PASS_ISOLATED：单Task及两个真实SQLite Dataset/Task引用的原型 |
| PR03/04 | PASS_ISOLATED：科学/证据/快照缺口原样显示 |
| PR05 | PASS_ISOLATED：原renderer只读HTML及ASGI、CSP/sandbox；正式发布BLOCKED |
| PR06 | PASS_ISOLATED：明确PDF_NOT_GENERATED；实际PDF渲染未实施/未认证 |
| PR07/08 | PASS_CODE/PASS_ISOLATED：prototype模板版本及真实冻结manifest_digest |
| PR09 | BLOCKED：正式项目报告Job尚未实施，不拿原型冒充恢复测试 |
| PR10 | PASS_ISOLATED：原型引用现有manifest且不改旧ZIP；正式M1整合待实施 |
| PR11/12 | PASS_ISOLATED：不调用分析/下载/渲染子进程，不接受范围外或未核验Claim，无虚构科研发现 |

后续顺序：先完成RA01–RA15真实环境与浏览器验收；再审核Project报告source契约及兼容迁移；固定项目BioReport模板/依赖与预算；实现独立JWT确认/报告Job/HTML；验证PDF失败保留HTML与恢复；最后以已生成制品建立新交付版本并跑真实下载/离线校验。保持RI10有限场景，RI11继续使用已有Gateway Profile；本轮不开放reproduction.execute。
