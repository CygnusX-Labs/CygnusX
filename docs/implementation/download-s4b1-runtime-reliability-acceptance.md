# S4-B1 PostgreSQL / Celery / Broker Reliability Acceptance

日期：2026-10-17。**S4-B1 = RUNTIME_BLOCKED**。B1-0 环境准入未通过；按任务要求输出最小环境需求，停止运行阶段。无 PASS_RUNTIME / PASS_E2E，不新增 Mock 测试代替运行验收。

## 1. 真实环境与版本

HEAD：51011118535f782f5282f638b4a54649c79bf6d6。既有工作树清单见 evidence/download-s4b1/status-before.txt；脱敏探针见 environment.json。项目 .venv 客户端版本：SQLAlchemy 2.0.51、Celery 5.6.3、asyncpg 0.31.0、redis 5.3.1。默认 Python 环境与 .venv 不同，不能互代；这些不是服务端版本。

TEST_DATABASE_URL、E2E_DATABASE_URL、TEST_REDIS_URL、REDIS_TEST_URL、TEST_BROKER_URL、CELERY_TEST_BROKER_URL、S4B1_DATABASE_URL、S4B1_BROKER_URL 均未提供。仅检测存在性，未打印凭据或读取 .env。没有明确授权的专用数据库/角色、Broker、Worker/Beat、测试用户/项目及目录清理范围清单。PATH 未找到 postgres、redis-server、rabbitmq-server，不推断远端或其他目录一定不存在。docker/celery 客户端存在不代表获授权实例。

TCP loopback 和 Unix socket 的 bind/listen 均返回 errno 1 Operation not permitted。Unix socket 对象仅创建曾成功，随后绑定仍失败，不能据此认定 IPC 可用。探针仅使用并释放自身临时目录。未连接默认业务数据库、Broker 或容器；服务端版本、Worker 源码一致性、任务注册、权限和额度均未验。

## 2. 修改文件

仅新增本文及 evidence/download-s4b1/environment.json、status-before.txt，并在罗盘登记链接。无生产代码、配置、测试、迁移或部署修改。证据目录是本地资料，不保证随 Git 分发。

## 3. PostgreSQL 并发结果

NOT_TESTED / RUNTIME_BLOCKED。未建立多连接事务，User 锁、唯一约束、别名并发、死锁、元数据保护及最终数据库状态均未验证。事务数、并发数和锁等待没有实测值，不能填零冒充结果。

## 4. Broker 故障矩阵

真实 commit/rollback/savepoint、commit 异常、enqueue 失败、接收后丢确认、发布超时、HTTP 中断及提交后发布前退出均 NOT_TESTED。已有替身证据不升级为真实通过；保持至少一次语义，不宣称 exactly-once。

## 5. Worker 重复执行测试

NOT_TESTED。未启动 Worker、发布消息或执行下载子进程；重复投递/消费对领取、目录、配额和 FileRecord 的真实影响待验。

## 6. Beat 恢复扫描结果

NOT_TESTED。未运行 Beat/双扫描器。101 旧行加有效任务、105 有效行、持续输入、长期 Broker 故障、慢 running 与双 Beat 场景均待验。100 行批次、10 分钟冷却、600 秒周期及 SKIP LOCKED 只有既有代码/隔离证据。

## 7. 任务幂等测试

本轮 NOT_TESTED。同键同参/变参、异键活动意图、跨 owner/project、无键终态、显式重试、别名上限和并发别名写入均待真实 PG 验证。未测 JSON 执行计划，不凭猜测更换 User 锁。

## 8. 取消及晚到状态

本轮 NOT_TESTED。重复取消、CANCELLED/FAILED 防迟到 SUCCESS、不重新领取及取消/finalize 竞争待验。cancel_requested、cancel_accepted、process_tree_stopped、egress_revoked、reconciliation_completed 是不同事实；没有 Supervisor 回执，不声称 OS 停止或出口撤销。

## 9. FileRegistry 对账

本轮 NOT_TESTED。未登记本地业务文件、扣配额或创建资产。Task/owner/project/source、实测 SHA/size、幂等登记、失败回滚、部分产物与 Dataset reconcile 均留待授权环境；scientific_ready 不提升。

## 10. 工作目录归属

本轮 NOT_TESTED。未分配业务目录或清理历史文件。目录冲突、并发、rollback、marker 缺失/冲突、链接/替换、旧目录和未知文件均待验。marker 只能辅助只读核对，不能授权删除、恢复或下载。

## 11. 可观测性证据

本轮只有脱敏环境探针，未取得真实 request_key/digest、Task/owner/project、enqueue/Broker/claim/recovery、取消、FileRecord/SHA 的运行关联日志。last_recovery_attempt 等真实采集与日志脱敏待验。不打印 URL、token、凭据或环境变量值。

## 12. 性能与锁等待数据

扫描耗时、锁等待、恢复延迟、重投次数、持续输入等待上限、故障期间写量及 JSON 执行计划均 N/A（未测）。不以 SQLite 耗时推断 PG 性能，不调整频率和锁设计。

## 13. 未通过范围与最小环境需求

B1-0 未通过，B1-1 至 B1-6 全部 NOT_TESTED / RUNTIME_BLOCKED。至少需要：

- 明确非生产 PG 地址、专用数据库/角色、版本、迁移/测试写权限和清理范围，不能使用默认业务库。
- 实际隔离 Broker 的类型/版本、专用 vhost 或 Redis DB、队列/账号/额度；如需独立 Redis 一并说明。允许有界故障注入且不影响生产。
- 与当前工作树一致的独立 Celery Worker/Beat、源码修订及工作树摘要、配置来源、任务注册和专属队列，只消费本轮测试任务。
- 可用 TCP/Unix IPC、进程管理及受控故障注入；无需高权限网络组件。
- 独立用户/项目、专属受管目录、配额测试数据、磁盘/连接/消息/时长额度、生命周期与清理责任。
- 脱敏日志和证据目录；停止语义需要可信单 Task Supervisor 进程树/出口回执。

凭据通过受控配置注入，不要求在聊天正文发送密码。变量存在也不单独证明授权，必须明确用途和隔离范围。

## 14. 回滚方案

仅撤回本轮报告、证据和罗盘链接，无程序/数据库/Worker/Broker 回滚。不整仓 reset/clean，不删除用户文件或已有 Task。无提交、推送或部署。

## 15. S4-B1 验收结论

**RUNTIME_BLOCKED**。已完成本轮规定的环境核验、最小需求与停止交付，真实验收未完成。原 S4-B0 PASS_ISOLATED 不变，不引用历史测试数字充当本轮结果。DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False、WRITE_RUNTIME_ACCEPTED=False、DOWNLOAD_EXECUTION_READY=FALSE。

## 16. G3 与 S6 剩余阻断

G3 仍 PARTIAL_CODE / RUNTIME_BLOCKED：受信执行、真实出站/硬预算、进程树与出口停止、逐协议认证仍未完成。S6 不自动准入，还需 B1 真实可靠性及 S5-C2 PG/Redis/Node/浏览器运行证据，按能力评审。当前停止运行阶段，不新增平行测试框架或大型调查。
