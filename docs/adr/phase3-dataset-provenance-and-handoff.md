# ADR：Dataset 版本、来源与受控 Handoff

状态：代码采纳；运行发布待验收。活动架构入口：`ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md`。

选择在既有 Project/FileRecord/Sample/Task 上增加 Dataset 版本化关联，不改写旧文件资产。来源原文与人工注释分离；冻结快照绑定审批，修订复制新版本并重新校验。新增 Ingestion 作为既有 DownloadService 的关联和对账记录，AnalysisLink 保存既有 Flow validator/TaskService 的参数与版本来源；不创建平行下载或执行引擎。

原因：FileRecord 代表可访问文件，不足以代表“这个研究版本的科学输入”；Task 成功也不足以代表“样本映射正确、可做差异分析、报告已交付”。将这些状态拆开可以表达 PARTIAL、UNKNOWN 和需要人工对账，避免假 READY。

安全决策：项目按现有 owner-only 事实授权；每次复核文件和模块。批准凭证继续使用原 JWT/Redis TTL/CAS 服务。prepare 允许写预案与审计，不产生 Task/文件；execute 在源码门禁前不触碰业务。投递前提交 SUBMITTING，未知队列结果转人工对账，牺牲自动可用性以避免重复副作用。只对已存在 Task 做自动 reconcile，不自动重试下载。

科学决策：分类必须综合内容、来源处理说明、样本映射；整数不能证明 raw counts。未知类型不得经人工用途标签升级。参考、对照和处理组由人明确；RNAFlow 只接收合规 FASTQ，独立 counts Flow 执行固定受限 DESeq2 设计，不把矩阵塞入 RNAFlow。counts Flow 本地验证不替代 Worker/FlowFrame 日志和镜像认证，默认隐藏。

取舍与后续：SHA-256 提供变更检测而非对抗 DB 管理员的签名；64MiB 校验预算当前适合小样本隔离验收，大数据需要专用受控 Worker 验证任务。下载 Worker 的 SSRF/硬预算与真实配额并发、PostgreSQL 迁移、Redis 双消费者、挂载、外部 MCP、报告来源闭环仍是发布阻塞。关闭开关即可撤回入口；不得删除用户文件补偿失败。
