# S4 Reliability Last Gaps

本轮只读盘点与隔离回归完成；**可靠性运行认证 BLOCKED**。依据资料包06、当前2026-10-18 audit与下载活动架构核对现有Task/DownloadService/Repository/Celery机制。未修改共享源码、旧测试或下载门禁，未运行监听服务、PG/Broker/Worker故障实验，未commit/push。

## 基线与证据

主仓HEAD/dirty、递归子仓SHA/dirty、diff SHA及关键源文件/uv.lock哈希见 `evidence/s4-residual/baseline.json`。这是演进中的共享工作树快照，运行验收须重新冻结镜像与源码。命令/退出码与原日志见同目录 `commands.json`，逐ID结论见 `acceptance.csv`。

## 核查结论

- SR01：DownloadService在User行FOR UPDATE后查幂等键/活动intent；TaskRepository.save与Domain submit仍直接flush，没有唯一约束冲突后的业务重读或稳定409转换。历史PG-01的IntegrityError不能视为可恢复客户端契约。API通用异常处理返回脱敏500，但不等于合法重试或业务冲突。真实两PG连接竞争仍BLOCKED。后续应先定位违反的准确unique constraint，在受控savepoint/事务恢复后按owner/project/intent重读，否则返回明确ConflictError；不能吞掉全部IntegrityError。
- SR02：现有别名保全用例只有一个joined键、上限用例两键，未证明三个并发别名。独立离线探针现验证指定Task三个顺序请求返回同ID，行内三项digest与顺序完全匹配。PASS_ISOLATED，真实PG并发BLOCKED。
- SR03：原测试已断言100+5+0及105 unique，但legacy与105并非同场。独立探针同场建立105 queued与101 legacy，完整记录三批ID，断言各批无重复、前两批互斥、并集精确等于全部105 queued且与101 legacy互斥。PASS_ISOLATED；PG多连接skip_locked/公平性仍BLOCKED。
- SR04–SR10：ACK丢失、commit/enqueue窗口API SIGKILL、长Worker离线、长Broker故障、真实600秒Beat、cancel/finalize并发、专属下载Worker身份均BLOCKED。注入OSError/Mock丢ACK、手动reconcile、顺序cancel/finalize、静态schedule==600不能替代这些运行场景。

## 本轮执行

首次 `uv run pytest` 两命令均退出2：默认uv缓存只读，测试未启动，失败日志保留。改用仓库现有 `.venv/bin/python -m pytest`：

- 原S4-A/S4-B0：34 passed，退出0。
- 独立 `evidence/s4-residual/test_residual_isolated.py`：2 passed，退出0，使用原SQLite fixture/服务与dispatch替身，无外网/真实队列。保留完整100+5集合断言源码，不改变旧测试语义。

34与2分别列出，不与旧120矩阵、IAT或其他包统计相加。隔离fixture局部替换门禁是旧测试行为，不修改全局源码常量，不构成运行准入。

## 保留机制与风险

原after_commit仅外层提交派发、savepoint通知快照、queued持久恢复、running保守对账、10分钟cooldown、SQL limit前版本过滤、FileRegistry关联与终态防复活均保留。`transport_call_returned`不证明Broker ACK，Celery succeeded不等于Task success。真实PG/Redis/Broker/Worker/Beat及资源/时限/清理授权未给出，不继承旧环境授权。

回滚仅移除本轮独立探针/报告；原始日志和事实保留。没有服务、数据库或Broker实验资源需要清理，不执行reset/clean/down -v。S4结论不能替代P0A或G3，S6仍NO-GO。
