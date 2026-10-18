# CygnusX 下载与公共数据接入架构

类型：as-built 活动基线；核实日期：2026-10-16。描述当前工作树代码，不代表生产部署或任何协议已验收。调查快照、D01–D16、D-T01–44、DL-RG01–15 及原始证据定位见 [专项调查](../docs/audits/cygnusx-platform-download-capability-and-agent-tool-readiness-audit-2026-10-16.md) 与 [证据索引](../docs/audits/appendix-download-evidence-index.md)。

**本文是"平台下载模块"的单一权威架构文件**。下载模块的完整细节——四阶段边界、三条传输实现、Worker 与 CLI 分发、FileRegistry 登记、源码门禁与验收——一律以本文为准；其余文档只在各自域内保留接入点与回指链接：

- 共享 Agent 工具层（catalog/身份 scope/审批/恢复）：[CygnusX_agent_tool_gateway.md](CygnusX_agent_tool_gateway.md)
- 寻宝鼠端到端链路（下载 Prepare→审批→执行段）：[CygnusX_treasure_mouse_architecture.md](CygnusX_treasure_mouse_architecture.md)
- Dataset 资产与 Flow 输入接入：[CygnusX_dataset_architecture.md](CygnusX_dataset_architecture.md)
- 路径与共享盘：[CygnusX_storage_architecture.md](CygnusX_storage_architecture.md)

**S0+S1 实施更新**：真实下载 Worker 已复用现有 FileRegistry 写入 Task ID、source=download、实测 SHA-256/size，并由不手填 FileRecord 的跨层隔离测试验证到 DatasetAsset。仅登记/对账契约 PASS_ISOLATED；没有部署、真实传输或解除 Agent 写门禁。S2–S7 尚未实施，历史审计仍保留其当时的断点结论；本节与当前源码为修复后的现状。阶段证据：[S0 红测试](../docs/implementation/download-s0-baseline-and-red-test.md)、[S1 契约修复](../docs/implementation/download-s1-file-registry-dataset-bridge.md)。

## 1. 模块职责与真实边界

下载有四个不同阶段：发现来源、执行传输、登记文件、审阅科研资产。前端「数据下载与聚合」的公共数据库/云存储/直链三tab共用一条Task链；云盘tab仅占位。下载文件落服务端用户空间，用户浏览器不承载远程传输。平台MinIO/S3存储、向浏览器生成presigned下载URL和拉取外部对象存储是不同功能。

| 层 | 当前职责 | 关键代码 |
|---|---|---|
| UI | 三来源POST、下载Task列表、跳转Task详情；云盘warning | frontend/src/views/DownloadsView.vue:193/217 |
| REST | 认证、按source开关、links数量、API-Key写门禁/确认消费 | api/v1/downloads.py:38/59；api/deps.py:47 |
| DTO | sra/cloud_storage/direct_link、协议与线程范围、浅层URL检查 | application/schemas/download.py:46/95 |
| Service | 用户目录/目录链、通用Task提交、队列调度 | application/services/download_service.py:48 |
| 队列 | 默认Celery analysis；settings可换RocketMQ | infrastructure/task_queue/dispatcher.py:22；celery_app/celery.py:78 |
| Worker | source三分派、CLI日志进度、按退出码判终态、文件扫描登记 | infrastructure/celery_app/tasks/download.py `_execute_download` / `_execute_cloud_storage_download` / `_execute_direct_link_download` / `_finalize_download_files` |
| 传输器 | EBI/SRA公共镜像或ENA；三家云CLI；aria2c与FTP目录ftplib | 同上；pipelines/EBIDownload/crates/ebidownload-cli/src/main.rs:347 |
| 文件注册 | Task前置文件清单、owner/task/source/SHA/size校验，原FileRegistry注册，目录链及配额同事务；冲突要求对账 | download.py `_prepare_download_registration` / `_register_downloaded_files`；storage/file_registry.py `register`；download/outputs.py |
| 科研治理 | 真实项目权限、Source/Run选择、预案、Asset/Version、SHA/科学输入审阅 | dataset_import_service.py:136/343/426；dataset_handoff_service.py:52/158 |
| Agent工具 | typed catalog、身份scope、确认、关联恢复、禁止执行 | agent_tool_gateway.py:47/77/167/761 |

## 2. 组件关系图

实线是源码关系，不代表运行认证；虚线是受门禁或断链阻断的关系。

