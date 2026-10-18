# CygnusX BioOps · 当前开发状态与完成度审计

## 1. 审计范围、时间、目标与权限限制

审计日期：2026-10-18，Asia/Shanghai。完整阅读任务书 docs/info/26.10.19/CygnusX_Current_Implementation_Status_Audit_Codex_2026-10-18.md，先阅读架构索引，再按下载、Dataset、寻宝鼠、Flow、科研交付活动基线定位源码。覆盖主仓、七个顶层子仓及相关嵌套报告子仓、HEAD+dirty 源码、IAT-R2 原始日志和脚本、IAT-R3/G3-E2 增量。旧报告仅作线索。

本轮唯一新增产物为本报告，未运行测试、构建、下载、外部元数据请求、Agent 自动执行、DB/Redis/Broker 操作、迁移、容器操作、提交或推送。环境事实来自保留日志，未声称旧服务现在仍在线。新运行补验为 RUNTIME_NOT_AUTHORIZED；历史授权不延伸为本轮授权。

## 2. 代码基线（HEAD/branch/dirty/submodule/build digest）

主仓 main，HEAD d648f54d24affd2bd3787332a49a5f4c96494cef。审计起点 git status --porcelain -uall 共24条：17条tracked修改（含五个dirty子仓），7个untracked文件；暂存区为空。父仓gitlink与子仓HEAD一致，无加号前缀，但未提交内容不由父仓指针覆盖。

| 子仓 | HEAD / 分支 | dirty范围 |
|---|---|---|
| Protocol/FlowFrame | 977ad657bbe7d49f2200a5f3f550b70f25234f3d / main | fastqc env |
| pipelines/ATACFlow | 4a68b347ba3b9497a86eed2603b6577afc3c2f27 / main | env、嵌套container_env/report/src、缓存删除 |
| pipelines/RNAFlow | 19f5068c4f9370ea27cb6fe554a3f061a1b62a51 / feat/result-manifest | 参数/env/DEG/manifest/snakefile；新增deg_edger.yaml、deg_method.py；嵌套report/src |
| pipelines/EBIDownload | b351e03dfc845d229102d90f9bd88d6ca731f0de / v1.4.0-2-gb351e03 | clean |
| pipelines/Treasure-Seeking_Mouse | 88dae95e7294dea5004330203f56e4211776fd74 / feat/paper-data-analysis | Node/server/组件/i18n修改；platform-tools.ts、React island及测试含untracked |
| pipelines/scrna | b5066338fba47b1ed3fbee042f1cb43859cff882 / main | clean |
| pipelines/tools | 24ecb6ce75657c5ce188603b54ac7bf10ffb6d46 / main | skills注册/新增RNA与ATAC skills、缓存删除 |

嵌套RNA report c4a0cae8e129918ccfbd4e031da808b85abffbb4、ATAC report 4b9f6254d7f967cb9d35391a92b684cb2b113ac1均dirty（Dockerfile/vendor）。RNA src f973d5f86de11a0efa156b7ecd2aa6b02c7ee17f、ATAC src 80e8ded2f958f2e26a8ada3587dffc0c8b54912f、container_env a41746e5712ea5898e2bf599356d86d5ed4e2711可访问。

IAT-R2/R3 baseline均为d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33，当时数百dirty文件；当前fa450dcc、d648f54d吸收了大量代码。R3 manifest.json初次复核93/93文件SHA匹配，但这不是日志执行时的签名构建认证。R2 API/Worker镜像sha256:be1904d09413f09bb467e336070676810c0a7e95bc166b576fdfd923c814c907仅证明旧环境；当前部署digest为NOT_OBSERVED。

主仓最新G3 dirty hunk：models/download_execution.py +77/-2，models/__init__.py +4；新增download_execution_admission.py仓库、dwnadmission01迁移与四项测试。迁移合并dwnreceiptnonce01/resstream01，未应用PG。R3 Provider/SSE/mTLS client已在当前HEAD，不应全写成未提交。uv.lock SHA=dcc3f7155380e3fc852a29b50974e053ec1393e70b68ac248ae9ce0da68e2c2e；frontend/package-lock.json SHA=995b06832aa2bdea3b31e912e5ddfee64b61e4957808c2f9719f6ee03c56d35e，与R3 baseline相同。

