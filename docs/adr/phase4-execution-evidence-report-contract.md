# ADR：Phase4 执行关联、结果观察与双报告

状态：代码采用，运行验收 BLOCKED。

## 决策

复用既有 DatasetVersion/Frozen Handoff、TaskService、FileRegistry、ReportService 与不可变 ReportSnapshot。AnalysisLink 在 prepare 保存 Flow/标准化参数摘要；最终提交及 Worker 复查，actual Task/link 在入队前提交。投递不明留给对账，不自动提交第二次分析。

新增 ResultObservation 作为真实 manifest/文件采集的追加证据，不作为工作流或任务状态机。其 owner/project/link/task 外键不级联删除；唯一事实摘要串行化幂等登记。旧 Task 无该关系时明确未知；历史软件环境不回填。

科学报告与执行证据报告使用独立 ReportModel 和独立既有 generation job template。Counts BioReport 固定受控模板只读取完成的表格；报告失败不触发分析任务。已有科学 HTML 可复用；丢失科学报告修复产生新版本/新归档。执行证据快照只增不改；缺失 HTML 仅能从原快照恢复匹配原 SHA 的字节，损坏归档或不能精确重建的格式交人工恢复。

## 取舍

读取会实际复核小数据文件，受字节/数量/时间预算限制；不是规模化索引服务。默认关闭，未接受 Worker 镜像/release 证据时保留 PARTIAL，因此当前不会只凭 manifest 自证 READY。没有引入新的下载器、运行引擎、Agent shell/DB 写权或平行报告中心。

SQLite 不能证明 PG 事务、advisory lock、trigger 并发与 Celery 交付语义；运行 Gate 必须单独验收。未来若提供 execution-time attestation，应以真实 Worker 观察与可信摘要另行评审，不能删除缺口常量充当验收。
