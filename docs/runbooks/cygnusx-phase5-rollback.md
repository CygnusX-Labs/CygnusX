# Phase5 关闭与回滚说明

状态：未部署，未在业务 PostgreSQL 应用迁移，未创建真实科研业务任务。以下是供人工验收的操作说明，不表示已执行。

## 功能关闭

`core/config.py` 的 `research_plan_enabled` 默认 False。保持关闭并按现有服务发布流程重新加载配置后，新 ResearchPlan 路由与共享规划工具拒绝访问。关闭不删除已有研究计划元数据，不影响既有 Task/Report。不要修改 `WRITE_RUNTIME_ACCEPTED=False` 或 Phase4 开关来绕过历史运行门禁。

如已经启用，先停止新调度并核对所有 RUNNING/SUBMITTING/RECONCILIATION_REQUIRED 计划。暂停计划只停止后续协调，不取消真实 Task，不删除 Dataset、文件或报告。不确定调用按 Invocation/request_id/owner/project 对账，不能通过重投验证是否执行。

## 代码恢复

本次尚无提交 ID；以验收后的单独逻辑提交为回滚单位。恢复前保存计划导出及当前 diff，确认工作树归属。使用经审核的 revert 保留历史，不执行 reset --hard、git clean 或批量 checkout；`.env.example`、既有子模块和 `docs/info/26.10.15` 不属于本次变更。

## 数据库迁移恢复

新迁移 `bioopsphase5` 的父版本是 `bioopsphase4`，仅新增 `research_plans` 及本表的不可变 trigger/function。SQLite 的 upgrade/downgrade 测试不证明 PostgreSQL 兼容。实际部署前必须在隔离 PostgreSQL 保存原有数据、升级、验证约束和 downgrade，再保留完整证据。

若未来确已应用：关闭入口，停止协调并备份 `research_plans`、审批和事件关联；先检查 Alembic 当前版本与后继依赖。仅在无后继依赖并获得数据库维护授权后，由维护者执行 downgrade 至 `bioopsphase4`。downgrade 会删除本轮计划历史，必须先完成归档；不能删除实际 Task、Dataset、Artifact、Report 或既有幂等记录。禁止在本轮直接操作生产数据库。

## 恢复核验

确认计划接口关闭、共享 catalog 不再暴露计划能力、原聊天/发现/分析/报告功能保持原合同。核对已有资产数量和 ID、审计归档、迁移单 head。任何未知投递保持人工对账，不自动重试分析。重新启用前重做 G0/G15、独立写审批与全栈验收。
