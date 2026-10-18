# 项目科研交付 RI06–RI09 增量实施

日期：2026-10-16。状态：PASS_CODE / PASS_ISOLATED；真实环境及浏览器验收 BLOCKED。本轮承接 RI01–RI04、RI12/RI13；未重建下载、报告、分析或 Agent 运行时。没有提交、推送、部署、生产迁移、真实下载/分析或开启既有执行门禁。

## 1. 依据与复用

已读附件列出的架构审计、实施路线、RI01–RI04记录、最新生命周期稳定化记录、RI06–RI09提案、可复现报告Phase0/1/2设计；现状依据架构库README、科研交付/报告/数据库基线及当前源码。历史提案不授予运行许可。

| 已有能力 | 本轮复用与边界 |
|---|---|
| Project / DatasetRepository | 当前active用户、owner项目、files/reports/tasks模块授权；不按目录判定Task归属 |
| ResearchProvenanceService | 项目有界聚合、真实DatasetVersion/AnalysisLink/Task/Run/Observation/Report；新调用允许不可用Task显式留缺口，旧调用默认行为不改 |
| ReportService / ReportFile | 读取已经完成的报告和实际文件；不触发build_delivery_package或报告生成 |
| ReportSnapshot | 验证既有冻结摘要/owner/Task，逐字节冻结为项目内容；不新增/改写旧快照 |
| ResearchDeliveryBuilder / EvidenceManifest v1/v1.1 | 只调用原verify_package校验已有单任务ZIP，保存其真实Manifest引用；不调用渲染和单任务大内存build来生成项目ZIP |
| BioReportAdapter | 本轮不调用；缺报告转已有独立生成流程，不由导出隐式触发 |
| Celery / 报告Job模式 | committed queued outbox、独占连接PG advisory lock、Beat恢复、固定安全错误、有限重试；原报告Job要求非空Task，不能直接承载项目包 |
| report_archive / StorageBackend | 本地pinned目录FD、原子发布、对象存储write_stream；有界回读核验后登记 |
| FileRegistry / 目录链 | source=report，task_id为空，明确ProjectExportJob.file_record_id；原User锁保护配额校验和一次计量 |
| AgentToolGateway | 新增两个只读能力；已有报告溯源能力继续使用，没有新MCP或Agent写导出工具 |

## 2. 可信关联与历史缺口

可信路径：Project.id → Dataset.project_id/user_id → DatasetVersion.dataset_id → AnalysisLink.version_id/task_id → Task.id/user_id。Task没有Project FK，Run.project_slug不是强关联。本轮不把目录、时间、同名文件或自然语言升级为可信关系。

Run仅取原Provenance核验的同Task/owner/flow、confirmed_at非空关联。Report按真实Task/owner查询，保存每个版本的ID、version、parent、snapshot、observation。Snapshot验证原模型及摘要；Observation复核owner/Task/project。Worker在收集和发布前重新检查当前项目/Task/Version及Report元数据关系；文件指纹独立检查。

新inventory使用VERIFIED_ASSOCIATION / PARTIAL_ASSOCIATION；缺Task标UNAVAILABLE，历史无Project FK为NOT_RECORDED。权限错误仍用既有403 FORBIDDEN，跨用户/项目返回不泄露身份的404，不把ACCESS_DENIED伪装为空列表。声明verified仅针对显式ID关联，不是执行环境认证。

原Provenance项目查询有20个Dataset、每个5个版本、全局20个分析Link等保守上限；truncated必须显示并拒绝prepare，不能导出截断集合后称完整。首版不提供无界项目扫描；超限项目需后续分页/选择协调。无项目关系的历史Task不枚举、不自动回填；删除/不可用显式关联保留缺口。

## 3. Manifest及范围冻结

契约：[ProjectDeliveryManifest v1](../contracts/cygnusx-project-delivery-v1.md)，[机器Schema](../contracts/cygnusx-project-delivery-v1.schema.json)。冻结actual files、references、missing、unverified、excluded五种情况。每个实际payload必须有大小和SHA，references不能假扮文件。

默认证据包；结果包仅增加已登记且核验的小型结果；复现材料包只整理已有证据和资源引用。报告版本可按ID选择，空选择的含义在UI明确说明。不存在默认递归打包、自动FASTQ/BAM复制、历史补环境、报告渲染或科研复现执行。

