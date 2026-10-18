# 科研生命周期 RI01–RI04 实施与 RI12 契约评审

核对日期：2026-10-16。范围依据本轮附件；现状依据 ARCHITECTURE_DESIGN 活动文档、代码和隔离测试。本文是实施记录，不替代架构权威库。证据目录：`evidence/lifecycle-ri01-ri04/`（运行证据，不入提交）。

## 1. Executive Summary

本轮在既有下载、数据导入和报告链上增量实现 RI01–RI04，并完成 RI12-Design DTO、JSON Schema、摘要和兼容设计。没有新增下载调度器、报告引擎、数据库表、历史回填器或复现执行器。

下载登记补充真实 Task、owner、当前项目访问权和模块权限核对；能力契约统一服务端、REST、Gateway 和原下载页面；未验收传输在 Service 和 Worker 边界关闭。交付包修复科学报告和执行证据角色，核验关联、文件字节和 ZIP 清单，缺失内容诚实标为 partial。

**隔离验证通过不等于真实运行准入。当前所有实际下载模式包括人工下载入口均被源码门禁阻断；分析写门禁未开启。** 最终针对性 Python 测试 199 项、相关回归 270 项通过；前端针对性 43 项、Node 12 个测试文件通过。全仓 Ruff/mypy 未通过，不能宣布全仓 PASS。

项目一键可追溯导出（RI07–RI09）、历史流程复现（RI14–RI16）没有在本轮实现。报告交付包是将来项目导出的一个证据单元，不能把单个任务报告 ZIP 等同于完整项目归档。

## 2. 当前仓库与 Dirty Baseline

起始分支 `feat/research-agent-phase5`，HEAD `51011118535f782f5282f638b4a54649c79bf6d6`。`baseline.json` 保存关键文件摘要和子仓状态；`status.txt`、`diff-stat.txt` 保存起始脏状态；`baseline-files/` 保存涉及文件的变更前版本。工作区原有大量未提交修改及 docs/info 删除，均未 reset、stash、恢复、提交、推送或部署。

特别区分：真实 FileRegistry 登记、输出清单、部分下载来源/方法收敛和测试，在本轮开始时已存在未提交实现。本轮复用并加强它们，不把全部相对 HEAD 差异归为新增成果。相关基础文件包括 `domain/download_contract.py`、`infrastructure/download/outputs.py`、FileRecord 身份字段及登记测试。DatasetImportService 保持原实现。

基线测试记录 74 passed、3 failed、5 errors，Node 11/12。根因包括异常对象不存在的 `.message`、不完整 Settings 测试替身、旧 DownloadService fixture 和沙箱子进程警告断言；没有以跳过它们替代修复。

## 3. 修改文件清单

以下为本轮涉及文件，包含对继承脏文件的增量修改；精确起点以 baseline-files 为准。

| 组 | 文件 |
|---|---|
| 下载身份与准入 | `src/cygnusx/infrastructure/celery_app/tasks/download.py`、`application/services/download_service.py` |
| 来源与能力 | `domain/download_security.py`、`infrastructure/download/policy.py`、`application/schemas/download.py`、`application/schemas/download_capability.py`、`tools/download/config.py` |
| REST/Gateway | `src/cygnusx/api/v1/downloads.py`、`application/services/agent_tool_gateway.py` |
| 原下载页面 | `frontend/src/api/downloadCapabilities.ts`、`frontend/src/views/DownloadsView.vue`、`frontend/src/views/__tests__/DownloadsCapabilities.test.ts` |
| 报告交付 | `src/cygnusx/application/services/report_service.py`、`research_delivery_service.py`、`application/schemas/report_delivery.py` |
| 定义设计 | `src/cygnusx/application/schemas/execution_definition.py`、`docs/contracts/cygnusx-execution-definition-v1.md`、同名 `.schema.json`、`cygnusx-download-capabilities-v1.md` |
| Python 测试 | `tests/unit/test_lifecycle_download_security.py`、`test_lifecycle_report_delivery.py`、`test_execution_definition_contract.py`、`test_download_registration_contract.py`、`test_download_service.py`、`test_agent_tools_phase2.py`、`test_report_service.py` |
| Node 测试 | `pipelines/Treasure-Seeking_Mouse/functions/seqout-chat/tests/validateSearchQuery.test.ts`（仅测试，无检索内核改写） |
| 活动架构补记 | `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md`、`CygnusX_download_architecture.md`、`CygnusX_report_architecture.md` |

