# Agent Task Link v1

SQL `agent_tool_invocations` 是调用关联与编排投影，TaskService/原 Task 是执行事实。
record = invocation_id → owner_id/project_id/conversation_id/agent_kind/capability_id →
confirmation_id/parameters_hash → task_id。无需新增 Dataset、Artifact 或任务中心。

查询必须同时验证 active principal、owner session、真实 Project.owner、当前模块 scope，
再按 owner/session/project 取关联；task_id 再经原 TaskService 校验 owner。
猜测任务 ID、伪造 X-User-Id、换项目、项目删除/转移不能获取旧记录。项目引用保留 tombstone，
不以目录 slug 或缺失项目推断授权。

状态视图：INSPECTED/AWAITING_APPROVAL/APPROVED/REJECTED/EXPIRED/SUBMITTING/
QUEUED/RECONCILIATION_REQUIRED；运行/终态实时来自 Task，不在关联表自造第二份进度。
PENDING→APPROVED→CONSUMED 与 TTL/CAS 仍由既有确认服务权威管理。
SQL 审批投影更新失败可从 Redis 重新读取；Redis TTL 到期后只能看摘要，不重放批准。

当前所有 execute 在业务副作用前被源码门禁拒绝。隔离测试中的未来适配器使用 SQL
row lock、同 proposal Redis CAS、持久 SUBMITTING reservation。重复已完成 proposal 返回
原 task_id；提交超时/进程退出不自动 retry。不同 proposal 是不同人类审批，不声称对所有
生物学等价参数去重。真实 PostgreSQL 并发和真实队列仍未验收。

人工对账：先冻结相关写入口，按 owner、proposal、request、parameter digest、时间窗口
检查 Task/queue/Worker/日志；若确认 Task 已存在，由受控管理员修复关联并留下审计；如无法
证明未投递，保留 SUBMITTING/RECONCILIATION_REQUIRED，不能让 Agent 再次 submit。
本轮没有提供无审批的“自动解锁/重试”端点。

迁移 `bioopsphase2` 接 `reportauditphase1`，新增表和两个 owner 复合索引；旧 API/表/Task
不改。发布前先在隔离 PG upgrade/downgrade 和 drift 验证；源码回滚保留表和审计事实。
`alembic downgrade reportauditphase1` 会删除本表，必须先保全记录、确认没有在途关联，
本轮未执行任何数据库迁移。关闭 feature flags/callback 即可安全退回原只读科研发现。
