# S4 Reliability Last Gaps

本轮源码增量与隔离回归完成；**可靠性运行认证 BLOCKED**。依据资料包06、当前2026-10-18 audit与下载活动架构核对现有Task/DownloadService/Repository/Celery机制。仅修改原 TaskRepository 与 DownloadService 的精确幂等冲突处理及对应 S4-A 单测；未新增 Task/队列、未修改下载门禁，未运行监听服务、PG/Broker/Worker故障实验，未commit/push。

## 基线与证据

主仓HEAD/dirty、递归子仓SHA/dirty、初始diff SHA及关键源文件/uv.lock哈希见 `evidence/s4-residual/baseline.json`。SR-01 实施后当前 HEAD 与三个变更文件 SHA 单独记录在 `evidence/s4-residual/sr01-source-hashes.json`；这是演进中的共享工作树快照，运行验收须重新冻结镜像与源码。命令/退出码与原日志见同目录 `commands.json`，逐ID结论见 `acceptance.csv`。

## 核查结论

- SR01：`TaskRepository.save()` 仅对下载 Task 的 `uq_tasks_idempotency_key` 精确唯一约束冲突做保存点恢复并转成专用异常；`DownloadService.submit()` 将其映射为稳定 `409 DOWNLOAD_REQUEST_CONFLICT`，并仅清理本次 marker 匹配且空的工作目录。其他 IntegrityError 不转换。SQLite 隔离用例验证数据库唯一冲突可恢复、Task 行保留，以及服务层 409/不派发/空目录清理。两个 PostgreSQL 连接竞争及提交后查询重试仍 BLOCKED，故只记 PASS_ISOLATED。
- SR02：现有别名保全用例只有一个joined键、上限用例两键，未证明三个并发别名。独立离线探针现验证指定Task三个顺序请求返回同ID，行内三项digest与顺序完全匹配。PASS_ISOLATED，真实PG并发BLOCKED。
- SR03：原测试已断言100+5+0及105 unique，但legacy与105并非同场。独立探针同场建立105 queued与101 legacy，完整记录三批ID，断言各批无重复、前两批互斥、并集精确等于全部105 queued且与101 legacy互斥。PASS_ISOLATED；PG多连接skip_locked/公平性仍BLOCKED。
- SR04–SR10：ACK丢失、commit/enqueue窗口API SIGKILL、长Worker离线、长Broker故障、真实600秒Beat、cancel/finalize并发、专属下载Worker身份均BLOCKED。注入OSError/Mock丢ACK、手动reconcile、顺序cancel/finalize、静态schedule==600不能替代这些运行场景。

## 本轮执行

首次 `uv run pytest` 两命令均退出2：默认uv缓存只读，测试未启动，失败日志保留。改用仓库现有 `.venv/bin/python -m pytest`：

- S4-A：23 passed，退出0（含新增精确唯一约束冲突、非目标约束不误分类与稳定409隔离回归）。
- S4-B0：14 passed，退出0。
- 独立 `evidence/s4-residual/test_residual_isolated.py`：2 passed，退出0，使用原SQLite fixture/服务与dispatch替身，无外网/真实队列。保留完整100+5集合断言源码，不改变旧测试语义。
- S4-A/S4-B0/独立探针联合复跑：39 passed，退出0；原始日志 `evidence/s4-residual/sr01-isolated.log`。
- 相关 Ruff 检查通过；`download_service.py` 与 `task_repository.py` 的 mypy 通过，日志见 `evidence/s4-residual/sr01-static-checks.log`。

隔离结果不与旧120矩阵、IAT或其他包统计相加。SQLite 只证明明确唯一冲突分支及保存点行为，不证明 PostgreSQL 锁竞争、等待后重读或 API 端到端并发；隔离fixture局部替换门禁是旧测试行为，不修改全局源码常量，不构成运行准入。

## 保留机制与风险

原after_commit仅外层提交派发、savepoint通知快照、queued持久恢复、running保守对账、10分钟cooldown、SQL limit前版本过滤、FileRegistry关联与终态防复活均保留。`transport_call_returned`不证明Broker ACK，Celery succeeded不等于Task success。真实PG/Redis/Broker/Worker/Beat及资源/时限/清理授权未给出，不继承旧环境授权。

回滚仅移除本轮独立探针/报告；原始日志和事实保留。没有服务、数据库或Broker实验资源需要清理，不执行reset/clean/down -v。S4结论不能替代P0A或G3，S6仍NO-GO。
