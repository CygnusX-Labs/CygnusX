# RI095 D1：项目报告来源兼容决策

选择 B：最小项目来源/Job 身份。旧 reports、report_snapshots、report_generation_jobs 不放宽 task_id、不回填项目、不伪造 Task。此决策先于模型实施；不是运行认证。

证据：report.py 中 ReportModel.task_id、ReportGenerationJobModel.task_id、ReportSnapshotModel.task_id 均 NOT NULL；起点 ReportFile 的 report_id 强制指向 reports；本轮按文末产物适配追加互斥来源。ReportRepositoryImpl.get_by_task_id、ReportService 的列表/版本/下载/删除、reproducible_report_service 的 task/template 活跃唯一键及 reports worker 的 Task 取证直接依赖这些身份。scientific_report_job 仍是 Counts Task 渲染路径。直接选 A 会把 nullable Task 传播到既有 API DTO、快照、锁、保留与 Worker，而当前并无该兼容证据。

项目身份仅保存 owner/project/M0/冻结选择/模板版本/状态及发布文件引用；不复制取证引擎、FileRegistry、存储或分析调度器。冻结数值复用 ResearchClaimService.provenance；授权复用 ProjectDeliveryService.authorize/validate_associations；后续发布必须适配 ReportService 及现有原子发布能力。最小身份不应被称作已经完成的正式报告。

迁移边界：后续仅追加项目来源/Job 以及必要产物关系，使用 RESTRICT FK、服务层 owner/project 归属复核、请求和源摘要复合唯一约束；不可让项目文件依靠不存在的 ReportFile 外键。选 B 仍需明确产物适配并完成 SQLite 迁移/旧报告回归后才能宣称 P1 完成。PG CHECK/FK/锁/触发器须显式 opt-in 测试库验证。

回滚：关闭新增入口/Worker 准入，保留追加身份、文件和 M0/M1；不删除历史科研证据，不修改旧迁移/索引/Manifest v1 摘要。当前没有执行迁移或修改业务数据。基线见 evidence/ri095-project-report-phase1-4/baseline.json 与 baseline-sha256.json。

产物适配补充：复用 ReportFileModel，增加 nullable project_report_job_id，report_id 改为 nullable，并用 XOR CHECK 强制二选一。Task Report/Job/Snapshot 的 task_id 仍 NOT NULL。旧 reports.files 关系和下载仍限定 report_id；项目文件只经新项目授权入口读取。此处不建立第二套文件注册表。迁移需以 batch alter 支持 SQLite，并验证旧文件关联、两源均空/均有拒绝。