## 4. RI01 下载身份修复

真实登记入口首先验证数据库 Task、owner、下载 flow 和工作目录，然后核查该 Task 对应的 DatasetIngestion 及当前项目访问权；不能从目录名称推断项目。多条冲突关联拒绝。用户被停用、下载模块被撤销或项目权限变化时拒绝登记。

沿用实际下载前文件清单、输出筛选、SHA-256、FileRegistry、事务/savepoint 和配额锁。重复登记不得重复计费；既有路径内容变化、跨 owner/Task 及符号链接均不能静默接管。Task 成功但无合格输出仍需对账，失败或部分输出不会因此成为 Dataset READY。

贯穿测试链为：真实登记函数 → 原 FileRegistry → SQLite/FileRecord → 原 DatasetImportService.reconcile。当前 FileRegistry 原本直接使用 ORM 持久化，**并不经过 FileRepository**；未为迎合流程图增加一层平行持久化。测试没有预先手工插入带 task_id 的合格文件来冒充登记成功。SQLite 不能证明 PostgreSQL 并发锁行为。

G-RI01-01～04：隔离通过。真实 Worker、PostgreSQL 并发及下载运行仍 BLOCKED。

## 5. RI02 下载能力契约

`describe_download_capabilities()` 是共享服务端描述来源。认证 REST `GET /api/v1/downloads/capabilities` 和 Gateway `downloads.describe_capabilities` 调用它，原 DownloadsView 通过集中 API 获取方法、云来源和运行状态。界面请求失败或 write_enabled=false 时禁用提交，提交处理器同样拒绝。

描述区分源码支持与运行验收：sra 方法 aws/ftp；direct_link 为配置允许的受支持协议子集；云来源 aliyun/volc/huawei。二进制只显示受信配置的 basename，版本未核验为 null；runtime_status=BLOCKED，write_enabled=false。SRR/PRJNA 是候选来源，不是运行验证成功记录。

旧参数明确兼容：aws/ftp 继续可解析，但实际执行受门禁约束；Aspera/Auto/Prefetch 等不支持方法提交前明确拒绝，不映射成其他方法。GSE/GSM 不冒充已解析下载任务。额外 owner、Task、项目、二进制或任意 CLI 字段拒绝。没有升级生产 Polariseq 或删除历史任务记录。

G-RI02-01～05：源码与隔离验证通过；实际 CLI 版本、协议与 Worker 环境兼容仍 BLOCKED。

## 6. RI03 来源安全与资源控制

URL/URI 语法验证拒绝本地、内网、链路本地、组播、保留地址、IPv4 映射、非标准数字 IP、编码 host、凭据和异常端口。修复云 URI 的 ValueError 被捕获吞掉漏洞。DNS 观察与 redirect 辅助函数只能拒绝危险观察，**不能把事前 DNS 检查当成实际连接固定**。

原 ftplib 遍历增加目录深度、目录/文件数量、超时及 canonical pwd 循环约束，finally 关闭连接。输出登记有文件数、字节数和最终配额边界；下载期间的硬字节预算、CLI 重定向和最终出口目的地还没有可信环境证据。能力契约明确 transfer_max_bytes=null、transfer_budget_enforced=false。