prepare只读且不创建Job。CREATE重新采集同一选择，比较用户看过的manifest_digest；变化返回409 EXPORT_DRIFT，必须重新预览。Job提交时冻结JSON，Worker仅验证并收集该集合，不重新prepare补入新文件或报告。预览时缺失允许partial；冻结后包含项漂移必须失败。

## 4. Job持久化与恢复

迁移文件 `projectdelivery01_project_exports.py`，parent=bioopsphase5，仅在隔离SQLite运行过真实upgrade；没有应用生产迁移。注册两个ORM表：

- project_export_jobs：owner/project FK RESTRICT、原始request_key、manifest+digest、阶段、尝试次数、retryable/error_code、archive_path、最终SHA/大小/FileRecord。
- project_export_requests：同owner/project/request_key唯一，指向Job。相同清单的不同请求复用一个Job，但每个请求别名都持久绑定，不能随后复用别名换范围。

Job另有owner/project/manifest_digest唯一约束；CREATE持Project行锁，数据库唯一约束作为并发后盾。ORM及PG trigger拒绝改变冻结scope；JSON不是数字签名，也不承诺永久防管理员篡改。

状态：queued → collecting → validating → packaging → verifying → publishing → ready；任何阶段可failed。各阶段提交真实状态，无虚拟百分比。队列投递失败保留queued，Beat每60秒扫描queued、超时active、retryable failed；Worker独占连接上的advisory lock跨commit保持，重复消费者返回busy，ready不重复发布。

默认最多3次尝试/300秒；存储、超时、暂时DB失败可恢复，权限/范围/摘要/内容冲突不可自动重试。archive_path在发布前提交；恢复重用原manifest和路径，重新验证源字节，不重做分析或下载。无法继续时保留失败行和私有归档，不删除科学事实。无DB/S3分布式事务；孤立私有文件不自动GC。

默认限制500文件、16MiB单文件、64MiB总payload、80MiB最终ZIP。有限内存ZIP_STORED实现有明确硬上限；大项目返回EXPORT_LIMIT，不宣称无限流式。目录使用StoragePathFactory.create_project_run_dir及ensure_directory_chain；用户可见目录无UUID。最终SHA/size、文件登记和ready同事务完成，User锁下校验剩余配额，幂等恢复不重复加配额。

## 5. 标准API、前端和Agent

| API（/api/v1） | 行为 |
|---|---|
| GET /projects/{id}/delivery-inventory | 只读关联、所有有界报告版本、缺口与能力状态 |
| POST /projects/{id}/exports/prepare | 只读预览，输入kind/task_ids/report_ids，返回manifest及digest |
| POST /projects/{id}/exports | 真实用户JWT确认该digest和request_key；API-Key不能创建 |
| GET /projects/{id}/exports/{job} | 当前权限下的持久Job状态，不暴露内部路径/异常正文 |
| POST /projects/{id}/exports/{job}/retry | 用户JWT、当前权限、retryable，同一冻结Job |
| GET /projects/{id}/exports/{job}/download | 用户JWT、当前权限/登记/字节/ZIP核验，attachment+no-store+SHA头 |

新增独立 `project_export_enabled=false`；原research_delivery_read_enabled仍保护读取。disabled时不投递/构造Worker DB引擎；本轮未开启配置。它不改变下载或分析源码门禁。生产启用必须先迁移并完成隔离环境认证，不能只打开flag。

ProjectDetailView保留原布局、ResearchPlan和ResearchDeliveryChain，追加ProjectResearchDelivery卡片。提供资产/任务/报告/执行证据、包类型、Task和Report版本勾选、真实文件/引用/缺口预览、确认、持久状态、重试、SHA核验下载及离线校验说明。缺报告进入原ReportsView，不隐式生成。空记录、未启用、无权限、网络错误、导出失败、partial完成分别展示。

项目切换中止请求并增加generation，旧inventory/preview/create/status/download结果均丢弃；selection变更使旧preview失效。递归轮询无重叠，离页清理；sessionStorage按project保存Job ID供同会话刷新恢复。窄屏采用换行和可展开文件清单；尚无真实浏览器验收。

