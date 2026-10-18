# ADR：寻宝鼠复用共享工具及科研交付

2026-10-16；已实施只读与 Prepare 接线，真实执行与发布 BLOCKED。

保留 FullPresentation、原 DatasetCard/ChatMessage 和 Node 检索循环。新增原样式 ResearchWorkflowPanel 仅负责呈现和 typed callbacks，Vue useResearchWorkflow 负责平台请求。所有业务 prepare/inspect 进入既有 AgentToolGateway，Node delegated callback、ToolBridge/MCP 与网页调用落同一服务。

只对 dataset.discover 放宽 project 为 optional；所有持久 prepare 仍需已授权项目。默认开关不变，WRITE_RUNTIME_ACCEPTED 与 worker_paths_verified 不变。下载、导入共用一个 Import 预案；分析独立批准。现有 Analysis REST 缺失 reject，最小复用 ToolConfirmationService.reject 补齐，不新增确认存储。状态恢复增加安全 dataset/version/expiry 引用；不暴露内部路径给 Island。

任务及双报告只读取真实引用。报告生成失败仍由现有交付 Job 处理，本轮不启动分析或报告任务。不能以本次 DOM/SQLite PASS 替代 PG、Redis、Worker、MCP transport 或浏览器验收。回滚关闭新动作接线，保留原展示与所有持久科研记录，具体见实施报告。
