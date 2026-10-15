# CygnusX BioOps Phase3 实施报告

## 1. Executive Summary

完成 P3-0 与 P3-A–G 的安全代码实施：版本化 Dataset 资产、GEO/ENA 证据发现、原始/processed 两条导入预案、原确认与下载服务适配、受限内容/归档校验、冻结 Handoff、RNAFlow/counts Flow 预案、共享 Gateway 与原生 UI。结论 **CONDITIONAL（本地隔离验证） / BLOCKED（真实运行与发布）**，不能声称寻宝鼠已能安全自动下载并分析。所有新增能力默认关闭，Agent 写门禁保持关闭。没有提交、推送、部署、生产迁移或真实大文件下载。

## 2. Baseline & Gates

HEAD `c68ea9e0d6ecb63cb5678444ad3dd1e2a8a00407`，分支 `feat/reproducible-report-phase0`。首次 dirty、diffstat、递归子仓指针记录于 `evidence/phase3/baseline.json`。既有 Phase0/1/2、报告和子仓成果保留；未改六个子仓内容或指针。P3-0 计划见 `evidence/phase3/implementation-plan.md`。

Phase0B Closure 仍 BLOCKED，Phase1/2 为隔离实现且真实验收未闭合。复查当前环境：Docker socket operation not permitted；没有 redis-server/psql；创建 loopback socket 也被限制，见 `runtime-probes.json`。Treasure 源码/既有镜像来源差异沿用 Phase0B Closure 阻塞，未伪造新镜像/digest。真实 Redis CAS、Postgres、Worker、外部 MCP、多用户全栈尚未验收。源码 `WRITE_RUNTIME_ACCEPTED=False` 不变，单改环境变量不能开放写入。

## 3. Architecture Decision

活动现状文档唯一入口：`ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md`，决策说明 `docs/adr/phase3-dataset-provenance-and-handoff.md`。复用 Project/FileRecord/Sample/Task，新增资产集合与版本关联，不将下载 Task 成功混同科学输入 READY；不创建第二套工具或执行系统。源原文、用户审阅和输出交付状态分别保存。SHA-256 是变更检测，不是签名或防管理员篡改承诺。

## 4. Database Schema & Migration

七表：datasets（owner/project/assay）、dataset_versions（序号、原始 snapshot、人工 review_annotations、校验、冻结 handoff）、dataset_sources（来源关系/证据）、dataset_assets（FileRecord/Task 引用、用途、类型、实测 checksum）、dataset_samples（既有 Sample 引用与版本映射/人工分组）、dataset_ingestions（原确认/调用/Task 关联和幂等键）、dataset_analysis_links（冻结版本→分析预案→真实 Task）。唯一约束保护版本号、版本文件、样本键、owner/project/request_key 和 Task 关联。

迁移 `bioopsphase3_dataset_inputs.py` 接 `bioopsphase2`；upgrade/downgrade 实际在 SQLite 测试运行，旧文件 sentinel 保留。迁移链静态检查通过。**PostgreSQL upgrade/downgrade、并发锁和实际 schema drift 未运行**，发布前必须在隔离 PG 执行。downgrade 只删新增关系表，不删除用户文件或旧表；须先备份导出关系证据。

## 5. GEO Adapter

`infrastructure/geo/adapter.py` 使用官方 SOFT 与 ENA file-report，不依赖网页拼猜下载 URL。支持严格 GEO/SRA/BioProject accession 验证、GSE→GSM→SRX→多 SRR、平台和 supplementary 候选、原始样本特征/处理说明。只查询有界候选，超限/无法关联保留 confidence_flags；没有 FASTQ 则不虚构。缓存/条件请求/速率限制是单 adapter 进程内能力，非分布式限流。