```mermaid
flowchart TB
 UI[人工下载三来源] --> REST[Downloads REST]
 CD[云盘tab] --> STUB[尚未接后端]
 REST --> SVC[DownloadService]
 SVC --> T[Task ebi_download]
 T --> Q[dispatcher / analysis队列]
 Q -.部署运行未验.-> W[run_download]
 W --> EBI[EBIDownload]
 W --> CC[ossutil tosutil obsutil]
 W --> FD[ftplib匿名FTP目录]
 FD --> AR[aria2c]
 W --> AR
 EBI --> REG[原FileRegistry task_id source SHA size]
 CC --> REG
 AR --> REG
 GW[AgentToolGateway] --> META[GEO ENA resolver]
 META --> IMPORT[DatasetImportService.prepare]
 IMPORT -.源码write gate关闭.-> SVC
 REG --> FR[owner Task关联的FileRecord]
 FR -.受写门禁保护的reconcile.-> DS[DatasetAsset Version]
 DS --> H[verify / frozen Handoff]
 H -.worker_paths_verified=false.-> FLOW[Flow输入]
```

## 3. 三条传输实现

公共数据库：DownloadRequest.source=sra，原accession交EBIDownload `download -A`。人工表单不经过GeoMetadataAdapter。CLI用ENA filereport获取read_run；FTP分支经wget -c下载FASTQ并核MD5，AWS分支获取SRA再fasterq-dump转换/压缩。GSE/GSM的科学解析在独立Dataset resolver中；不承诺CLI原样GSE能展开。UI/API method=aws/aspera/ftp；已核宿主CLI选项=ftp/prefetch/aws/auto，Aspera有明确契约漂移。

云存储：source=cloud_storage；aliyun/volc/huawei及别名→OSS/TOS/OBS scheme→对应CLI cp。CLI配置/IAM从实际运行环境供给，不由前端传AK/SK。没有通用s3://或COS适配，也没有云盘解析器；presigned HTTPS只能按普通直链理解，未完成签名时效/日志脱敏认证。

直链：source=direct_link，http/https/ftp，URL作为argv交aria2c，无shell。recursive FTP尾斜杠先ftplib匿名遍历，后aria2批量。FTPS在DTO不接受，没有FTP_TLS或登录参数。--continue、split、max-tries等CLI参数是局部恢复机制，不证明Task跨Worker crash可靠恢复。

## 4. 一次请求的实现时序

```mermaid
sequenceDiagram
 participant U as 人工Vue
 participant A as Downloads REST
 participant S as DownloadService
 participant D as DB
 participant Q as dispatcher
 participant W as Worker CLI
 participant F as 文件登记
 U->>A: POST source / 参数 / 目标目录
 A->>A: 认证、feature、确认或人类JWT
 A->>S: submit owner DownloadRequest
 S->>S: normalize + owner realpath + ensure dir
 S->>D: 创建Task并save work_dir
 S->>Q: enqueue_task
 S->>D: transition QUEUED
 A->>D: get_db结束commit
 Note over D,Q: 队列可见可能早于DB提交，未运行验收
 Q-->>W: analysis任务（运行未知）
 W->>D: RUNNING
 W->>W: source分派外部CLI
 W->>F: CLI退出后有界完整或部分产物检查
 F->>D: FileRecord + Directory + used_storage
 Note over F,D: task_id source SHA size同savepoint登记；失败回滚SQL并保留文件
 Note over W,D: exit0但无完整产物或登记失败不得SUCCESS
 W->>D: SUCCESS或FAILED
```

## 5. 来源与科研资产接入

GeoMetadataAdapter固定HTTPS主机、禁重定向/trust_env、限制响应/样本/Run与缓存；输出SOFT/ENA来源证据、候选文件及未知项，不下载科研文件。DatasetImportService.prepare以真实owner Project、显式选择、source snapshot与预算建立Ingestion与一次确认，不创建目录/Task。raw仅已解析SRR；processed权威附件→direct_link请求。

execute仍被源码门禁阻断。代码意图是重验来源与配额→消费批准→持久SUBMITTING→Version/source_snapshot→同一DownloadService→task_ids。reconcile不重投，从Task→FileRecord.task_id取产物。S1已修复原DataFile/FileRepository登记断点：三来源Worker统一调用 `_finalize_download_files` → `_register_downloaded_files` → FileRegistry.register，明确传task_id/source=DOWNLOAD/实际SHA与size。Dataset原有task_id查询规则不变，真实登记跨层测试已证明能建立Asset；不再依赖double给FileRecord补字段。此处是代码/隔离证明，不能当成真实Worker下载验收。

