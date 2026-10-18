# RI10 科研结论证据追溯：设计与最小增量

日期：2026-10-16。状态PASS_CODE/PASS_ISOLATED，真实数据/部署/浏览器BLOCKED。实现限定已有DEG TSV单元格；不宣称通用科学结论、文献真实性、统计设计或因果验证。

## 现有能力与复用

原ResearchClaimService.assessment只评估引用是否落在可用集合，COMPUTATIONAL_RESULT仍有NUMERIC_VALUES_REQUIRE_VERIFIED_ARTIFACT_CELL，fact_checked固定false。research.plan.assess_claim / artifact_cell及其Gateway输入输出保留，不增加同义MCP工具或平行Claim Engine。

原cell要求当前owner/project、完成Task、输入/结果VERIFIED和明确FileRecord，只读取已核验且实际文件名为deg.tsv的表。要求gene_id唯一、目标列存在、列名不重复；只支持log2FoldChange/pvalue/padj/baseMean/lfcSE/stat。数据来自逐级FD/O_NOFOLLOW打开的有界真实字节，复核SHA及文件前后属性，不从LLM、文件名或文献编号生成数值。缺失NA保留None，非有限数值和歧义feature拒绝。本轮补充拒绝行列数不齐。

## 新投影契约

新模型在schemas/claim_provenance.py；响应及请求机器Schema分别为docs/contracts/cygnusx-claim-provenance-v1.schema.json与cygnusx-claim-provenance-request-v1.schema.json。

| 内容 | 真实来源/边界 |
|---|---|
| claim_id/type/text | claim_id是owner/project/Task/Report/Observation/File/SHA/行列值及可选草稿的内容摘要；DEG_TABLE_CELL限定场景，不是新持久化实体 |
| source_report_id/version | 可选、同owner/实际Task、completed、scientific或reproducibility；准确指向所选版本，不按最新版本替换 |
| report_snapshot_id/digest | 仅该Report明确snapshot_id；原validate_snapshot_row及项目/Version关联核验 |
| Task/AnalysisLink/DatasetVersion | 原Provenance及显式Dataset关联；不按目录、时间、同名文件推断 |
| ResultObservation/digest | 所选Report明确观察，或其实际Snapshot引用；无Report时才取当前匹配观察。核验owner/project/Task/Link、原payload digest及artifact ID/SHA |
| FileRecord/SHA/行列/value | 原cell结果，再刷当前FileRecord生命周期/身份/登记摘要，并用原Provenance重核同SHA |
| ExecutionDefinition/binding digest | 只从已保存Observation.runtime取历史声明；可用时与实际Task冻结证据文档校验，绝不查当前catalog/镜像/参考补历史 |
| input_file_record_ids | 原Handoff/Provenance中的显式引用，空值保持未记录 |
| transformation | identity，仅解析已有数值，不重算统计量 |
| missing_evidence | Snapshot/Observation/定义缺失、NA、原Provenance环境/来源等缺口完整保留 |

schema_version=cygnusx.claim_provenance.v1。claim_id是只读投影内容身份，没有新Claim表/迁移；不是用户批准、签名或数据库不可变事实。若后续需报告长期保留该投影，应通过现有报告冻结/Manifest引用保存，不能把一次实时查询冒充历史结论记录。

## 四层语义

- VERIFIED_VALUE：当前受管表的这一行、这一列、这份SHA得到有限数值；可以同时存在环境、Snapshot、历史关联缺口。
- SUPPORTED_CLAIM：只用于服务器产生的“feature / column = value”有限数值陈述，不推广为机制、显著性、QC通过或普遍科研发现。
- AI_INTERPRETATION：可选ClaimDraft自由文本即使有DOI/PMID，也只按未验证解释显示；claim_text_verified固定false。
- NOT_VERIFIED：NA/缺值没有有限数值陈述；证据身份或字节冲突直接拒绝，不返回编造的替代值。

根verification_status描述值的核验；observation_binding、definition_status和missing_evidence另述追溯覆盖。数值核验不意味着全链完整，reproducibility_status恒NOT_RUN。

旧报告无Observation或Snapshot时不借最新记录；旧报告观察指向不同文件SHA、项目/Version/Task/Link或冻结定义发生冲突时拒绝。观察有定义摘要但文档不可得仅REFERENCE_ONLY，缺口明示；观察没有定义时NOT_RECORDED，不用Task当前配置补写历史。

## API与界面

POST /api/v1/projects/{project_id}/research-evidence/claim-provenance 是只读业务API，沿用现有research_plan_enabled及research_delivery_read_enabled、当前owner、reports/files/tasks权限；不依赖打开分析/下载门禁。输入仅继承原ArtifactCellRequest的Task/File/feature/column，另有可选source_report_id及未可信草稿。客户端不能自报value、DatasetVersion或verified状态，额外字段422。

ProjectResearchDelivery的现有Task成果卡增加ClaimEvidencePanel“查看结果依据”。仅列实际已登记且VERIFIED的deg.tsv和已有报告版本，用户输入feature/选择列后查询。显示实际值/状态、文件SHA、Task、Version、Link、Observation、定义、输入引用、Snapshot及缺口。报告/Task继续链接原详情；不另建报告中心。项目/Task切换中止请求、清空旧值，晚到结果丢弃，自由文本由Vue转义。

原Gateway工具仍由同一ResearchClaimService提供原cell/assessment能力；本轮没有为新投影增加别名或写权限。若未来将投影并入旧tool的可选返回字段，需单独评审契约/flags，不能因该UI上线强制扩大旧工具授权。

## CP验收

| ID | 隔离覆盖 | 边界 |
|---|---|---|
| CP01 真实单元读取 | 临时真实TSV，值0.03、行列及有限陈述 | 合成fixture，不是公开科研数据运行 |
| CP02 SHA | 漂移、登记摘要及观察artifact SHA不符拒绝 | 真实远程/并发运行未验收 |
| CP03 Task | 实际SQLite Task/Link及同owner查询 | 非文案关联 |
| CP04 Version | 实际DatasetVersion和已保存Observation引用 | 没有历史环境补写 |
| CP05 丢文件 | 删除临时文件后无verified值 | 不自动补下载 |
| CP06 旧报告 | 单独旧版本无观察不借最新；有观察冲突拒绝 | 缺Snapshot保持缺口 |
| CP07 AI解释 | 带PMID草稿仍AI_INTERPRETATION；不进入有限数值声明 | DOI/PMID不作事实认证 |
| CP08 跨owner | 伪造Task/File/Report及跨用户拒绝，客户端值/Version断言422 | ASGI身份验证替身，真实JWT/部署BLOCKED |

另有FileRecord外部停用缓存刷新、项目失活、UI晚响应隔离/转义测试；详见tests及quality证据。没有读取生产结果、修改ReportSnapshot或新增科研分析。

后续优先将已审阅Claim及其内容摘要作为现有Report/项目Manifest的明确选择引用，补完整历史报告的Claim冻结关系；不要将这个只读DEG投影升级为通用结论引擎。跨表转换、汇总、阈值政策和多组学解释须独立版本化与科学评审。