证据保留 URL、响应 SHA-256、时间、API 版本。HTTPS 固定主机、禁止重定向、限制响应、超时；404/429/timeout 返回明确不可用。当前使用 httpx fixture transport 做确定性验证，未做实时 GEO 公共源运行验收。参考：[GEO SOFT](https://www.ncbi.nlm.nih.gov/geo/info/soft.html)、[GEO 下载说明](https://www.ncbi.nlm.nih.gov/geo/info/download.html)、[ENA file reports](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/file-reports.html)。

## 6. Raw FASTQ Ingestion

prepare 不创建 Task/下载目录，产生持久预案/审计/可信确认记录；预算、owner/project、候选、规范化 DownloadRequest、源摘要和会话绑定审批。JWT 批准仅写授权。未来 execute 先检查源码+配置门禁、权限/模块、审批后的配额、权威源是否变化，再 CAS 消费确认，提交 SUBMITTING 预留，调用现有 DownloadService，记录真实 Task ID。

仅解析得到的 SRR 可走原 sra/ftp adapter；PRJNA/GSE 不盲传 SRR 入口。Task 状态与 FileRecord 注册分开；本地合成 FASTQ、实际 SQLite Task/FileRecord + DownloadService double 验证链接和 checksum。多 Run/配对必须明确映射，RNAFlow 命名不符给人工整理提示，不改原名。真实 SRA 转换二进制、下载硬预算、下载端重定向和 Worker 挂载未验收，因此不开放执行。

## 7. GEO Processed Data

processed 选择权威 supplementary，复用原 direct_link DownloadService。Series Matrix、表格、归档、h5/h5ad/mtx 等只标候选；不把文件名当科学类型。ZIP/TAR/GZ 流式受限展开，拒绝 ZipSlip、symlink/hardlink/特殊文件、超量/压缩炸弹、覆盖已有目录。展开使用项目私有新目录、FileRegistry 与目录链登记、原配额服务；保留父 archive FileRecord 与 SHA。真实 FileRegistry/SQLite + 合成 ZIP 测试通过，源字节不变；失败后保留 stage 供登记对账，不删用户文件或重下。

## 8. Expression Matrix Validation

gene×sample TSV/CSV 有界读取，校验唯一 feature/sample、方向、列宽、元数据精确匹配、非有限/负数/非整数、全零特征和空矩阵。保留原 ID，不静默修复。整数外观仍需可追溯 raw-counts 处理证据；UNKNOWN 不自动提升。TPM/FPKM/CPM/transformed/Series Matrix 不可进入 DESeq2。metadata 的 sample_id/group 必须匹配人工分组。来源原文不覆写，人工实验类型/资产用途/分组记录审阅人、原因和历史；冻结后修订复制新版本并重新校验。

## 9. Data Handoff Contract

契约 `docs/contracts/cygnusx-dataset-handoff-v1.md` + 同名 schema JSON；生成自严格 Pydantic DTO。manifest 包含 project/dataset/version、Source、FileRecord/asset ID、SHA/可用性、Sample 映射、Ingestion/Task、审阅和缺口。固定顺序、规范化 JSON hash；冻结持久化，相同版本后续读取快照；每次访问重查归属。执行前复核文件摘要，拒绝变化。未知 assay 明确阻塞，RNA/counts 只匹配 bulk_rnaseq；`worker_paths_verified=false`，不会把本地可见路径声称 Worker 可见。Task/Result/Report 未真实关联时 UNKNOWN / NOT_REQUESTED，不能虚构 Run 或输出。

## 10. Flow Integration

RNAFlow 复用既有配置和 AnalysisFlowToolService/最终 FlowSubmissionValidator；要求 bulk assay、人选参考/物种/链特异性、命名与配对、同目录且每文件唯一映射。预案展示受控 directory:// 引用、样本表、比较组和资源，内部路径仅服务端保留。counts/TPM 不进 RNAFlow。

独立 `pipelines/CountsDEGFlow` + `flows/counts_deg.yaml`：固定 `~ group` / `~ batch + group`、每组≥2重复、满秩且残余自由度、明确 reference/treatment、DESeq2 Wald 未收缩结果。提供 DEG/QC PDF/size factors/sessionInfo/output manifest 与 SHA 输入依赖。真实本机 R4.5.1、DESeq2 1.48.2、jsonlite2.0.0 和 Snakemake 在临时合成数据运行，199 个非全零基因六列数值与独立 R 参考在 rtol1e-8/atol1e-10 内一致。

该 Flow 是矩阵 specialization，跳过仅 FASTQ 的模板步骤；rich-loguru/监控、镜像、Worker 路径、结果发布及 FlowFrame 全量认证未通过，不能称生产认证 Flow。catalog 默认隐藏，TaskService 的最终提交保护阻止绕过 Dataset 来源；即使测试解除源码开关，worker_paths_verified=false 仍拒绝执行。

## 11. Tool & UI Integration

Dataset discover/inspect/list_files/list_project_assets/prepare_import，以及 analysis.list_compatible_workflows/prepare_from_dataset 使用同一 gateway 和 DTO；默认隐藏，不允许模型提供 owner/project/执行路径或自证确认。原 MCP preset、两类 Agent schema 和 Node 固定回调复用既有共享通道，未修改 Node 检索内核。

数据管理、分析中心 query 入口、寻宝鼠来源卡和工具卡共用 DatasetWorkspace/ImportCard；可选项目、区分 raw/processed、查看源样本、生成预案、恢复项目预案/真实 Task 链接、显示校验缺口、人工审阅/新建版本及准备分析。审批 TTL/失败可见，切换项目/会话忽略迟到响应。所有下载/分析执行按钮保持禁用。大型样本映射编辑与 archive 操作目前主要由 JWT REST 提供，非完整数据策展 UI。

## 12. Security & Multi-tenancy

所有服务通过 DatasetRepository 校验当前用户 active、模块、owner-only Project；文件必须 personal/active/同 owner，已知其他项目目录拒绝。旧无项目上传允许用户显式关联。共享项目权限不能凭设计推断。HTTP ASGI 实际 JWT 测试覆盖匿名、跨用户、API key 不能批准、JWT 批准与关闭执行；不代表完整 middleware/反向代理/真实 Redis 双用户 E2E。

openat/O_NOFOLLOW、路径根与 FD 校验、禁止硬链接/特殊文件及校验过程变化。外部源不执行脚本/反序列化，不记录私钥或确认凭证原文。工作区未发生破坏性 git 操作；未触及冻结镜像清单或受保护 mem0 配置残留。

## 13. Reliability

导入 owner/project/request_key 唯一，参数变化冲突；execute row lock + 消费确认 + SUBMITTING durable reservation；未知投递禁止自动重放。Celery Beat 每60s reconcile-only、最多20条，仅检查已存在 Task；关闭门禁在 DB engine 前返回。没有 FileRecord 则 RECONCILIATION_REQUIRED；Task失败但有文件则 PARTIAL，不能 READY。源变化、配额变化、权限撤销拒绝提交。真实 PG 并发、Redis恢复、Celery重复投递未验收。

查询无文件写副作用；不自动清理用户输入、stage 或失败资产。部分恢复须人工区分重登文件和重算，不将报告失败转为分析重跑。

## 14. Tests & Evidence

所有日志位于 `evidence/phase3/`（运行证据，不入提交）。`checks.json` 记录全量命令、exit和超时；`targeted-final.log` 为相关后端最终组合；`review-tests-final.log` 为新增审阅/REST/Flow关联测试；`frontend-research-final.log` 为7个共享卡/会话测试；types/lint-final 为新增核心检查。统计与真实 Snakemake 测试在 targeted 中运行，并非 mock统计。

全仓 Ruff 297 errors、mypy 1045 errors/228 files（首次全仓命令，含此前存量）；新域核心单独严格检查通过。后端 tests/unit+e2e 全量在180s上限结束，已出现 Agent config 存量失败，不能写全绿。前端全量519通过、7失败（协作室5、聊天流2）；本轮研究组件测试通过。Bridge190通过2跳过。前端类型/构建和最终相关计数见本报告末尾的最终结果表。没有全仓提交资格。

## 15. Changed Files

详细逐文件清单：`docs/implementation/cygnusx-phase3-changed-files.md`。baseline 只保存状态与 diffstat，没有逐文件原始内容，故共享 dirty 文件不能从最终 diff 精确分离历史 hunks；清单明确标记增量归属，未把旧 Phase 修改冒领为本轮。新增主体：7表/迁移、Dataset服务/DTO/REST、GEO与校验、CountsFlow、UI/API、测试/契约/ADR/活动架构。相关已有文件仅做注册、开关、共享工具和受管路径修复。

## 16. Remaining Risks / Blockers

- P0：Phase0B/2 未闭合；真实 PG迁移/并发、Redis CAS、队列与下载预算/重定向、Worker二进制/挂载、镜像来源、外部MCP及双用户全栈未验收。禁止开放写操作。
- P1：CountsFlow 模板日志/监控/镜像认证、输入→真实 Task→Result Manifest→Report 的整链没有平台运行证据；GEO实时适配尚未验收；adapter限流非分布式；多 Run/不规范命名须人工策展。全仓质量门禁存量失败须处理后再提交。
- P2：64MiB小数据校验预算；更大数据应迁移受控 Worker验证任务；复杂实验设计、混合物种、批次/多平台、多对比、单细胞只返回缺口，不自动扩展科学结论。批量 mapping/人工编辑体验仍可完善。

## 17. Rollback Strategy

保持四个 Phase3 flag false 并保留源码写门禁即可撤回入口；停止 Dataset reconcile 调度后备份新增关系与manifest，再在隔离副本确认 downgrade。真实数据库未执行迁移，本轮无需生产回滚。任何回滚不删 FileRecord/Sample/Task 原记录或用户磁盘文件；归档 stage/部分输出由人工核对保全，不自动重下或重算。旧下载/分析/报告入口沿用原服务。

## 18. G0–G15 Acceptance Matrix

PASS 下文仅指注明层次；BLOCKED 不等于未写代码，尤其 G15 按任务书允许阻塞。

| Gate | 结论 | 证据 / 边界 |
|---|---|---|
| G0 | PASS（记录）/ BLOCKED（真实） | baseline、Closure复读、当前runtime probes、源码门禁保留 |
| G1 | PASS（隔离） | 7表实际SQLite持久化、来源/文件/样本关联 |
| G2 | PASS（隔离） | 跨owner/project/挂接/撤权负例、ASGI JWT；真实双用户未验收 |
| G3 | PASS（SQLite+静态）/ BLOCKED（PG） | 实际upgrade/downgrade保留旧文件；真实PG未测 |
| G4 | PASS（fixture）/ NOT TESTED（live） | SOFT/ENA多Run/异常/证据透明 |
| G5 | PASS（隔离） | prepare无Task/文件写，审批展示绑定内容 |
| G6 | PASS（隔离拒绝） | forged/变更/关闭gate/JWT负例；真实Redis待验收 |
| G7 | PASS（隔离）/ BLOCKED（Worker） | mock下载+实际Task/FileRecord+FASTQ摘要 |
| G8 | PASS（本地合成）/ BLOCKED（传输） | processed候选/原direct_link适配/真实FileRegistry展开；下载端未测 |
| G9 | PASS（隔离） | counts证据、TPM/FPKM/log/Series Matrix、元数据/设计负例 |
| G10 | PASS（隔离） | typed manifest/冻结hash/新版本/缺口；Worker false |
| G11 | PASS（prepare隔离）/ BLOCKED（执行） | 实际RNAFlow配置/validator/受控引用；挂载未通过明确拒绝 |
| G12 | PASS（本机统计+Snakemake）/ BLOCKED（发布认证） | 独立R参考一致；非平台Worker认证 |
| G13 | PASS（隔离）/ BLOCKED（并发运行） | 幂等、PARTIAL、SUBMITTING不重放、恢复链接；真实重投未验收 |
| G14 | FAIL（全量）/ PASS（相关组合） | 全仓lint/type/前端存量失败、后端超时；相关下载/Flow/报告测试通过 |
| G15 | BLOCKED | Phase0B+2及全栈未READY；所有Agent写操作仍关闭 |

### T01–T36 测试索引

| ID | 结果层次 | 实际覆盖 / 缺口 |
|---|---|---|
| T01 | PASS 隔离 | dataset_phase3：多资产、样本、来源持久关联 |
| T02 | PASS 隔离版本 | clone及显式目标导入新版本均保留旧关联；同GSE两次Mock导入新版本通过；真实二次传输未测 |
| T03 | PASS 隔离 | 跨owner文件读取/挂接拒绝 |
| T04 | PASS 隔离 | 跨project猜测Dataset/version拒绝 |
| T05 | PASS 隔离 | 历史FileRecord无Dataset保持存在可访问 |
| T06 | PASS SQLite / BLOCKED PG | actual migration upgrade/downgrade + sentinel |
| T07 | PASS 隔离 | 审批后active/配额撤销拒绝，无Task |
| T08 | PASS fixture | GSE/GSM/SRX/多SRR，源证据 |
| T09 | PASS fixture | 无原始Run显式缺口 |
| T10 | PASS fixture | Series Matrix不标raw counts |
| T11 | PASS fixture | 404/缺supplement，不虚构URL |
| T12 | PASS fixture | 429/timeout/有界响应；无自动无界重试 |
| T13 | PASS fixture | redirect/不可信URL拒绝；真实下载Worker待测 |
| T14 | PASS 隔离 | prepare无Task/目录副作用（有预案/审计写） |
| T15 | PASS 隔离 | 未批准不可consume/execute |
| T16 | PASS 隔离 | 参数/来源变化旧确认拒绝 |
| T17 | PASS 隔离 | flags开启也不能绕过源码门禁；Celery关闭不建engine |
| T18 | PASS 隔离 | request_key重复复用；投递不明不重放 |
| T19 | PASS 隔离double | 真实SQLite Task/FileRecord+temp FASTQ+source/checksum |
| T20 | PASS 隔离double | failed Task已有文件仍PARTIAL，不READY |
| T21 | PASS 隔离 | 配额/预算/路径负例，执行前复查 |
| T22 | PASS 合成 | ZIP/TAR/GZ炸弹、ZipSlip、链接及特殊文件 |
| T23 | PASS 合成 | rawcounts源证据+实物metadata+人工组→实际countsFlow prepare |
| T24 | PASS 合成 | 整数但来源未知→UNKNOWN/REVIEW_REQUIRED |
| T25 | PASS 合成 | TPM/FPKM/log/小数被分类或拒绝；R禁止非raw类型 |
| T26 | PASS 合成 | 缺失/重复样本列、metadata不匹配拒绝 |
| T27 | PASS 合成 | 方向未知/重复gene拒绝，ID不改 |
| T28 | PASS 合成 | 字节/行列/行长/膨胀预算；非大规模性能验收 |
| T29 | PASS 实际R负例 | 无重复/混淆设计/无剩余自由度拒绝 |
| T30 | PASS prepare隔离 | 真实RNAFlow validator受管目录/样本表，绝无Task |
| T31 | PASS 实际本机隔离 | DESeq2独立参考数值、Snakemake全DAG；Worker未测 |
| T32 | PASS 拒绝 / BLOCKED live | manifest worker=false，解除测试门禁仍拒绝执行 |
| T33 | PARTIAL / BLOCKED | version→AnalysisLink→Task代码；真实ResultManifest整链未测 |
| T34 | PASS 报告相关回归 / BLOCKED整链 | Phase2报告重试独立测试；Dataset真实报告关联未知 |
| T35 | PASS 代码/隔离 | 共用catalog/DTO/gateway；跨Agent现有schema回归，无live MCP |
| T36 | PASS 隔离恢复 / BLOCKED运行 | 持久proposal/Task ID恢复、会话scope；断网真实全栈未测 |

## 19. Phase4 Readiness

**不准入需要真实自动下载/分析/证据交付的 Phase4。** 可开展只读契约/合成测试开发，但不能以本地统计通过替代平台运行验收。下一阶段前必须：补齐隔离PG迁移/并发、真实Redis CAS/TTL/故障恢复、干净镜像来源与Worker挂载/工具版本、下载安全预算、双用户UI/REST/MCP整链，以及一个小型真实公开科研案例的版本→Task→Result Manifest→Report证据闭环。关闭开关和输入文件保全策略继续有效。

### 最终验证结果（与全量失败分列）

| 命令 / 检查 | 结果 | 证据 |
|---|---|---|
| `.venv/bin/pytest` Dataset/Geo/Import/Review/Counts + Phase2 tools/Download/Flow/Report 相关组合 | **135 passed, 5 deselected**，21.36s | targeted-final.log；含真实本机R与Snakemake |
| 新增跨Agent Dataset schema / 源码门禁测试 | **2 passed** | gateway-tests-final.log；共享gateway组合 **41 passed**，gateway-regression-final.log |
| Dataset核心 Ruff | **PASS** | lint-final.log |
| Dataset/Geo/REST/队列/Gateway严格mypy | **PASS**，14源文件；后续gateway单独PASS | types-final.log / gateway-types-final.log |
| 全仓 Ruff / mypy 最终复查 | **FAIL：297 / 1042 errors（227文件）** | ruff-all-final.log / mypy-all-final.log；本轮gateway3个类型错误已修复 |
| 迁移链 | **PASS**，唯一head/拓扑连通 | migration-chain-final.log；不是实际PG升级 |
| Bridge pytest | **190 passed, 2 skipped** | bridge.log |
| 前端研究入口 DOM 测试 | **7 passed** | frontend-research-final.log |
| 前端 vue-tsc --noEmit / npm run build | **PASS**（构建产物已更新）；最终微调后复查另有 final 日志 | frontend-types.log、frontend-build.log；frontend-types-final.log / frontend-build-final.log |
| 前端全量 Vitest | **519 passed, 7 failed，3失败文件** | frontend-all.log；协作室5、聊天流2 |
| 后端全量 unit+e2e | **TIMEOUT 180s，未完成** | backend-regression.log / checks.json；不能视为全绿 |
| 镜像映射、实际 load_agent_configs 与Studio离线契约 | **PASS** | image-mapping.log / studio-runtime.log；不表示镜像启动通过 |
| `git diff --check` | **PASS** | diff-check.log |

全仓失败均未通过批量格式化或修改无关模块掩盖。隔离覆盖不包括真实数据库/Redis/Worker、下载运行、浏览器手工E2E或外部MCP transport。临时测试 `_MemoryStore` 和 DownloadService doubles 的使用在测试文件声明，未启用生产内存确认。

最终增补：同一GSE显式导入已有Dataset的新版本已实现（ImportPrepare.dataset_id，owner/project重查且绑定审批），两次Mock导入与旧版本保全通过；审阅/REST/Flow/版本增补组合 `review-tests-final.log` **8 passed**。最终135项组合已包含这些增补及2项Dataset Gateway测试，其他聚焦日志均有重叠，不另行相加。

最终生产构建复查 `npm run build` exit 0，产物 `frontend/dist/index.html` 更新于本轮最后UI修改之后；汇总机器可读证据 `evidence/phase3/final-verification.json`。不将 G15 阻塞转写为已开放。
