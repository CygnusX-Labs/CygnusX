# S4-B0 Download Reliability Hardening & Recovery Contract

日期：2026-10-17。本轮限定范围 PASS_ISOLATED；真实 PG、Redis、broker、Worker 与 OS supervisor 为 RUNTIME_BLOCKED / NOT_TESTED，无 PASS_RUNTIME。

## 1. 基线与代码复用

HEAD：51011118535f782f5282f638b4a54649c79bf6d6。基线工作树清单见 evidence/download-s4b0/status-before.txt。依据 [S4-A 报告](download-s4a-task-reliability-implementation.md) 与[下载架构](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)。复用 DownloadService、TaskService、TaskRepository、dispatcher/Celery、FileRegistry、DatasetImportService，无新任务系统、队列、表或迁移。

## 2. S4-A 机制核实

外层 after_commit 发布、savepoint 不发布、rollback 不发布、queued 持久恢复、queued→running 原子领取、owner/project 绑定、FileRegistry 实测 SHA/配额和取消事实分离均已存在。S4-A 原 16 项与登记回归本轮继续通过；不把隔离 SQL facade 当作真实 PG 并发。

## 3. 新发现的实际问题

扫描先 limit 100 再跳过历史行，101 个旧行会永久阻塞有效 queued；Session.close 后 info 残留通知；重复取消报错；别名无上限且旧 Worker 实体可能覆盖新别名/登记/恢复事实；首次显式键任务结束后无键请求不能复用；SQL rollback 后目录缺少归属提示。提交后异常边界也需加强。

## 4. 红测与修复依据

red.txt 记录 3 failed：旧行饥饿、重复取消、Session close 残留。修复后与 S4-A 合跑 19 passed，见 green-first.txt。其余测试针对代码审查发现的缺口补充，未声称均有修改前红测。expanded.txt 的旧 Service 3 项失败来自所有查询都返回 User 的替身，现按查询实体区分结果，保留原断言。

## 5. 修改文件及函数

源码路径相对 src/cygnusx：infrastructure/download/reliability.py 的 dispatch_download、_committed、_transaction_ended、reconcile_download_tasks；application/services/download_service.py 的 submit；application/services/task_service.py 的 cancel_task；infrastructure/database/repositories/task_repository.py 的 save；tools/download/config.py 的 DownloadReliabilityConfig；infrastructure/celery_app/tasks/download.py 的领取日志。新增 tests/unit/test_download_s4b0_reliability.py，调整 test_download_service.py 的查询替身。另更新本文、下载架构与罗盘；整文件既有 diff 不全属于本轮。

## 6. 提交与队列一致性

导入和原 dispatcher 发布异常均转 deferred；after_commit 再兜底，避免把已提交事实误报为 rollback。通知发布前 pop；outer transaction end 包括 close 清理残留。外层提交、savepoint、rollback 与 commit failure 测试保留。HTTP 返回异常重试依原幂等找 Task；原子领取保护重复消息，恢复不依赖原请求 Session。

不新增 Outbox：queued Task 是原有持久待投递事实。至少一次发布加保守领取，不承诺 exactly-once。同步发布可能增加提交返回延迟；真实 ack 丢失/网络超时需 B1，隔离用例覆盖提交后异常和重试复用。

## 7. 幂等与别名治理

保留规范意图摘要、唯一 idempotency_key、owner/project 隔离、同键变参拒绝、活动意图复用和新显式键终态重试。无键请求现在也查本版本相同摘要，复用首次显式键的终态；窗口为 Task 保留期。

别名候选只查本版本当前 owner 的键列表字段，再精确确认成员。reliability.max_request_keys 默认 64，可配置 1–1024；达到上限报 DOWNLOAD_REQUEST_KEYS_LIMIT，已有键仍可复用，不截断或遗忘绑定。旧 Worker save 在原 Task 行锁内保留数据库维护的别名、可靠性、登记、恢复和取消事实。

User 行锁仍串行化同 owner 提交。没有性能测量证据，本轮不替换锁。后续最小优化候选为 owner/project/意图和请求键事务锁，须固定顺序并先做 PG 死锁/多连接测试。单 Task 别名有界，但历史任务增长的 JSON 查询成本仍需执行计划评估，未声称查询已有索引优化。

## 8. 恢复扫描与公平性

SQL 在 limit 前过滤 version=1，按 updated_at、id 排序，FOR UPDATE SKIP LOCKED。持久更新 updated_at、last_recovery_attempt、recovery_attempts，提交后再发布。101 个历史行不再阻塞，105 个有效任务三轮结果为 100/5/0。

保留 600 秒 beat、10 分钟冷却、100 行批次，无新游标/调度平台。固定冷却限制失败重试频率；提交后崩溃最多增加一轮等待。扫描 commit 失败不发布，rollback 后 queued 仍可选。running 只标不确定，不自动重跑；慢任务和历史行不重放，终态不扫描。真实多扫描器竞争需 PG。有限积压可轮转，不承诺无限持续输入下固定等待上限；updated_at 被其他写入刷新可能延后恢复，B1 核查实际写入来源。

## 9. 工作目录归属

