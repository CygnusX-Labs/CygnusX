# 项目科研交付稳定化记录

日期：2026-10-16。PASS_CODE / PASS_ISOLATED；真实环境BLOCKED。原RI06–RI09未重新实施；本轮P0修复来自当前源码审查和可重复隔离负例，**不称为真实运行发现并修复**。

## 起点及局部修复

原链路/8个Job状态/ProjectManifest v1继续复用。基线5个相关测试文件105项通过，PG opt-in因无DSN跳过。起始branch/HEAD/dirty/diff/submodule/flags及原文件见evidence/project-delivery-runtime-ri10。未覆盖其他下载稳定化等并行未提交成果。

1. `ProjectDeliveryService.authorize`绕过User和Project identity map旧值，按当前owner重取Project。None/active/completed/handed_over允许原有读取；其他停用/未知状态明确403 PROJECT_INACTIVE。完成或移交不等于停用。
2. `download`验证Frozen Manifest摘要、owner/project，再核Task→Version→Link及Report版本/快照/Observation关系。ready只代表曾发布，关联后来漂移时拒绝下载，不静默换入新内容。
3. RI10读取器在单元格读取后刷新FileRecord，复核当前owner/Task/personal/lifecycle及已登记SHA；再次原Provenance采集与该SHA匹配。防止同一Session缓存已停用结果记录。
4. 原DEG TSV读取器拒绝行列数不齐的记录，保留原重复列/重复feature、非有限数值和NA处理。合法已有表兼容；畸形行从可能被忽略收紧为STATISTICAL_TABLE_INVALID。

当前16MiB单文件、64MiB payload、500文件、80MiB ZIP保持；不新增无限流式或分页引擎。冻结范围超过原Provenance上限仍拒绝EXPORT_LIMIT。大项目下一步应采用owner/project限定keyset分页、显式Version/Task选择及完整页集合digest；页水位变化重预览，不以截断集合冒充全项目。

## API与契约

原导出端点和ProjectManifest schema不变。新增两个只读接口：现有research-evidence路由的POST claim-provenance（RI10），以及原导出Job的GET summary-preview（只读HTML原型）。既有Gateway命名及下载/分析写门禁不变，没有新MCP或Agent创建入口。

ClaimProvenance为独立投影契约，不把新增默认字段塞进旧ReportSnapshot/ResearchProvenance。原报告HTML renderer仅抽取共享CSS帮助函数并增加原型函数；同一合成快照的旧/新审计HTML已做逐字节相等及SHA比较，兼容证据在quality/legacy-renderer-compatibility.json。

## 文件范围

增量修改：project_delivery_service.py、research_claim_service.py、report_audit_renderer.py、api/v1/research_claims.py、api/v1/research_delivery.py、frontend/api/projectDelivery.ts、ProjectResearchDelivery.vue及对应组件测试。

新增：schemas/claim_provenance.py及两份JSON Schema、frontend/api/claimProvenance.ts、ClaimEvidencePanel.vue、面板测试、test_claim_provenance_ri10.py、test_project_summary_prototype.py、test_project_delivery_stabilization.py，以及本轮四份文档和架构增量说明。无模型/迁移/锁文件/子模块改动，没有改Frozen Manifest/ReportSnapshot/Observation内容。

## 测试与未通过项

最终选择范围、退出码、JUnit及源码摘要以evidence目录checks.json为准。测试包括缓存失活、ready后关系漂移、精确/超限预算、commit/ACK异常保留queued、DEG单元格/历史版本/解释分层、HTML原型、真实临时文件、ASGI与jsdom。

最终13个后端选择文件215项通过（其中本轮新增21项）；前端3个文件13项通过，类型检查及构建退出0。6源文件mypy及所选Ruff通过，同范围旧6源文件shadow baseline/current均0诊断。Schema与模型一致，原Claim schema源文件未变。旧审计HTML相同快照的前后SHA完全一致；上述通过仅限代码/隔离层。

SQLite不是PG；Broker/ACK故障是显式替身；线程读取使用既有inline_file_capture适应沙箱唤醒限制。没有Worker强杀、PG并发业务API、真实存储、真实JWT或浏览器通过证明。本轮不宣布全仓质量通过；既有全仓Ruff/mypy和聊天/协作室前端失败记录不能由选择范围绿灯覆盖。

## 长期保留、停用与删除

Job/Manifest、requests别名、FileRecord、ReportFile、ReportSnapshot/Observation是不同生命周期：FK RESTRICT及不可变trigger保护部分关联，不意味着对象存储WORM、软删除保护或长期字节可得。source=report归档无自动cleanup期限；用户停用FileRecord后ready记录仍保留，当前下载可以拒绝。

建议分为活跃项目、完成/移交、停用、归档保留和经批准删除。当前停用拒绝在线读取，不能通过旧Job下载绕过；未来只读冷归档需单独明确权限/owner转移/合法保留策略。不得把completed误当停用。保留期限由机构/项目负责人批准，不擅设90天或自动清空。

长期方案优先复用原文件生命周期，增加经审核的hold/到期策略和私有归档盘点；保留Manifest/请求/审计和必要来源tombstone。原件迁冷时先验证新后端SHA/大小、保留可用引用，不能原地替换历史事实。对象锁、签名和独立副本若需要须核实部署能力；当前都未认证。项目/账户删除要先完成保留评审，不能绕过RESTRICT删Job表；即使关闭功能也不删除证据。

## 回滚

默认flags维持false。先停止新投递，按本轮baseline逐hunk撤增量；不得整文件checkout/reset/stash。保留所有已写Job/Manifest/别名/ZIP/FileRecord和原报告快照。无本轮迁移，不做生产downgrade。两项只读接口与组件可成组撤回；共享CSS帮助函数与旧renderer成组回退。已冻结数据不重写，下载门禁与当前权限检查不得为恢复演示而放宽。