Gateway增加research.project_inventory / research.project_export_status，沿用read:research与每次新context校验；已有research.report_provenance负责报告查询。没有CREATE capability，Agent不能持模型参数创建无限ZIP；写确认只在标准JWT业务端点。

## 6. 测试与门禁矩阵

具体命令/日志/JUnit/静态诊断保存 `evidence/project-delivery-ri06-ri09/`；证据目录不应进入提交。完整数字以最终checks.json为准，不把重叠批次数相加。

最终针对性后端8个文件共155项通过（含新增业务26项、相关回归129项），前端两个文件9项通过；类型检查、最终构建及其退出码通过。所选源码/测试Ruff通过，6源文件mypy通过；原8源文件同范围baseline/current各6条相同继承诊断、新增0条。全仓观测仍为Ruff288条、mypy1022条/223文件，前端全量567通过/7失败，不声称全仓通过。构建存在既有大chunk提示；测试退出时可能出现既有OTel关闭输出流告警，不能算真实科研运行证据。

| 附件验收项 | 代码/隔离覆盖 | 真实验收 |
|---|---|---|
| 1 单Dataset/单Task | real SQLite、原Provenance、真实文件、ZIP发布/下载 | BLOCKED |
| 2 多Dataset/多Task | 两条显式Version/Link/Task；选择子集 | BLOCKED |
| 3 同Task多报告版本 | 保留各ID/version/parent，不默认覆盖；显式报告选择 | BLOCKED |
| 4/5 缺科学/证据报告 | 明确gap，partial，无假报告 | BLOCKED |
| 6 缺Snapshot | partial；另测真实冻结Snapshot及已有单Task包引用 | BLOCKED |
| 7 历史Task无项目关联 | 同路径孤立Task不纳入；缺失关联不可猜补 | PASS_ISOLATED；真实盘点未做 |
| 8 跨用户/项目 | 原授权真实SQLite拒绝；API-Key不能创建 | BLOCKED真实JWT/部署 |
| 9 撤权 | module撤销后拒绝下载，发布前重新授权 | BLOCKED跨进程撤权 |
| 10 同时重复提交 | 行锁+双唯一键+request别名；SQLite去重约束 | BLOCKED；PG opt-in用例含8并发请求 |
| 11 内容/元数据漂移 | preview/Worker/download字节漂移、Report版本漂移拒绝 | BLOCKED跨进程/存储 |
| 12 ZIP异常 | 重复、绝对/越界、额外成员及预算拒绝；源码还拒绝链接/加密/重复JSON键 | PASS_ISOLATED；非执行归档 |
| 13 大文件 | 单文件/总量/截断拒绝；raw结果排除、符号链接不收集 | BLOCKED真实资源压力 |
| 14 失败/恢复 | publish故障→failed→原scope/path重试；ready重复不发布 | BLOCKED真Worker强杀及broker恢复 |
| 15 下载SHA | ASGI字节、Job SHA、ZIP清单、独立标准库验证器 | BLOCKED真实浏览器下载 |
| 16 不触发分析下载 | TaskService/DownloadService/报告build设为抛错仍完成，原Task/Report数不增 | PASS_ISOLATED |
| 17 项目切换 | jsdom延迟响应、清理旧上下文；原ProjectDetail上下文回归 | BLOCKED真实浏览器 |
| 18 浏览器/窄屏 | 响应式CSS及jsdom交互 | BLOCKED：Playwright不可用，无PASS_E2E |

新增后端业务测试为PASS_ISOLATED；包括实际SQLite迁移、ASGI端点（JWT验证器替身）、原FileRegistry/归档服务、真实临时文件、已有Builder验证、离线验证脚本。线程文件读取在测试使用仓库既有inline_file_capture：受管环境asyncio.to_thread唤醒受限；生产实现仍在线程运行。这不是生产线程或Worker验收。

PG opt-in只使用显式PROJECT_EXPORT_TEST_DATABASE_URL，数据库名必须以project_export_test开头；创建/清理随机schema，测试实际迁移、唯一键、不可变trigger、Project行锁下8并发去重。不读取生产DATABASE_URL。当前未提供，跳过应记BLOCKED。