因此 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False` 在 DownloadService 创建目录/Task/入队之前关闭实际下载，并在 Worker 主入口、各 CLI 和 FTP 连接前再次阻断。不是可由 Agent 传参打开的开关。安全失败没有新增自动重放路径。

这是已评估的可用性变更：原合法人工提交也暂不可真实下载，页面清楚显示未验收。其语法与能力仍保留。解除必须另行验收受信 CLI、最终网络出口约束、资源预算和真实 Worker，再评审源码门禁；本轮不能只开 feature flag。

G-RI03-01/02/04：隔离通过（02 通过明确关闭未验收模式实现）。03：登记与 FTP 预算隔离通过，传输期间预算 BLOCKED。05：契约及界面回归通过，合法真实下载回归 BLOCKED；不宣称无运行影响。

## 7. RI04 报告角色和测试恢复

从科学报告或执行证据报告入口均按真实类型分配角色。验证 owner、真实 completed Task、冻结快照 owner/Task/digest，按 ResultObservation 和适用时间筛选报告；旧未绑定科学报告只能选取快照时间之前适用版本，显式不匹配快照拒绝。

缺少科学报告、证据或冻结快照时交付 partial，缺失项进入 manifest，不伪造 ReportSnapshot.json。无快照的新 manifest 使用 v1.1 可空引用；旧 v1 仍要求快照。新交付模板 `delivery-v1.1.0` 避免复用旧错误角色包；不原地改写旧报告与冻结摘要。

ZIP 校验拒绝重复成员、重复清单路径、未登记成员、不规范路径、链接、目录、自引用及超限内容，并核对 available 文件 SHA-256/大小、missing_files 和 checksums 精确覆盖。它是交付包验证器，不是导入或执行归档的引擎。测试禁止 TaskService.submit，确认打包不启动计算。

恢复旧测试：修正 DownloadService 注入和位置参数预期、非法 accession 在 schema 阶段拒绝；目录预期使用现行 downloads；删除对应过期 quarantine。Settings 替身基于完整设置复制。Node 用独立模块导入捕获实际警告，避免把沙箱 spawn EPERM 当业务结果。旧报告测试增加事件循环心跳及线程池关闭，保持真实文件 I/O，解决沙箱 teardown 挂起。

G-RI04-01～05：相关隔离通过。真实 BioReport 科学运行和真实项目完整交付未验收。

## 8. RI12 ExecutionDefinition 契约评审

详见 [契约](../contracts/cygnusx-execution-definition-v1.md) 与机器 Schema。本轮只是设计与纯 DTO 验证，无持久化、迁移、Worker 接线和执行 API。

区分意图 ResearchPlan/RunPlan、批准前定义 ExecutionDefinition、未来真实启动观察 ExecutionObservation、已有 ResultObservation、冻结 ReportSnapshot。模型采用 frozen、tuple 及规范化 JSON 字符串避免嵌套可变。摘要对版本、null、引用及参数进行固定规范化后计算 SHA-256；不等同签名或授权。

输入、参考、发布包和镜像 digest 缺失保持 UNKNOWN/null，不从当前机器补历史。Task ID 参与摘要，未来预执行绑定协议需正式设计。经对现有模型复用、来源信任、摘要稳定性、缺失语义、兼容和未来接线的内部设计核对，可进入 RI12/13 后续评审；这不是人类批准运行。

## 9. 现有业务服务复用

复用 AgentToolGateway 的授权入口、现有 MCP/ToolBridge 暴露机制、DownloadService/Worker/原 CLI、FileRegistry、DatasetImportService、ReportService 和 research_delivery_service。AnalysisFlowToolService、TaskService、ToolConfirmationService 的原契约和门禁保留；未新增分析提交捷径。Report 打包只读已有结果，不调分析执行。未改 React Island 展示结构、Node 科研检索内核、FlowFrame 或分析引擎。

## 10. DTO/API 变化

| 契约 | 本轮行为与兼容 |
|---|---|
| DownloadCapabilities | 新增只读版本化 DTO，方法/参数/限制/代码验证/运行状态分离；REST 与 Gateway 共享 |
| DownloadRequest | 来源校验加强、未知执行字段拒绝、稳定错误代码；不支持旧方法明确失败 |
| EvidenceManifest | 接受原 v1 和新 v1.1；仅新版本允许缺失快照，必须保持 partial 和缺失清单一致 |
| ExecutionDefinition | 独立设计 DTO/Schema，无写端点、无 DB 列、无历史自动转换 |

没有数据库迁移、锁文件编辑或生产 CLI 升级。

## 11. 自动化测试命令及结果

完整命令和逐项映射见证据 `commands.md`、`checks.json`；测试索引 T-RI01-01～10、T-RI02-01～08、T-RI03-01～12、T-RI04-01～12、T-RI12-01～06 共 48 项是需求索引，**不是 48 次独立真实端到端实验**。

| 检查 | 结果 | 层级/证据 |
|---|---|---|
| 9 个 Python 针对性测试文件 | 199 passed，2 warnings | SQLite/本地文件/替身隔离；targeted-tests.log、targeted.xml |
| 23 个相关回归测试文件 | 270 passed，2 warnings | 原服务隔离；regression-tests.log；其中 integration 文件也是 isolated |
| 前端选择范围 | 43 passed，10 files | jsdom/组件，frontend-tests.log |
| Node 原仓测试 | 12/12 文件通过 | 离线，node-tests.log |
| 前端 type-check / build | exit 0 | 编译；frontend-types.log、frontend-build.log；非浏览器验收 |
| 本轮选择的 Ruff 文件 | PASS | static-checks.log |
| 12 个 Python 源文件 mypy | PASS | mypy.log |
| 迁移链静态检查 | PASS | migrations.log；没有运行迁移 |
| 共享工作区全仓 Ruff | FAIL，记录 289 errors | full-ruff.log，非本轮全仓净基线比较 |
| 共享工作区全仓 mypy | FAIL，1023 errors /224 files | full-mypy.log，未扩展修复无关域 |

测试范围有重叠，不能相加声称独立覆盖数。单独 legacy-report-tests.log 的 6 项包含于相关回归。2 类常见警告为既有 Pydantic 配置弃用与测试 JWT 短密钥；相关回归另含既有 asyncio marker 警告。最终 uv run 因默认缓存只读不可用，使用同一现存 `.venv/bin/` 工具复跑，没有安装或变更依赖。

## 12. 真实运行阻断

| Runtime Gate | 状态及原因 | 解除条件 |
|---|---|---|
| PostgreSQL/Redis/Docker | BLOCKED；connect-only 探测 PermissionError，未进行认证或业务操作 | 在授权可达环境重新验证实际版本、服务、挂载及 worker |
| 真实下载与出口安全 | BLOCKED；CLI 版本、最终连接及硬预算未认证 | 受信镜像/CLI、出口策略和资源限制的真实负例与成功例验收 |
| Worker→真实 FileRecord→Dataset | BLOCKED；当前证据为 SQLite 和真实登记函数 | 原队列/Worker/PG/存储贯穿测试及并发回滚验证 |
| BioReport/分析运行 | BLOCKED；源码 WRITE_RUNTIME_ACCEPTED=false；本轮没有真实分析 | 原审批链与运行环境验收，不能用模拟结果代替 |
| 浏览器体验 | 未进行真实浏览器验收 | 授权部署环境下页面与任务状态联调 |

`flags.json` 是验证时观察，不冒充起始时间采集；本轮没有修改其值。`runtime-probes.json` 不包含真实下载/分析 Task 或伪造运行日志。

## 13. G0–G10 验收矩阵

| 门禁 | 状态 | 证据/限制 |
|---|---|---|
| G0 基线保护 | PASS_WORKSPACE | baseline、快照、无 git 破坏操作；继承脏状态保留 |
| G1 下载身份 | PASS_ISOLATED | 原登记函数写入真实 Task/owner，错误身份拒绝 |
| G2 Dataset 对账 | PASS_ISOLATED | 原 reconcile 读取实际登记记录；PG 运行 BLOCKED |
| G3 方法契约 | PASS_CODE_AND_ISOLATED | 共用描述函数、schema/CLI 源码子集及组件测试；CLI runtime BLOCKED |
| G4 来源/预算 | PASS_FAIL_CLOSED；RUNTIME_BLOCKED | 危险语法拒绝；未验收模式均阻断，不能宣称实现传输期间硬预算 |
| G5 报告角色 | PASS_ISOLATED | 双入口、缺失、适用快照、字节及 ZIP 校验 |
| G6 已知测试缺陷 | PASS_TARGETED | 相关基线失败修复；全仓检查 FAIL 单列 |
| G7 定义契约 | DESIGN_REVIEWED_ISOLATED | 六组设计测试，Schema 对齐；无外部运行批准 |
| G8 写门禁 | PASS_CODE | 原分析门禁与新传输门禁 false，Settings 观察为关闭 |
| G9 范围与复用 | PASS_CODE_REVIEW | 无新引擎，无导出/复现执行系统，无 DB 迁移 |
| G10 真实状态 | PASS_DISCLOSURE | 所有真实运行缺口显式 BLOCKED，解除条件见第12节 |

子门禁详细状态和 48 项需求测试映射记录在 checks.json；PASS 均有层级，不能升级为 Runtime Ready。

## 14. 数据兼容与迁移风险

无 schema 迁移和批量回填，不修改已有快照摘要或旧报告字节。旧下载 aws/ftp 参数可读，不支持参数拒绝；旧任务也不能绕过 Worker 安全检查。当前功能收紧会阻断实际下载，必须在部署评审明确告知，不应悄悄开放。

Manifest v1.1 的可空快照要求消费者识别新版本；旧 v1 严格验证保持。升级只生成新模板交付，不覆盖旧错误包；旧包若不符合新验证规则可能被拒绝，不能自动修补为看似可信。FileRecord 重新登记必须满足原内容、归属及当前权限，不为历史缺失身份猜关联。

## 15. 回滚策略

本轮未提交或部署，无需也不得执行数据库或队列清理。需要撤销时按 baseline-files 比对，仅回退本轮明确补丁；禁止 git checkout/reset 整文件覆盖继承修改。新增设计文件可独立撤销，前端与 capability API 应成对回退，报告 DTO/服务/模板应成组回退。

保留真实文件、FileRecord、Task、Report、冻结快照和审计记录。已生成的 v1.1 包不得交给只识别 v1 的旧验证器并宣称已验证；保留版本或隔离新包。任何旧下载代码回滚仍须保持传输门禁关闭，不能为了恢复页面按钮而直接解除安全准入。无需回滚 migrations，因为本轮没有迁移。

## 16. 下一阶段准入判断

| 阶段 | 当前判断 |
|---|---|
| RI05 真实链路验收 | 可准备环境与用例；运行依赖尚 BLOCKED，不能宣称已完成 |
| RI06 生命周期只读整合 | 可基于现有身份和缺失语义增量准备，禁止自动补历史 |
| RI07–RI09 项目归档/导出 | 尚未实现；需项目范围、manifest、权限、制品保留及不可变快照设计 |
| RI12/RI13 正式定义/观察 | 可继续设计评审；持久化和 Worker 接线须独立实现与验收 |
| RI14–RI16 历史一键复现 | 未就绪；先补受信发布、输入/参考摘要、镜像、审批和新 Task 比较策略 |
| RI17 真实科研案例结论 | 未具备真实运行证据，不能宣称论文级复现成功 |

最终追溯目标应是“报告 → 冻结快照/结果观察 → 真实 Task → 已批准执行定义 → DatasetVersion/输入/参考/发布包”，每个缺口显式可见。一键复现应先预检并产生待人工批准的新任务，保留原任务与报告，再按明确比较政策对照新旧结果；本轮只补基础身份、报告可信交付和定义契约，没有执行这条后续链。