保留原子 mkdir、O_NOFOLLOW、独立可读标签/时间/序号目录。预分配 Task ID，并独占创建 .download-task.json，记录版本、Task ID、owner 和意图摘要；Task 使用同 ID。UUID 不进入用户可见目录名，凭据不含 URL、token 或路径。

rollback 后 marker 仅为归属提示，不是提交或执行批准；隐藏控制文件被原 S1 规则排除登记。文件可被篡改，必须只读核对真实 Task.work_dir、owner、摘要与 FileRecord，缺失或冲突为 UNKNOWN，不能据 marker 单独授权删除。marker 创建失败目录也保持未知。本轮无自动清理、无按文件名猜历史归属、无删除用户内容。

## 10. 取消与晚到状态保护

下载取消在原 Task 行锁下重读；CANCELLED 直接返回原事实，不重复进入退款等后处理。FAILED 不被旧 SUCCESS 覆盖；取消后 finalize 返回 false 并记录 RECONCILIATION_REQUIRED，保留部分文件。SQLite 覆盖顺序交错，真实取消/finalize 并行锁竞争归 B1。

request_accepted=true、process_tree_stopped=false、egress_revoked=false、reconciliation_required=true 分离。无 Supervisor 回执，不伪造停止或出口撤销；不 kill 全 Worker。既有 FileRecord 和配额事实保留，取消不撤销已发生登记。已取消 Task 的重复 Worker 消息不领取。

## 11. FileRegistry 回归

保持 Task→FileRegistry→FileRecord→Dataset。真实登记、SHA/size、owner/task/source、幂等扣配额、登记失败 savepoint、部分产物及链接拒绝测试通过；不手填关联。Repository 防止旧实体覆盖登记投影，不自动提升 scientific_ready。

## 12. 测试证据

证据目录 evidence/download-s4b0/。delivery-regression.txt：252 passed / 1 warning，8.19s，集合 tests/unit/test_download*.py 与 test_dataset_import_handoff.py，参数 -q -m 'not quarantine' --tb=short。最终完整回归包含 FAILED 晚到成功和恢复 commit 失败两项；final-focused.txt 共 12 passed / 1 warning，0.67s。集合重叠不累加。

命令前缀 LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib .venv/bin/pytest。ruff.txt 聚焦检查通过，migrations.txt 迁移链通过。mypy.txt 四个源码文件仍有原 TaskRepository dict/Row 的 5 项泛型错误，不宣称全仓绿。使用真实业务/SQL facade/临时文件，隔离 broker 与执行器；复用 S1 沙箱唤醒 fixture。Pydantic warning 和退出后存量 OTel/Loguru closed-stream 日志保留。

## 13. 未完成的运行验证与可观测性

真实 PG/Redis/broker/Worker/监督器均 RUNTIME_BLOCKED / NOT_TESTED，本轮未试写默认服务。新增安全日志 download.enqueue 的 Task/outcome、download.claim 的 Task/outcome、download.recovery 的 Task/owner/project/digest/status/attempt。last_recovery_attempt 是持久扫描尝试，不代表 broker ack。原 Task 状态、取消/登记投影和 FileRecord.task_id、checksum/size 支持关联文件数与校验事实，不另建审计。日志不输出 URL、token、凭据或目录；真实采集/关联查询留 B1。

## 14. 回滚与兼容性

无迁移，新 config 有默认值。旧任务不自动重放，旧目录无 marker 不猜归属；已有超上限别名仍可读取，仅拒绝新别名。逐 hunk 回退查询、Session 清理、取消幂等、元数据保留、marker、配置及日志，不整文件 reset/checkout，不删除 Task、文件、配额或审批事实。回滚可能恢复扫描饥饿等缺陷，应评审。

## 15. S4-B0 验收结论

限定范围 PASS_ISOLATED。真实运行仍 RUNTIME_BLOCKED，无 PASS_RUNTIME。DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False、WRITE_RUNTIME_ACCEPTED=False、DOWNLOAD_EXECUTION_READY=FALSE。未真实下载、启动未授权 Worker、操作生产数据库、提交、推送、部署或清理历史数据。

## 16. S4-B1 最小环境与验收清单

需明确授权的隔离 PG 角色/数据库、Redis、原 broker、固定版本 Celery Worker/beat、测试挂载和可用 IPC，数据生命周期与清理范围明确。Supervisor 验证需要可信单 Task 进程树/出口回执。

1. PG 多连接提交、别名写入、owner/project、同键变参与终态重试；量测 User 锁等待，验证 JSON 查询语义和执行计划。
2. commit 前后崩溃、发布接收后丢 ack、发布超时与 HTTP 断开，核对 Task 唯一性与重复消息。
3. 两扫描器 SKIP LOCKED、跨批次积压/持续输入、broker 故障冷却与恢复、扫描事务失败。
4. beat/Worker 重启，queued 不漏、running 不重跑、慢任务与取消不误恢复。
5. cancel/finalize 双连接竞争、退款/配额、真实 FileRecord SHA 与部分文件；禁止凭 CANCELLED 宣称 OS 已停。
6. 目录冲突、rollback marker、挂载权限/链接攻击与只读归属核对，检查日志脱敏和证据关联。

本轮完成后停止，不自动进入 S4-B1；不因隔离通过解除执行门禁。