全仓Ruff/mypy和前端全量测试没有通过；诊断原样保留。改动选择范围Ruff及新6源文件mypy通过，原8源文件shadow baseline/current均6条相同继承诊断（ProjectService原dict类型注解），新增0条；不能由此宣布全仓PASS。前端全量7失败位于协作室消息与聊天流式token断言，本轮未修改这些域。已跑前端类型检查和构建；构建退出及产物核验见证据。

## 7. 真实运行验收停止点

没有指定并授权的独立PG/broker/存储/登录浏览器环境，本轮不连接生产、不启动真实导出Worker，不启动任何科研下载/分析。真实验收必须用已有合法测试成果，按RI05独立环境计划固定版本、账户、配额及网络；先跑专用迁移/漂移、PG并发和trigger，再验证真实Celery重复投递、强杀各阶段、broker不可用、S3回读、撤权及恢复。

浏览器在1920/768/390宽度核查真实ProjectDetail：选择证据/结果/复现材料、逐项预览、确认、后台离页再进入、partial/失败/重试、切项目时注入慢响应、真实下载并比较Job/头/本地SHA、运行离线验证器；核对不存在横向溢出、焦点遮挡或假进度。未完成前不标PASS_RUNTIME/PASS_E2E，不开启项目导出flag。原下载/分析运行门禁保持关闭。

## 8. 兼容、保留与回滚

不改变ReportSnapshot/原ResearchProvenance DTO默认字段及摘要；报告版本只在新inventory投影中补充，避免旧快照反序列化新增默认值导致摘要变化。EvidenceManifest v1/v1.1沿用原校验器；不重写旧包、修补历史输入或升级复现结论。新ProjectManifest是单独版本，不拿它替代单任务Manifest。

Job、请求别名、原报告、快照和科学文件保留。FileRecord按原个人文件生命周期；首版不设自动到期/GC，清理需要单独审批的保留策略；FK RESTRICT保护记录关联。有保留Job的项目在功能启用时明确409 PROJECT_EVIDENCE_RETAINED，不能普通删除后丢失证据。关闭flag后数据库FK仍保护关联；旧删除流程的停用场景需运维保留审核，不能直接删表绕过。

回滚先关闭project_export_enabled并停止新投递，保留所有已冻结JSON/请求别名/ZIP/FileRecord；活动任务停在可对账状态。按baseline逐hunk撤新路由/组件/Worker，不整文件checkout/reset/stash，不覆盖原脏修改。没有部署或生产迁移，不执行生产downgrade；已产生Job的数据库不得drop两表或删归档来“回滚”。旧消费者继续读取原Report/Manifest；新包保留校验脚本和版本说明。

工作区另观察到download-s3-e1相关并行文件，本轮不修改、不归为项目导出成果。实际变更见下一节和baseline；不以相对HEAD的全部diff冒认本轮实现。

## 9. 实际文件及后续建议

新增：`application/schemas/project_delivery.py`、`application/services/project_delivery_service.py`、`domain/project_delivery_archive.py`、`database/models/project_export.py`、`celery_app/tasks/project_exports.py`、迁移`projectdelivery01`、项目Manifest契约/Schema、前端`api/projectDelivery.ts`及`ProjectResearchDelivery.vue`、组件测试、后端业务测试及PG opt-in测试。

增量修改：`core/config.py`、`api/v1/research_delivery.py`、`research_provenance_service.py`、`project_service.py`（保留审核删除保护）、`agent_tool_gateway.py`、`schemas/agent_tools.py`、`models/__init__.py`、`celery_app/celery.py`、`frontend/src/api/researchDelivery.ts`（仅可选version类型）、`ProjectDetailView.vue`及科研交付活动架构。锁文件、子模块、既有下载/分析门禁不由本轮改动。

RI10下一步将已有ResearchClaim/ArtifactCell与项目Manifest中的Task/Observation/Report版本引用对接，展示结论证据覆盖，不能从包校验推导科学正确。RI11继续收敛现有FlowAgent/固定工具的Profile和Gateway路由，保持授权源与审批边界；不为导出新建MCP或扩大Agent写权限。更大项目另评审分页冻结、流式存储及历史弱关联人工审核，不在本轮自动补录或执行历史复现。
