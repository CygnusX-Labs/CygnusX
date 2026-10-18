# 项目科研交付真实运行验收

核查日期：2026-10-16。结论：**BLOCKED，未完成真实运行验收**。本报告不是生产准入凭证。源码复核、SQLite、替身Broker、ASGI及jsdom结果分别记PASS_CODE/PASS_ISOLATED，均不提升为PASS_RUNTIME或PASS_E2E。

## 实际环境与停止点

已记录分支、HEAD、原脏工作区、完整diff、子模块、相关源码起点和Feature Flags：`evidence/project-delivery-runtime-ri10/`。没有reset、clean、checkout、stash、提交、推送或部署。报告中的旧成果不替代本轮当前源码检查。

| 项目 | 本轮权威观察 |
|---|---|
| Git | feat/research-agent-phase5，HEAD 51011118535f782f5282f638b4a54649c79bf6d6；大量已有未提交成果保留 |
| 独立PG | PROJECT_EXPORT_TEST_DATABASE_URL未提供；不读取或连接生产DATABASE_URL |
| PostgreSQL服务版本/实际表状态 | UNKNOWN；没有运行alembic current、线上schema查询或测试迁移 |
| 本地库声明版本 | Celery 5.6.3、redis客户端5.3.1、asyncpg 0.31.0、SQLAlchemy 2.0.51；不是服务端/Worker版本证明 |
| 测试Broker/Redis/Celery Worker | 未明确授权地址、namespace、队列和Worker；不启动或探测默认服务 |
| 测试存储 | 未提供授权的测试卷/bucket；真实类型UNKNOWN，SQLite测试使用临时本地文件 |
| 当前flags | project_export_enabled、research_delivery_read_enabled/write_enabled、research_plan_enabled及Agent下载/分析写均为false |
| 浏览器 | Playwright模块不可用；实际Chromium两次启动均退出46，Snap不能在只读/run/user/1000下创建运行目录，临时XDG_RUNTIME_DIR未解决 |
| 浏览器截图 | 未产生；没有用jsdom截图或模拟页面充当真实浏览器证据 |
| 实际科研项目ZIP/真实下载SHA | 未产生；测试确有真实临时ZIP及独立离线校验，但不属于真实环境科研交付验收 |

环境证据为runtime-inventory.json、browser/probe.log、chromium-launch.log及chromium-writable-runtime.log。没有提供专用DSN时，现有PG opt-in测试明确跳过；这项结果必须记BLOCKED，不能算PG通过。

## 迁移与并发审查

当前`projectdelivery01_project_exports.py`定义Job、请求别名、FK、两个去重维度及Frozen Manifest trigger；模型已注册。静态迁移链检查通过，但没有确认真实PG版本兼容、实际FK/索引/trigger或归档关联是否已部署。未提前执行迁移。

原PG opt-in用例覆盖实际migration、唯一约束、trigger和Project锁下8个SQL事务。**它不是8个真实业务CREATE API并发验收**。不能凭它或SQLite重复提交结果宣布4.3完成。获得专用环境后，还需用实际ProjectDeliveryService/API及两个独立连接以上同时提交8请求，分别覆盖相同/不同request_key、同manifest/不同manifest、别名重用冲突，直接检查最终jobs/requests表与FileRecord，不只比较HTTP结果。

Project行锁用于CREATE范围及幂等事务；Worker使用独占连接上的PG session advisory lock，跨阶段commit保留互斥。源码采用NullPool短生命周期引擎并在finally解锁/dispose；这只是代码审查结果，尚未证明强杀时连接释放、第二消费者恢复及Broker的实际行为。

## RA矩阵