人工下载无自动Dataset创建；已有合法FileRecord可经DatasetService.attach_asset显式关联。验证计算实际SHA-256、检查FASTQ/矩阵与安全归档，审阅样本/单位后冻结manifest_hash。source MD5、实际文件SHA和manifest hash分别存语义，不等价。worker_paths_verified固定false，因此Dataset READY文本不是Worker执行准入。

归档接入已有 `GeoProcessedDataService.expand:65`：写门禁后保留原archive、核SHA、受限展开、使用FileRegistry注册子文件并保存parent archive ID/SHA；失败保留staging对账。FileRegistry.register已支持task_id/source/checksum，S1下载Worker已复用该入口；现有ORM列足够，无新增表/迁移（历史证据E46/E47，S1真实登记契约验证）。

## 6. Agent与人工入口

```mermaid
flowchart LR
 H[人类下载] --> API[原REST]
 API --> DL[DownloadService]
 N[寻宝鼠Node] --> CB[有限委托固定callback]
 CB --> GW[AgentToolGateway]
 AI[平台AI] --> MCP[builtin MCPClient]
 MCP --> TB[ToolBridge bioops]
 TB --> GW
 GW --> CAT[typed catalog与scope]
 CAT --> DS[Dataset发现和预案]
 CAT --> DP[downloads.prepare SRR PRJNA]
 DP --> C[一次确认 人类JWT批准]
 DS --> C
 C --> G[源码门禁CLOSED]
 G -.未开放.-> DL
 F[FlowAgent] -.缺可信下载adapter.-> GW
 EXT[外部独立MCP legacy] --> API
```

下载页人类JWT可直接提交；API-Key写REST先过Agent gate。Gateway read默认关闭；上下文从active user/session/project派生而非模型输入，模块与scopes交集裁剪。Node有限委托不能approve/execute；批准端点用CurrentJwtUserId。模型user_confirmed布尔不能自证。

downloads.prepare仅SRR/PRJNA候选，预算未知；dataset.prepare_import拥有权威来源与科研选择/预算，内部不再调用downloads.prepare，所以当前没有嵌套双确认。跨入口重复请求仍缺统一去重。外部MCP legacy不是所有Gateway能力的等价投影；FlowAgent当前仅submit_plan适配Snakemake计划端点，下载Gateway尚未接通。

## 7. 配置、部署与观测

- 下载配置：tool_configs/download/download_config.yaml，mtime热重载；显式binary路径优先Settings。YAML三features=false；REST按YAML OR Settings。本地进程仅EBI开，其他download/read/import/Agent download关，非容器证据。
- Worker声明：deploy/docker/docker-compose.worker.yml worker image cygnusx-worker:v0.0.2dev，源码、tool_configs、共享盘与pipelines挂载；Dockerfile.worker未构建Rust downloader/安装aria2与三云CLI，依赖运行数据盘供给。
- 版本：子模块EBIDownload1.4.0；独立旁仓Polariseq1.4.3；宿主binary1.4.0/hash见调查；socket被拒，当前容器版本/digest/UID/挂载UNKNOWN。
- SRA逐Run进度：CLI本地加密Progress API→轮询解密→Redis→REST；缺失返回unavailable。Task状态与日志回写DB+PubSub。HTTP/云CLI百分比日志不代表逐文件完整性。
- Task状态只有pending/queued/running/success/failed/cancelled；Ingestion另有PREPARED/SUBMITTING/QUEUED/RUNNING/VERIFYING/PARTIAL/COMPLETED/RECONCILIATION_REQUIRED。不可混合成单一枚举。

Web与Worker共享盘分别由CYGNUSX_DATA_ROOT/WORKER_SHARED_DATA_DIR供给，同目标路径不证明同一物理内容。Worker entrypoint声明PUID/PGID默认1000降权，真实UID未知；Studio沙箱uid10001与出站proxy不是下载Worker的运行基线。证据见E49/E50。

## 8. S1 登记契约、恢复边界与后续验证

CLI前 `_prepare_download_registration` 持久化受控文件清单到原Task.parameters._download_output_baseline，核Task/user/work_dir与local backend，拒绝被其他Task引用的目录和旧未绑定文件。唯一任务目录尚属S4；因此历史重复accession/首URL造成的共享目录会先要求对账，而不是自动覆盖或抢占。