审计期间出现外部新文件docs/audits/*、frontend/src/utils/id.ts，随后stores/ai.ts、stores/upload.ts、TreasureResearchWorkbench.vue又出现diff。本轮未创建或修改这些文件；当前前端不能继承此前全绿结论。最终快照另附。

## 3. 执行摘要

**S6 NOT_READY / NO-GO；S7 NOT_READY / NOT_YET_END_TO_END。** 已有受保护业务主干、真实PG/Redis/文件登记子证据，以及项目报告HTML/PDF/ZIP交付子链；没有可信OS下载执行器和完整科研下载分析验收。

（A）完成分类：

- CODE_COMPLETE+已验证（限定局部）：十二类目录与状态分离、共享Gateway/schema、身份重验/缩权、确定性Provider两运行时工具结果回灌、HTTP发布回执/nonce隔离验证；文件SHA/size、Redis单消费另有历史真实子证据。
- CODE_COMPLETE+待运行（限定模块）：React typed action/展示树、合法Import Prepare持久化路径、Handoff与provenance模块；部署PG/Node/浏览器E2E未证。SSE仅同进程隔离范围完成。
- 接口/部分实现：G3协议+mTLS客户端+发布签名校验、server-owned admission/budget仓库。
- 尚未实现：Supervisor服务端、同步原子RX强制、全可写路径block/inode硬配额、独立租约回收、按环境/协议/工具/caller消费的运行认证。
- 正在开发：最新admission dirty实现与子仓未提交接入。依据代码差异，不推断存在活跃后台任务。

（B）闭环缺口：持久审批绑定→可信启动接线→OS强制和九项验收→S4故障窗复验→真实Dataset/Flow/BioReport。IAT-R3只读/Prepare与Runtime验收可并行于G3。

## 4. 按能力完成度矩阵

源码简写均位于src/cygnusx下，子仓另写完整路径。I=implementation；V=verification；O=operability；W=work_status。历史运行不代表当前部署。每行均给源码与测试/运行证据，缺失写NONE。

| ID/能力 | 当前源码定位 | 隔离验证/测试 | 真实运行 | 浏览器E2E | I / V / O / W与阻断 | 下一步 |
|---|---|---|---|---|---|---|
| D01 GEO/SRA/ENA | infrastructure/geo/adapter.py:GeoMetadataAdapter.resolve | test_dataset_geo_validation.py；ag09-prepare-isolated.txt | AG-12 NOT_TESTED，无真实外部元数据 | NONE | CODE_PARTIAL/PARTIAL/UNKNOWN/UNVERIFIED | 授权元数据验证 |
| D02 十二类目录 | tools/download/config.py:describe_download_capabilities | test_download_s5a_catalog.py | R2 p3-s5-run.log AG-16 count=12，非CLI认证 | NONE | CODE_COMPLETE/PASS_ISOLATED/DISABLED_BY_GATE/DONE（目录） | 分协议认证 |
| D03 Gateway/委托 | application/services/agent_tool_gateway.py:77,175；agent_tool_delegation.py:54 | test_download_s5b_consumption.py；ag06-revocation-regression.txt | R2 AG-05真实Redis NX/版本重验 | NONE | CODE_COMPLETE/PARTIAL/DISABLED_BY_GATE/DONE（局部） | 当前服务复验 |
| D04 Node HTTP | pipelines/Treasure-Seeking_Mouse/functions/seqout-chat/platform-tools.ts:3、index.ts:1874 | 子仓platform-tools.test.ts | task4-a-node-evidence.txt仅目录audit+Redis key | NONE | CODE_PARTIAL/PARTIAL/UNKNOWN/IN_PROGRESS | 完整Node聊天轮次 |
| D05 React/Vue | frontend/src/views/TreasureResearchWorkbench.vue；子仓src/island/FullPresentation.tsx | frontend-unit-regression.txt历史60 focused/597 full | NONE（当前服务） | 科研业务NOT_TESTED | CODE_PARTIAL/BLOCKED/ENV_BLOCKED/IN_PROGRESS | 构建island/Chromium流程 |
| D06 Legacy | infrastructure/ai_provider/testing.py；test_download_s5b_consumption.py:test_full_shared_tool_round | r3-runtime-regression.txt 32 passed | ASGI非监听服务；PG/配置替身 | NONE | CODE_PARTIAL/PASS_ISOLATED/ENV_BLOCKED/BLOCKED | 合法template/Provider真实服务 |
| D07 LangGraph | 同D06，engine参数化 | 同D06 | NONE（部署） | NONE | CODE_PARTIAL/PASS_ISOLATED/ENV_BLOCKED/BLOCKED | 同D06 |
| D08 Prepare/审批 | application/services/dataset_import_service.py:136,322,343 | ag09-prepare-isolated.txt、ag09-gateway-isolated.txt | R2 AG-10双并发一消费；合法Import PG未验 | NONE | CODE_PARTIAL/PARTIAL/DISABLED_BY_GATE/IN_PROGRESS | 合法proposal→JWT→Task绑定 |
| D09 PG幂等/事务 | application/services/download_service.py:155；infrastructure/download/reliability.py:39 | s4-unit-regression.txt 34 passed | p2-pg-run.log部分；PG-07弱断言、PG-01 IntegrityError | NONE | CODE_PARTIAL/PARTIAL/DISABLED_BY_GATE/UNVERIFIED | 当前PG并发复验 |
| D10 Broker/Worker/Beat | infrastructure/celery_app/tasks/download.py:197；download/reliability.py:88 | rec04/06/07隔离日志 | iat-mq-run.log 3/6通过；业务failed | NONE | CODE_PARTIAL/PARTIAL/ENV_BLOCKED/BLOCKED | ACK/API死亡/长期缺席/Beat |
| D11 FileRegistry关联 | tasks/download.py:_finalize_download_files；dataset_import_service.py:428 | registration contract、fr09-terminal-retry-isolated.txt | p2-fr-run.log FR-01：1200字节SHA一致 | NONE | CODE_PARTIAL/PARTIAL/DISABLED_BY_GATE/UNVERIFIED | 下载Task→Dataset对账 |
| D12 Adapter实体 | infrastructure/download/supervisor_client.py:43；trusted_execution.py:326 | g3-e2 isolated-regression.txt 99 passed摘要 | Supervisor NONE | NONE | CODE_PARTIAL/PASS_ISOLATED/NOT_DEPLOYED/IN_PROGRESS | 服务端+Worker生命周期 |
| D13 RX/出口 | trusted_execution.py:45观察契约；policy.py:77辅助验证 | test_download_trusted_execution_contract.py | 执行强制NOT_FOUND | NONE | NOT_IMPLEMENTED/NOT_TESTED/DISABLED_BY_GATE/TODO | 可信强制点 |
| D14 block/inode | trusted_execution.py:ExecutionBoundaryObservation | inode contract隔离子项 | quota实施NONE | NONE | INTERFACE_ONLY/NOT_TESTED/ENV_BLOCKED/TODO | 全可写路径配额 |
| D15 死亡/取消 | tasks/download.py:1319；trusted_execution.py:require_quiescent | S4 cancel、G3 receipt tests | R2 false/false；真实停止NONE | NONE | CODE_PARTIAL/PARTIAL/DISABLED_BY_GATE/TODO | 独立租约+空scope回执 |
| D16 九项HTTP | tests/integration/test_download_trusted_http_boundary.py:42 | real-http-boundary.txt | 9 skipped，0执行 | NONE | INTERFACE_ONLY/BLOCKED/ENV_BLOCKED/BLOCKED | 非Mock driver无skip |
| D17 FlowFrame | dataset_handoff_service.py:158,324；dataset_analysis_service.py:455；FlowAgent/src/tools/platform.ts | test_dataset_import_handoff.py、test_execution_evidence_ri13.py | 平台受控计算NOT_TESTED | NONE | CODE_PARTIAL/PARTIAL/DISABLED_BY_GATE/BLOCKED | 冻结输入到原Worker执行 |
| D18 BioReport/provenance | application/services/bioreport_adapter.py；research_provenance_service.py:233 | test_report_pdf_and_bioreport_phase2.py | RI095 delivery-chain/results.json交付子链；真实科学结果NONE | RI095三宽度export_ready=false | CODE_PARTIAL/PARTIAL/DISABLED_BY_GATE/UNVERIFIED | 科学结果渲染交付 |
| D19 S6准入 | policy.py:32；database/repositories/download_execution_admission.py:issue/resolve | admission四项SQLite；g3-e2日志 | 无运行证书消费 | NONE | CODE_PARTIAL/BLOCKED/DISABLED_BY_GATE/IN_PROGRESS | 同Task审批预算+caller认证 |
| D20 S7全链路 | dataset_analysis_service.py:463,481；research_provenance_service.py | NONE（全链路），子域日志不能替代 | NOT_YET_END_TO_END | NONE | CODE_PARTIAL/NOT_TESTED/DISABLED_BY_GATE/BLOCKED | S6后科研案例 |

## 5. S0–S3/G3：下载协议、安全边界及执行设施

十二类为geo_metadata/ncbi_sra/ena_fastq/geo_supplementary/http_direct_link/https_direct_link/ftp/oss/tos/obs/cloud_drive/existing_dataset_assets。Cloud Drive在config.py:299明确NOT_IMPLEMENTED；元数据与已有资产不是传输认证。DTO分开code/config/runtime/execution状态。EBIDownload子仓v1.4.0不能代表实际Worker二进制。HTTP认证不能外推其他协议。

GeoMetadataAdapter解析SOFT GSE/GSM、保留样本/关系/来源SHA；ENA filereport候选、截断/缺失flags明确；固定受信主机、禁透明重试/跳转。下载schema不接受GSE/GSM直接冒充SRR。文献工具在Node index.ts存在；Dataset权威来源经Gateway discover，前端卡片不是事实权威。真实外部元数据与文献关联科学正确性NOT_TESTED。

policy.py:18运输门禁false，describe_transport_admission固定execute_allowed=False，翻全局开关也不构成逐协议认证。DownloadService.submit:89及Worker多路径副作用前检查。URL/DNS辅助验证不钉住CLI连接，登记字节限制不等于传输RX硬上界。

## 6. S4：Task/Broker/Celery/FileRegistry可靠性

notify_after_commit外层提交才派发；nested rollback保护外层通知已有SQLite回归。DownloadService按owner/project/参数digest/request_key、User锁、独立目录、O_NOFOLLOW、64别名上限处理。终态无键复用与显式新键重试分开。Worker条件queued→running；running不盲重跑，标记RECONCILIATION_REQUIRED。marker仅归属线索。

R2 p2-pg-run.log：PG-02相同Task；PG-03 DOWNLOAD_REQUEST_CONFLICT；PG-04不同owner/project不同Task；PG-06发布替身失败后queued仍持久；FR-05晚到finalize返回false，FR-06取消幂等。FR-01 file_record bff3309c-c1ba-49fe-b207-b3e7dcf0c0fe，size=1200，独立SHA与DB一致。FR-03实测DOWNLOAD_LEGACY_UNLINKED拒绝，不是写入中断rollback；FR-04不完整产物拒绝。

PG-01一个创建、一个IntegrityError:gkpj，未证客户端可恢复重读/明确409。PG-07 harness:294只断言len(keys)>=1，挑任意活动行，不要求k2/k3保存在指定Task。PG-05只覆盖部分savepoint场景，当前通知逻辑新增后须PG复验。REC-03有双会话扫描历史证据；REC-02日志100+5与unique_ids=100，需完整两批ID验证并集。

PG-11 raw UPDATE最终success，harness允许success作为ok；应用Service/Repository防复活不等于DB触发器/RBAC保证。先审计角色权限和全部写入口，不能据此盲加DB触发器。

消息链最终failed/DOWNLOAD_ACCESSION_UNSUPPORTED，Celery成功结束不等于下载成功。MQ-02更正承认dispatch替身；MQ-01前后队列深度均0不证明时序。MQ-03未实际丢ACK；MQ-06/REC-BEAT初跑false，后续failed仅证明消费过，未验长期停Worker/Beat周期。当前deploy/acceptance/runtime.py:125仅允许report/export任务，过滤download，不能复证旧MQ-08。需专属下载Worker、SERVICE_NAME、队列、源码digest重新固定。

## 7. S5：Catalog、Gateway、Node、Legacy/LangGraph

ToolArgs禁止额外控制字段；capability_catalog与AgentService/MCP preset共享。Gateway.invoke:175重新context，校验agent_kind/project并取scope交集，catalog按ToolCapability.agents裁剪。delegation.verify:54校验身份/版本/TTL/当前scope，再Redis NX；重放码DELEGATION_REPLAY_BLOCKED。decide:629不匹配码CONFIRMATION_RECORD_MISMATCH；JWT approve与模型invoke分离。

ToolBridgeService.execute:48把bioops送同一Gateway；缺scope可信派生、有scope不扩张，异常success=false/is_error=true。tools/errors.py:79仅合法枚举码透传，未知ConflictError仍SERVICE_ERROR，不能称通用冲突码全覆盖。tool_bridge_service.py:99目录优先保留runtime_status/write_enabled字段已实现；仍需截断边界验证，不应列为完全未实现。

Node callback URL运维配置，不来自模型；platform-tools.ts过滤submit/cancel，redirect:error、30s超时、不自动重放；index.ts接真实工具循环。adapter/island未提交，父仓不可复现。AG-01原始记录只含downloads.describe_capabilities的audit 5143e0a7-8fd0-4519-93a2-989f6457e395与Redis key，不能证明完整客户端HTTP响应、dataset.discover或模型聊天全轮次。

## 8. IAT-R3：真实Agent/React科研UI当前完成度

testing.py确定性Provider由ProviderManager装配，test_full_shared_tool_round参数化两Runtime，匹配当前assistant工具调用后消费实际Gateway结果、二次回复与done；正式chat/stream ASGI序列化也覆盖。Agent查询、模型配置、Chat持久化facade被替换，不能声称真实PG agent_templates已配置或第三方模型调用。r3-runtime-regression.txt 32 passed，退出0后Otel/Loguru closed-stream异常属于观测问题，保留不抹除。

React FullPresentation保留Composer/SessionSidebar并复用MessageBubble组件树、ResearchWorkflowPanel；Dataset/Literature/ToolTrace/Grounding等原展示组件继续存在。typed adapter/迟到帧隔离有单测。597/88全前端结果为保留日志末尾摘要，非本轮重跑；当前外部前端diff使其不能认证当前版本。无真实Node/Vite/React科研入口构建与Chromium完整流程证据。

research_treasure_service实现request_id+fingerprint+event cursor回放，resstream01迁移、Vue去重恢复有37后端/6 parser/69组合隔离记录。producer/cancel注册进程内，跨进程取消与重启恢复未实现；真实PG并发/网络断流未验。合法Import PG持久化、GEO候选→资产→版本→Prepare待审批截图/HAR缺失。历史登录截图不补此缺口。environment.md的socket/bind/Chromium失败仅为当时环境证据，本轮未重新探测服务。

## 9. G3-E2：可信执行Supervisor与九项HTTP测试

mTLS客户端start/observe/renew/stop/evidence已实现，HTTPS+mTLS、禁代理继承/跳转、不重试、identity编码与64KiB响应界限。全src搜索仅定义，无生产实例化/Worker启动消费者。_verify_http_download_publication_receipt在FileRegistry前校验签名、Task/scope/attempt/execution/epoch、manifest并事务消费nonce；签名验证不能创造OS事实。

| 任务书设施条件 | 当前代码/证据 | 判定 |
|---|---|---|
| G3-01可信Supervisor/权限拆分 | 仅client，无服务端 | NOT_IMPLEMENTED |
| G3-02启动前cgroup/net/mount | request/observation与preflight可见性 | INTERFACE_ONLY |
| G3-03唯一出口/IPv4 IPv6/DNS逐跳 | policy辅助验证，不控制连接 | NOT_IMPLEMENTED |
| G3-04同步RX硬上界 | admitted/observed/dropped字段，无实际计量点 | NOT_IMPLEMENTED |
| G3-05 block/inode硬配额 | quota字段，无host配额/全挂载强制 | NOT_IMPLEMENTED |
| G3-06可信停止+scope为空 | require_quiescent仅检查回执 | CODE_PARTIAL/NOT_TESTED |
| G3-07 Worker死亡/重启租约回收 | renew客户端，无独立回收器 | NOT_IMPLEMENTED |
| G3-08同Task受控HTTP/CLI/SHA | 发布校验已接，admission未接线 | CODE_PARTIAL |
| G3-09九项真实HTTP | fixture:42固定skip，日志9 skipped | BLOCKED，0/9执行 |

CSV G3-01..09实际是small_file等场景编号，与上述设施条件不是同一编号体系，均未认证。

新admission/budget模型与resolver是实质开发；issue_processed_http_admission要求调用者已验证审批，但不查询验证真实ingestion/Task；resolve未接DatasetImportService/Worker/Supervisor。审批仍Redis TTL，缺持久actor/time与同Task fencing接线；raw多Task不能独立重复max_bytes。Integer字节列在PG通常32位，SQLite用100字节的四项测试不覆盖>=2GiB；小HTTP必须明确上限，否则评审BigInteger/DB约束。当前闭门下属于接线前风险，未证实可利用路径。

reserve只条件约束reserved≤limit；admitted计量/释放结算未接。revoke对CONSUMED拒绝，运行撤销/停止未完成。strict-visible-preflight记录CapEff/CapBnd=0、cgroup不可写/kill不可见、无XFS project quota，属可见性检查；工具安装和namespace可见不等于强制验收。

## 10. GEO/ENA→Prepare→Dataset→FlowFrame→BioReport

DatasetImportService.prepare独立生成ingestion/确认，不嵌套downloads.prepare。processed选权威附件，raw选解析run，预算/来源digest绑定；execute在确认消费/Task前过门禁。R2 AG-09空accession失败不证明合法proposal，R3合法proposal+Gateway关联只SQLite/metadata替身。

DatasetHandoffService.verify/manifest(freeze=True)校验SHA/size/科学类型并冻结DatasetVersion；DatasetAnalysisService兼容RNAFlow/counts_deg，counts必须raw_integer_counts及样本表，不把TPM/FPKM当counts。execute:463写门禁，:481 worker_paths_verified=false；TaskService/Worker有输入和定义digest接线。FlowFrame有validate/dry_run/ledger，平台Handoff冻结有代码；专家审核→签名release冻结→受控执行完整真实路径无足够证据，README不能替代。FlowAgent platform.ts仅x-api-key提交/api/v1/runs/snakemake/plan，未接统一下载委托。

BioReport源码可检查：嵌套report/bioreport/core.py有Jinja/Quarto render；平台BioReportAdapter屏蔽AI、清洗配置、拒绝远程依赖，HTML重用/PDF调用存在。phase4/bioreport-probe.json是FAILED。RI095项目交付链另有ready report c3698987-6f04-4a66-b3d2-b31379a65607；本轮重新计算HTML6635字节/SHA35cc6c13289b46c128588b4054119efaba2247f33da28bde555a4c438c39161b，PDF44369字节/SHAe829440a2ca232726b34b7ca2a2cf0d413583337db0036d4ac8f79d60c7a7e83，ZIP60429字节/SHAb112317efde17e3e2b07d2847771bd52f03d3ed6785a36295be5594db7ee2a2c，均与results.json一致。DB/HTTP对账、JWT下载/跨owner404是历史子证据。

PDF明确未做科研计算/复现，Dataset/Task未记录，无已验证结论，不能证明真实RNA结果科学报告。RI095 browser-results三种宽度export_ready均false。source-hashes与当前compose/control/checks/Dockerfile.pdf/report_audit_pdf_renderer五处不符：当前认证为STALE_EVIDENCE，但保存产物仍有效。完整科研链NOT_YET_END_TO_END。

## 11. 测试证据复核

旧CSV78条且ID唯一：PASS_RUNTIME42+PASS_E2E3+PASS_ISOLATED3+BLOCKED9+NOT_TESTED21=78。当前CSV120条且ID唯一：PASS_RUNTIME33+PASS_E2E3+PASS_ISOLATED27+BLOCKED44+NOT_TESTED13=120。父子断言不能转成业务能力通过率。

全部63个PASS行引用文件可访问，包括被rg默认忽略的.log。MQ-02阻断行引用的evidence/iat-r3-20261018/mq02-r2-reconciliation.md不存在，实际说明在docs/implementation/cygnusx-iat-r3-mq02-evidence-reconciliation.md。

主要降级：PG-07弱断言；PG-05部分savepoint；FR-03拒绝非写入中断；FR-05顺序两连接非并发；FR-09新键+文件登记仅R3隔离；AG-04会话/context拒绝非完整对象矩阵；AG-11模拟RedisError且未测确认故障；AG-13直接Gateway非ToolBridge运行；AG-14 Python URLError非Node；AG-15空列表类型断言非200版本上限；BR-04/06/08仅401/重复首页导航/刷新。MQ-02持久性可保留，幂等来自另一PG场景，不合成同次故障验证。

R3 raw pytest32/165 passed属隔离；G3最新99、admission4、S4 34、前端597、SSE37/6部分为追加摘要，强度低于逐例完整日志；均未本轮重跑，集合重叠不累加。九skip退出0不算PASS。R2 greenlet与R3Otel退出异常保留。全仓提交门禁本轮NOT_RUN。逐ID复核附后。

## 12. 当前安全门禁与发布能力分级

源码DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False、WRITE_RUNTIME_ACCEPTED=False；默认agent_download_write_enabled/agent_analysis_write_enabled/treasure_agent_write_tools_enabled=False；worker_paths_verified=False。Gateway/Dataset/report只读另受配置授权，本轮未读敏感.env，不声明线上值。

目录/只读发现/Prepare可独立按门禁验收；报告渲染交付有独立历史子链。人工下载、Agent下载/分析执行、可信HTTP、科研闭环均DISABLED_BY_GATE。审批权不等于执行认证；新admission不是已生效运行证书。

## 13. 当前阻断

| 类别 | 阻断 | 直接依赖 |
|---|---|---|
| 代码 | 持久审批→同Task admission/budget、Worker接线、Supervisor/RX/quota/lease、运行证书消费 | 后续实施授权/评审 |
| 环境 | 专用PG/Redis/Broker/Worker/API/Node/React及cgroup/net/mount/quota | 授权隔离主机 |
| 数据 | 合法GEO/ENA候选、原始counts/FASTQ、真实结果与版本冻结 | 受审查测试数据 |
| 授权 | 本轮只读，不能故障注入或启动服务 | 新一轮明确非生产授权 |
| 测试 | ACK/API死亡/长期缺席/Beat、Runtime/React、G3九项、科研闭环 | 上述代码/环境/数据 |

## 14. 本轮新发现风险与回归问题

1. 历史三个PASS_E2E未覆盖科研业务场景；PG-07/AG-15等ok条件过弱，需可失败的断言。
2. 当前验收runtime过滤下载任务，旧MQ注册不能复证；不能为补证擅自扩大报告Worker权限。
3. 共享树审计期间变化，93/93首次哈希不能覆盖后来前端变化；未提交子仓不在父仓digest。
4. G3预算32位PG列、consumed撤销缺失、admitted未计量、未查询真实审批记录，不能宣称S6接线完成。
5. 科学报告与项目摘要需分开，PDF存在但科学结果缺失，浏览器导出仍有false。
6. 具体错误码与紧凑目录已部分修复，不应重复列成完全未实现；通用冲突和截断边界仍待验。

## 15. P0/P1/P2下一步实施清单

本表仅交接，不是本轮实施授权。

| 优先级/模块 | 证据/预期位置 | 建议与验收标准 | 依赖/是否需授权主机 |
|---|---|---|---|
| P0-A审批绑定 | dataset_import_service.py:343；download_execution_admission.py；dwnadmission01 | 复用单Task processed HTTP，持久actor/time/摘要/tool digest/environment/caller/共享预算/epoch；事务回滚、并发单消费、撤销与字节边界验证 | 可先离线；PG需授权 |
| P0-B可信OS执行 | supervisor_client.py、trusted_execution.py、tasks/download.py | 独立Supervisor，启动前scope；唯一出口同步RX；全路径block/inode quota；独立lease与空scope回执；九项非Mock无skip及真实Registry/SHA | A后实际启动；需授权控制平面 |
| P0-C IAT-R3产品 | testing.py、Node platform-tools/index.ts、Vue/React island | 固定源码镜像、真实templates+确定性Provider两Runtime监听SSE；Node聊天全轮次；Chromium GEO→候选→资产→Prepare待审批/撤权/迟到/重连，HAR/截图/PG关联 | 与A/B并行，只读/Prepare独立；需授权栈 |
| P0-D S4故障窗口 | reliability.py、download_service.py、Task repository/原Worker | 指定Task别名并发保全；IntegrityError稳定重读或409；提交窗口API死亡、丢ACK、Worker长期缺席、Broker长故障、Beat故障/公平性 | 可并行准备；运行需PG/Broker授权 |
| P0-E科研E2E | handoff/analysis/execution_evidence/bioreport服务 | S6后同一审批/Task/FileRecord/DatasetVersion/Handoff/Flow/result/report；科学输入/版本指纹与授权HTML/PDF闭链 | A/B/D后；真实数据+授权主机 |
| P1-A证据治理 | CSV、R2 harness、R3 manifest、子仓dirty | 修弱断言、父子范围和坏路径；完整日志/exit/source manifest；先子仓审查再父仓pin建议 | 可离线，提交另授权 |
| P1-B错误/模型上下文 | tools/errors.py；tool_bridge_service.py:99 | 通用冲突、Node/MCP/SSE一致失败；大目录截断仍保留runtime/write状态 | 离线单测，无主机 |
| P1-C部署身份 | deploy/acceptance/runtime.py/compose.yml | 专属download Worker注册/队列/SERVICE_NAME及镜像源码绑定 | 需授权主机 |
| P2-A恢复观测 | reliability.py、Task日志/索引 | 别名查询性能、阈值/公平性、attempt/execution关联压测 | P0-D后，压测需授权 |
| P2-B其他协议 | policy.py、EBIDownload/云CLI | HTTP后逐HTTPS/FTP/SRA/ENA/OSS/TOS/OBS认证，不继承HTTP证书 | 逐协议授权 |
| P2-C FlowAgent | FlowAgent/src/tools/platform.ts | 规划与下载授权分离，最小委托、人类审批、禁止CLI自授权 | S6基础后 |

（C）下一轮前三件事：1）P0-A，同Task durable审批/预算接线，DoD为事务/并发/撤销闭合，风险为审批消费不可恢复、PG整数溢出；2）P0-C，可复现隔离栈与真实Runtime/React只读Prepare业务，DoD两Runtime+Node全轮次及Chromium记录，风险为误接生产/dirty构建；3）P0-B，在A定义稳定后实现可信Supervisor，DoD九项非Mock无skip，风险为内核/存储权限边界。P0-D与第二项并行准备，完成后才申请S6。

## 16. S6/S7 Go/No-Go

| 独立门槛 | 判定 |
|---|---|
| S4 PG+Broker+原Worker可靠性 | PARTIAL，ACK/API死亡/长期故障未验，当前Worker不匹配 |
| S5 Node/Legacy/LangGraph真实授权运行与审批回执 | PARTIAL_ISOLATED，部署完整入口未通过 |
| G3 OS与硬预算/配额/九场景 | NOT_IMPLEMENTED/PARTIAL，九项全skip |
| 审批/nonce/scope/预算同Task | CODE_PARTIAL，新仓库未接线/无PG运行 |
| environment/protocol/tool digest/human-agent认证撤销 | 无运行消费路径，默认拒绝 |

**S6 NOT_READY（人工与Agent均NO-GO）。S7 NOT_READY / NOT_YET_END_TO_END。** 保留已验证隔离成果、PG/Redis子断言和报告产物，不解除门禁。审计完成即停止，不启动后续实施。

## 17. 附录：证据索引、实际命令、未能访问的文件

证据根：evidence/iat-20261017/{01-baseline,03-env-runtime,05-s4-postgres,07-s4-files,08-s5-agent,09-s5-browser,13-iat-r2}；evidence/iat-r3-20261018；evidence/g3-e2-20261018；evidence/runtime-acceptance/ri095-authorized-20261017-attempt1。原日志可访问；未访问当前服务/数据库、生产栈、凭据或外部GEO/ENA。

实际命令族：pwd/date；git status --short/--porcelain -uall、rev-parse HEAD、branch --show-current/--list、log -8、diff --stat/--numstat/--name-status/--cached、submodule status --recursive及各子仓status；rg --files/rg -n；cat/sed；sha256sum锁文件；Python pathlib/csv/json/hashlib重新计数、存在性、哈希与原始日志提取。未运行pytest/npm/build或服务操作。猜测路径不存在后均改为实际文件定位，未用错误路径断言实现缺失。

### 17.1 全部Test ID复核

| ID | CSV状态 | 本轮判定 | 引用 |
|---|---|---|---|
| ENV-01 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-02 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-03 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-04 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-05 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-06 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-07 | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/g3-e2-20261018/isolated-regression.txt |
| ENV-08 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/12-report/progress-notes.md |
| PG-01 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| PG-02 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| PG-03 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| PG-04 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| PG-05 | PASS_RUNTIME | PARTIAL：savepoint覆盖不足，当前逻辑未PG复验 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| PG-06 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| PG-07 | PASS_RUNTIME | PARTIAL：任意行append和len>=1不证两别名保全 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| PG-08 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/13-iat-r2/iat-gap-run.log |
| PG-09 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/13-iat-r2/iat-gap-run.log |
| PG-10 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| PG-11 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-01 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| MQ-02 | BLOCKED | BLOCKED，引用缺失，实际说明见第11节；EVIDENCE_NOT_ACCESSIBLE:evidence/iat-r3-20261018/mq02-r2-reconciliation.md | evidence/iat-r3-20261018/mq02-r2-reconciliation.md |
| MQ-02.R2-PERSISTENCE | PASS_RUNTIME | PARTIAL：queued持久真实，dispatch替身，幂等另案 | evidence/iat-20261017/13-iat-r2/mq02-final-verdict.txt |
| MQ-03 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-04 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/13-iat-r2/iat-mq-run.log |
| MQ-05 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-06 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-07 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-08 | PASS_RUNTIME | STALE_EVIDENCE：当前runtime仅report/export | evidence/iat-20261017/03-env-runtime/env-03-06-runtime-identity.log |
| REC-01 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| REC-02 | PASS_RUNTIME | PARTIAL：100+5与unique_ids=100需完整并集 | evidence/iat-20261017/13-iat-r2/iat-gap-run.log |
| REC-03 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| REC-04 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| REC-05 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| REC-06 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| REC-07 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| FR-01 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/07-s4-files/p2-fr-run.log |
| FR-02 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/07-s4-files/p2-fr-run.log |
| FR-03 | PASS_RUNTIME | PARTIAL：legacy拒绝非中途rollback | evidence/iat-20261017/07-s4-files/p2-fr-run.log |
| FR-04 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/07-s4-files/p2-fr-run.log |
| FR-05 | PASS_RUNTIME | PARTIAL：顺序两连接非并发 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| FR-06 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/05-s4-postgres/p2-pg-run.log |
| FR-07 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| FR-08 | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-20261017/04-isolated-regression/p1-download-reliability.log |
| FR-09 | PASS_RUNTIME | PARTIAL：新键文件登记只隔离补验 | evidence/iat-20261017/07-s4-files/p2-fr-run.log |
| AG-01 | BLOCKED | BLOCKED，见源码/环境缺口 | docs/implementation/cygnusx-iat-r2-runtime-evidence-closure.md |
| AG-02 | BLOCKED | BLOCKED，见源码/环境缺口 | docs/implementation/cygnusx-iat-r3-runtime-ui-closure.md |
| AG-03 | BLOCKED | BLOCKED，见源码/环境缺口 | docs/implementation/cygnusx-iat-r3-runtime-ui-closure.md |
| AG-04 | PASS_RUNTIME | PARTIAL：会话/context拒绝非完整对象矩阵 | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| AG-05 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| AG-06 | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/ag06-revocation-regression.txt; evidence/iat-20261017/04-isolated-regression/p1-agent-gateway.log |
| AG-07 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| AG-08 | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-20261017/04-isolated-regression/p1-agent-gateway.log |
| AG-09 | NOT_TESTED | NOT_TESTED，无完成断言 | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| AG-10 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| AG-11 | PASS_RUNTIME | PARTIAL：RedisError注入，未测真实故障及确认 | evidence/iat-20261017/13-iat-r2/iat-ag-gap-run.log |
| AG-12 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| AG-13 | PASS_RUNTIME | PARTIAL：直接Gateway非真实ToolBridge | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| AG-14 | PASS_RUNTIME | PARTIAL：Python URLError非Node adapter | evidence/iat-20261017/13-iat-r2/iat-ag-gap-run.log |
| AG-15 | PASS_RUNTIME | PARTIAL：空列表类型断言不证明上限 | evidence/iat-20261017/13-iat-r2/iat-ag-gap-run.log |
| AG-16 | PASS_RUNTIME | 历史运行子证据，不授予当前部署认证 | evidence/iat-20261017/08-s5-agent/p3-s5-run.log |
| BR-01 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| BR-02 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| BR-03 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| BR-04 | PASS_E2E | PARTIAL：仅401 | evidence/iat-20261017/09-s5-browser/p4-br-run.log |
| BR-05 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| BR-06 | PASS_E2E | PARTIAL：仅重复首页导航 | evidence/iat-20261017/09-s5-browser/p4-br-run.log |
| BR-07 | NOT_TESTED | NOT_TESTED，无完成断言 | evidence/iat-20261017/09-s5-browser/p4-br-auth-run.log |
| BR-08 | PASS_E2E | PARTIAL：仅首页刷新 | evidence/iat-20261017/09-s5-browser/p4-br-run.log |
| BR-09 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| BR-10 | NOT_TESTED | NOT_TESTED，无完成断言 | NONE |
| G3-01 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-02 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-03 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-04 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-05 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-06 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-07 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-08 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| G3-09 | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-20261017/10-g3-security/BLOCKED-determination.md |
| ENV-01.R3-AUTH | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-02.R3-IMAGE | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-03.R3-STACK | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-04.R3-LOOPBACK | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-05.R3-DB | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| ENV-06.R3-WORKER | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| AG-02.R3-DET-PROVIDER | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/r3-runtime-regression.txt |
| AG-03.R3-DET-PROVIDER | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/r3-runtime-regression.txt |
| BR-01.R3-PRODUCT-E2E | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| PG-01.R3-CONCURRENCY | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| PG-11.R3-ALL-WRITES | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-03.R3-LOST-ACK | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-05.R3-API-CRASH | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-06.R3-WORKER-ABSENCE | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| MQ-07.R3-LONG-OUTAGE | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| REC-07.R3-BEAT-CYCLE | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| G3-01.E2-RECEIPT | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/g3-e2-20261018/isolated-regression.txt |
| G3-01.E2-NONCE-DB | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/g3-e2-20261018/isolated-regression.txt |
| G3-06.E2-INODE-CONTRACT | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/g3-e2-20261018/isolated-regression.txt |
| G3-01.E2-PUBLISH-GATE | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/g3-e2-20261018/isolated-regression.txt |
| G3-01.E2-MTLS-CLIENT | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/g3-e2-20261018/isolated-regression.txt |
| G3-01.E2-EVIDENCE-CLIENT | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/mtls-evidence-client.txt |
| MQ-05.R3-SAVEPOINT-ROLLBACK | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/s4-unit-regression.txt |
| BR-01.R3-UI-ISOLATED | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/frontend-unit-regression.txt |
| AG-01.R2-GATEWAY-AUDIT | PASS_RUNTIME | 历史audit+Redis key；客户端完整HTTP证据不足 | evidence/iat-20261017/13-iat-r2/task4-a-node-evidence.txt |
| PG-11.R3-SERVICE-GUARDS | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | docs/implementation/cygnusx-iat-r3-pg11-source-audit.md; evidence/iat-r3-20261018/s4-unit-regression.txt |
| AG-09.R3-PREPARE-ISOLATED | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/ag09-prepare-isolated.txt |
| AG-09.R3-GATEWAY-INVOCATION | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/ag09-gateway-isolated.txt |
| REC-06.R3-COMMIT-FAILURE | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/rec06-recovery-commit-failure.txt |
| REC-04.R3-BACKLOG-FAIRNESS | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/rec04-backlog-fairness.txt |
| FR-09.R3-TERMINAL-RETRY-REGISTRATION | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/fr09-terminal-retry-isolated.txt |
| FR-07.R3-WORKDIR-ISOLATED | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/fr07-workdir-isolated.txt |
| REC-07.R3-COOLDOWN-ISOLATED | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/rec07-cooldown-isolated.txt |
| BR-06.R3-STALE-SSE | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/frontend-unit-regression.txt |
| BR-08.R3-RECONNECT-CURSOR | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/iat-r3-20261018/environment.md |
| BR-08.R3-RECONNECT-PROTOCOL | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/sse-reconnect-isolated.txt; tests/unit/test_treasure_native_access.py; frontend/src/components/research/adapters/__tests__/researchPresentation.test.ts |
| BR-08.R3-CANCEL-SNAPSHOT | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/treasure-stream-cancel-regression.txt |
| BR-08.R3-CANCEL-ROUTE | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/sse-reconnect-isolated.txt |
| BR-01.R3-FRONTEND-UNIT | PASS_ISOLATED | PASS_ISOLATED，仅日志限定范围，非本轮重跑 | evidence/iat-r3-20261018/frontend-unit-regression.txt |
| G3-01.E2-HOST-PREFLIGHT | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/g3-e2-20261018/host-preflight-visible-gate-20261018.json; evidence/g3-e2-20261018/host-preflight-visible-gate.txt |
| G3-01.E2-ADMISSION-SOURCE | BLOCKED | BLOCKED，见源码/环境缺口 | evidence/g3-e2-20261018/admission-source-audit.md;evidence/g3-e2-20261018/isolated-regression.txt |

### 17.2 最终快照

2026-10-18T16:04:10.637865+08:00
R3 manifest 93项，最终不匹配1项：frontend/src/views/TreasureResearchWorkbench.vue。首次93/93与最终复核分开；变更项旧日志对当前版本为STALE_EVIDENCE。

```text
 M Protocol/FlowFrame
 M docs/implementation/cygnusx-agent-runtime-acceptance-compass.md
 M docs/implementation/cygnusx-g3-e2-trusted-http-runtime.md
 M "docs/implementation/\347\275\227\347\233\230.md"
 M "docs/info/26.10.18/04_\351\252\214\346\224\266\350\257\201\346\215\256\344\270\216S6-S7\344\272\244\346\216\245\346\250\241\346\235\277.md"
 M docs/info/26.10.18/CygnusX_Integration_Test_Matrix_2026-10-18.csv
 M evidence/g3-e2-20261018/admission-source-audit.md
 M evidence/g3-e2-20261018/isolated-regression.txt
 M evidence/iat-r3-20261018/handoff.md
 M evidence/iat-r3-20261018/manifest.json
 M evidence/iat-r3-20261018/manifest.sha256
 M frontend/src/components/AIChat.vue
 M frontend/src/components/ProjectResearchDelivery.vue
 M frontend/src/components/ProjectScientificSummary.vue
 M frontend/src/components/research/DatasetWorkspace.vue
 M frontend/src/stores/ai.ts
 M frontend/src/stores/upload.ts
 M frontend/src/views/TreasureResearchWorkbench.vue
 M pipelines/ATACFlow
 M pipelines/RNAFlow
 M pipelines/Treasure-Seeking_Mouse
 M pipelines/tools
 M src/cygnusx/infrastructure/database/models/__init__.py
 M src/cygnusx/infrastructure/database/models/download_execution.py
?? alembic/versions/dwnadmission01_add_download_execution_admissions.py
?? docs/Slogo.png
?? docs/audits/CygnusX-Current-Stage-Completion-Report.md
?? docs/audits/CygnusX-Feature-Evidence-Matrix.csv
?? docs/audits/CygnusX-Next-Action-Backlog.md
?? docs/audits/RI095-RC04-Completion-Gate-Matrix.md
?? docs/implementation/CygnusX_Current_Implementation_Status_Audit_2026-10-18.md
?? docs/info/26.10.19/CygnusX-Completion-Audit-Codex-Prompt.md
?? docs/info/26.10.19/CygnusX-Current-Stage-Completion-Audit-2026-10-18.md
?? docs/info/26.10.19/CygnusX_Current_Implementation_Status_Audit_Codex_2026-10-18.md
?? frontend/src/utils/id.ts
?? src/cygnusx/infrastructure/database/repositories/download_execution_admission.py
?? tests/unit/test_download_execution_admission.py

```

主仓tracked diff SHA256：99b116d72a753aa30eeeb929ce68be85c20ec98febf697f44e4d28d5e48c284b（不含untracked及子仓内部diff，不能代替构建digest）。