| ID | 代码/隔离证据 | 真实运行状态及缺少项 |
|---|---|---|
| RA01 迁移 | 现有SQLite真实upgrade、链静态检查 | BLOCKED：没有专用PG |
| RA02 FK/唯一/trigger | 模型、迁移和原opt-in用例已核对 | BLOCKED：PG trigger/约束未执行 |
| RA03 8并发CREATE | Project锁、manifest/request唯一键、别名绑定；SQL用例存在 | BLOCKED：真实业务API并发及最终DB盘点未执行 |
| RA04 投递异常 | PASS_ISOLATED：commit后拒收、接受后ACK丢失替身均保留同一queued Job | BLOCKED：真实Broker/Redis连接及故障注入 |
| RA05 重复领取 | 原ready幂等测试及独占连接锁代码 | BLOCKED：两个实际Worker消费者 |
| RA06 强杀/恢复 | 原冻结scope/path重试隔离测试；Beat扫描源码 | BLOCKED：collecting/packaging/publishing强杀与连接释放 |
| RA07 漂移 | PASS_ISOLATED：文件/报告版本/Task关联；本轮增加ready下载再核关联 | BLOCKED：跨进程、实际挂载和对象存储漂移 |
| RA08 撤权 | PASS_ISOLATED：跨owner/project、停用、reports/files权限及缓存刷新 | BLOCKED：真实JWT/不同连接撤权竞争 |
| RA09 ZIP下载 | PASS_ISOLATED：原发布/FileRegistry/ASGI字节与权限核验 | BLOCKED：授权环境实际HTTP下载 |
| RA10 离线SHA | PASS_ISOLATED：Job/ZIP/member/checksums与独立标准库脚本 | BLOCKED：真实下载ZIP及独立操作者复核 |
| RA11 预算 | PASS_ISOLATED：16MiB/64MiB/500文件边界、展开字节边界、配额和raw排除 | BLOCKED：80MiB压力、真实并发资源与磁盘/bucket故障 |
| RA12 项目切换 | PASS_ISOLATED：jsdom旧响应丢弃、状态清理 | BLOCKED：真实路由、登录会话与慢网 |
| RA13 真实窄屏 | 当前CSS/iframe sandbox已审查 | BLOCKED：浏览器启动失败，1920/768/390未验收 |
| RA14 partial | 原缺科学/证据/快照、不可用历史关联隔离覆盖 | BLOCKED：8个真实项目案例 |
| RA15 无计算副作用 | PASS_ISOLATED：TaskService/DownloadService/BioReport设为抛错仍完成允许路径 | BLOCKED：真实全栈事件/队列盘点 |

## 必须执行的恢复与安全验收

在专用环境保留原Job和manifest，对以下10点逐一故障注入：commit后Broker拒收；Broker接受但API失联；两个Worker领取；collecting中断；packaging中断；publishing中断；写成功但ready事务失败；原manifest重试；ready重复投递；Beat扫描过期active。每次保留Job ID、request别名、attempt、scope digest、实际锁连接、归档路径/SHA/FileRecord以及最终表状态。不能通过另建Job消除未知状态；强杀后的私有孤立归档要盘点，不自动清理科研证据。

权限用例还须覆盖Project删除/停用、用户失活、模块撤销、ready后撤权、伪造Task/Report/Version、FileRecord停用及同owner不同project。非法对象统一404/403，不泄露跨owner存在性；请求中自报value、dataset_version_id或verified状态不能成为证明。

真实ZIP案例至少为单Dataset双报告、多Dataset多Task、缺科学、缺证据、无可信历史关联、多版本、文件丢失及冻结后变化。逐项核对manifest_digest、ZIP及成员SHA/大小、checksums和五种包含/引用状态。没有真实案例输入或环境许可时不得为了演示重新跑RNAFlow或开启下载/分析。

FILE_INTEGRITY、EVIDENCE_COVERAGE、DELIVERY_COMPLETENESS、REPRODUCIBILITY_STATUS是四个不同维度。SHA通过只说明指定字节相符；partial不显示FULLY_REPRODUCIBLE，历史复现仍NOT_RUN。

## 浏览器后续验收

在获得可启动浏览器与授权应用栈后，按1920/768/390逐项操作ProjectDetail：可信Dataset/Task/科学/证据报告、三种包、预览缺口、JWT确认、真实Job状态、离页返回、ZIP下载本地SHA、切项目慢响应、撤权、失败重试。检查横向溢出、焦点、键盘导航、加载/错误、轮询清理和重复创建。原型HTML另查sandbox、无脚本、PDF明确缺失。任何JS DOM或Mock API结果仅计隔离层。

本轮停止在上述真实运行门禁。没有生产连接、真实组件写入、迁移、下载分析或模拟成功证据。可继续的已完成隔离增量见稳定化、RI10与RI09.5文档。
