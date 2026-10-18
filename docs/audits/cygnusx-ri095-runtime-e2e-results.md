# RI095 真实运行与 E2E 结果

**BLOCKED：没有 PASS_RUNTIME，没有 PASS_E2E。** Docker socket 返回 operation not permitted。未尝试 Podman、远程 daemon 或权限绕过。依用户规定，停止实际运行，仅交付配置、检查和操作说明。

| Gate | 状态 | 缺失的真实证据 |
|---|---|---|
| 配置与保护检查 | PASS_STATIC | 已离线渲染，六项错误配置拒绝；不算运行验收 |
| RA01 旧模型升级/迁移顺序 | BLOCKED | 实际 SQL、迁移记录、最终数据库状态 |
| RA02 XOR/FK/冻结/旧报告 | BLOCKED | 真实 PostgreSQL 断言与 SQLSTATE |
| RA03 并发/锁/项目保留 | BLOCKED | 8个真实业务 API、advisory lock、删除/停用证据 |
| RA04–06 Celery | BLOCKED | Broker/Worker/Beat、重复投递、中断和恢复日志 |
| HTML/PDF | BLOCKED | Worker 身份、Pandoc/Typst/字体版本、文件 SHA、分页/中文/失败恢复 |
| 私有存储/FileRegistry | BLOCKED | 原子发布/回读/owner/生命周期/配额/漂移/丢失/符号链接/撤权 |
| 对象存储 | BLOCKED | 独立测试 Bucket 授权与配置 |
| 真实 JWT | BLOCKED | 登录、创建、API key 拒绝、跨 owner/项目、停用/撤权重检 |
| M0→Report→M1→ZIP | BLOCKED | 实际制品/成员摘要/partial/旧 M0 与 ZIP 不变证据 |
| Browser 1920/768/390 | BLOCKED | 截图、console/网络日志、下载、交互及恢复场景 |

[证据目录](../../evidence/runtime-acceptance/) 中只保存实际采集的文件。没有伪造截图、SQL 最终状态、PDF、ZIP、JWT 或 Worker 日志。配置拒绝回归使用合成配置，仅测试保护行为。SQLite/jsdom、原有单测与首页探针均不替代运行验收。

完整业务 Playwright spec、精确阶段故障注入及全 RA01–06 自动业务执行器尚未实现；不得称为完整自动化套件。README 提供逐 Gate 执行方法及证据要求。报告阶段当前为 validating/rendering/publishing；collecting 属于导出。空库 head 不能代替旧模型升级，8个 SQL 事务不能代替8个业务请求。静态报告模板不代表全部 BioReport/Quarto 科学验收。

下一阶段须先有可用 disposable Docker、固定镜像、专用用户、批准的既有完成任务/制品 corpus；缺少 corpus 即停止，不能造虚拟 Task/模拟文件。先验证 PG/认证，再 Worker/存储故障恢复，最后 M0/M1/ZIP 与浏览器全链路。每项失败保留证据，最小修复、回归、同场景重跑。当前不建议开放生产写门禁。
