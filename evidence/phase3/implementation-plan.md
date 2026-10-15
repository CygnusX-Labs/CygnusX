# Phase3 内部实施计划

P3-0：主仓及子仓 baseline.json 已封存。Phase0B Closure BLOCKED；Phase1 PARTIAL/BLOCKED；Phase2 隔离实现 CONDITIONAL，所有 Agent 写操作源码关闭。保留全部 dirty 增量。

P3-A：新增 Dataset、Version、Source、Asset、版本样本关联、Ingestion、AnalysisInputLink；复用 Project(owner-only)、FileRecord 和 Sample。增量迁移接 bioopsphase2，无历史回填、无文件删除。Repository 统一 owner/project scope，FileRecord 挂接重查归属。
P3-B：只读 GEO/ENA Adapter，受信 URL、禁止重定向、受限响应、超时/速率、来源证据、失败 unknown；fixture 不等于实时源验证。
P3-C/D：服务端 prepare_import 规范化、原有确认服务/门禁、DownloadService 原始/processed 两条 adapter、状态关联与恢复；本地受限校验、压缩包安全、counts 证据与样本审查。execute 默认关闭。
P3-E/F：Typed Handoff 保存版本/校验/缺口；复用 AnalysisFlowToolService/ManagedFileResolver 和 RNAFlow，只做 prepare；检查 R/DESeq2 环境，不具备测试条件则 counts-only 标注 BLOCKED 并交付独立补丁/计划。
P3-G：REST 与 Phase2 同一 gateway 服务/DTO；原生前端最小数据资产和预案视图，不改 Node 检索引擎。所有 flags 默认关。

测试：先隔离 SQLite 真 ORM/迁移 upgrade-downgrade，再 fixture HTTP、合成 FASTQ/counts/TPM/压缩攻击、服务 doubles 的跨系统故障与审批。PG/Redis/queue/Worker/外部MCP/live 结果独立记录；不因 mock 通过声称 READY。