登记使用有界条目/文件/校验字节清单，目录按openat/O_NOFOLLOW遍历，文件用既有Dataset open_owned_file/checksum实算SHA，拒绝软/硬链接、特殊文件、越界、零字节与校验期间变化。排除progress.key、隐藏目录、checkpoint、*_metadata、.aria2/.part/.tmp/.log及带aria2 sidecar的未完成payload。新登记经原FileRegistry，真实子目录链与used_storage在同savepoint内写；User行锁/刷新配额，任一登记失败不留半批SQL记录、不删除真实文件。SRA进度写任务在最终登记前停止，避免迟到进度覆盖Task.parameters登记投影。

同路径只允许同owner/Task/source/SHA/size/active personal记录幂等复用；历史空hash/无Task/其他Task或owner的记录不静默更新。Task.parameters._download_registration投影记录FILES_REGISTERED/PARTIAL/RECONCILIATION_REQUIRED、file_ids/数量/字节，scientific_ready=false；不新增Task枚举或第二个ledger表。CLI非零退出可登记稳定普通部分文件，Task仍FAILED；exit0无完整产物或登记失败同样不得SUCCESS。部分文件SHA仅标识当前字节，不证明源checksum/传输完成，Dataset仍需科学审核。

登记配置在原DownloadValidationConfig：max_registration_entries默认20000、max_registration_files默认10000、max_registration_bytes默认1TiB，可由下载YAML覆盖；这是传输完成后的登记资源边界，不是网络硬预算。登记仅接本地受管存储，不声称远端S3对象已被拉取或认证。

仍未修复：通用URL/DNS/redirect/FTP出站防护、传输硬预算与并发预留、普通submit先排队后commit竞态、唯一工作目录/可靠取消/跨Worker恢复、Aspera选项漂移、完整逐协议Catalog及多Agent运行认证。这些分别属于后续S2–S7。现有源码写禁和worker_paths_verified=false继续有效。

S1验证：专用登记25个参数化用例；下载、Dataset、归档、Gateway、确认与MCP parity相关回归103 passed/5既有quarantine排除；修改文件Ruff、聚焦严格mypy与迁移链检查通过。全仓Ruff/mypy仍FAIL（报告记录当前问题），真实PG/Redis/队列/Worker/协议/浏览器E2E未执行。本阶段不承诺发布READY。历史审计111 passed/1 failed/5 deselected是当时快照，不能与本阶段测试集合混算。

---

## 附录 A：目标态参考（提案，非现状依据）

> 本节是"数据下载与多 Agent 工具化"的**目标架构**，用于规划方向与对齐长期愿景；**不得当作现状证据**。现状以实现 §1–§8 与源码为准。与现状的差距见 §8（开放缺口清单）与专项调查 DL-RG01–15。

```mermaid
flowchart TD
    A["科研寻宝鼠"]
    B["CygnusX AI 助手"]
    C["FlowAgent"]
    D["未来 Research Agent"]

    A --> E["Shared AgentToolGateway"]
    B --> E
    C -.-> E
    D -.-> E

    E --> F["Download Capability Catalog"]
    F --> G["Source Resolver"]
    F --> H["Download Prepare"]
    F --> I["Task / File 查询"]

    G --> J["GEO / ENA / SRA"]
    H --> K["统一权限与人工审批"]
    K -.-> L["DownloadService"]

    L -.-> M["现有下载 Worker"]
    M -.-> N["FileRegistry"]
    N -.-> O["DatasetVersion / Handoff"]
```

**与现状的关键差距**（对照 §1–§8）：

| 目标态节点 | 现状 | 差距 |
|---|---|---|
| A/B → E（寻宝鼠 / 平台 AI 共用 Gateway） | 源码已接线、运行未验 | 不代表实际tools注入/MCP/Node网络已认证 |
| C → E（FlowAgent） | `CygnusX_download_architecture.md` §6：FlowAgent 仅 `submit_plan` 适配 Snakemake 计划端点，**下载 Gateway 尚未接通** | 缺可信下载 adapter |
| D → E（未来 Research Agent） | 未落地 | 待规划 |
| K → L（统一权限与人工审批 → DownloadService） | 源码门禁 `WRITE_RUNTIME_ACCEPTED=False` CLOSED | 开放 Agent 执行的前置 |
| L → M（DownloadService → Worker） | Worker 部署运行未验收 | Dockerfile.worker 未装下载器/aria2/三云 CLI |
| M → N（Worker → FileRegistry） | S1已复用原register，写task_id/source/实际SHA/size，隔离契约通过 | 真Worker/挂载/传输与故障认证仍未完成 |
| N → O（FileRegistry → DatasetVersion/Handoff） | 真实登记→reconcile→Asset隔离通过；科学审阅与Handoff仍独立 | 写/运行门禁关闭，不自动提升科研READY |
