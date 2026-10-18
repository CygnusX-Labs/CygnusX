# RI095 隔离运行验收环境

当前状态：**BLOCKED（容器访问被沙箱拒绝）**。配置尚未启动；本文不是运行通过记录。入口不读取仓库根 `.env`，不连接现有数据库，不下载科研数据，不执行科研分析。

## 复用决策

已检查 `deploy/docker/Dockerfile`、`Dockerfile.worker`、`Dockerfile.frontend`、主 Compose 和 Worker Compose。现有 Worker 配置继承根 `.env`、external `cygnusx_net`、共享数据目录、Docker socket、analysis 队列，不能直接安全继承。此处仅定义独立的最小拓扑，复用现有镜像、Alembic、认证、FastAPI、任务函数与存储代码，不复制生产栈。

`Dockerfile` 只扩展审查过的现有 Worker/应用镜像：复制当前 `data/`，准备 UID 10001 所有的 `/acceptance-storage`，不安装软件。基础镜像必须包含本次源码和迁移。若缺 Pandoc/Typst/中文字体，版本探针标 MISSING，PDF Gate BLOCKED；本轮未擅自选择或下载依赖。新镜像标签须含本次源码短 SHA，运行使用该镜像的 sha256 digest。构建遵循 `Protocol/镜像构建国内加速规范_v1.md`；继承基础镜像不重复安装/换源。

```text
Linux Playwright → frontend:8080 → api:8000 → PostgreSQL
                                      ↓ publish
                       Redis DB1 / ri095_acceptance
                                      ↓
                    Worker + Beat（仅 report/export）
                                      ↓
                       private-storage 命名卷
```

所有服务只连接 internal 网络，无宿主发布端口。PG/Redis/私有卷均由固定 Compose project `cygnusx-ri095-acceptance` 独占。不要在同一 Docker daemon 并发运行两个相同 project。PG 身份固定 `ri095_acceptance / project_export_test_ri095`，符合原 `project_export_test*` 测试保护规则。Bucket 为 `ri095-acceptance-unused`，实际后端 local。S3 适配已存在，但未配置或授权测试 Bucket，本轮不启动对象存储；对象存储 Gate 单独 BLOCKED。

## 准备与预检

当前会话没有 Docker 权限，不执行以下运行命令。由拥有容器权限的验收操作者在 disposable Docker 主机执行：

1. 审查当前源码及脏文件，构建现有 Worker/前端镜像；使用本目录 Dockerfile 制作最小应用扩展。基础镜像缺少 `/app/data` 的问题由扩展解决。核对构建记录、源码 SHA 与镜像 digest，不采用 `latest`。本配置不会自动拉取或构建镜像。
2. 准备 digest 固定的 pgvector PostgreSQL、Redis，以及兼容 Linux 的 Playwright runner 镜像。Playwright 镜像须同时包含 `playwright` Node 包及其匹配 Chromium。官方浏览器基础镜像不保证含 Node 包，不能直接假定可运行；应在受控构建中补齐并固定版本。保留 Chromium sandbox；若宿主 seccomp/userns 不支持，标 BLOCKED，不加 `--no-sandbox` 伪造成功。
3. 将 `acceptance.env.example` 复制到仓库外的私有文件，权限 600。分别生成四个 `secrets.token_hex(32)`，填入专用密码/密钥；所有镜像填审查过的 `name@sha256:...`。将 `ACCEPTANCE_BROWSER_SECCOMP` 设为仓库内 `deploy/acceptance/seccomp-browser.json` 的绝对宿主路径。不要复制生产凭据。所有 flag 初始 false。该文件不会提交。
4. 用现有 `.venv/bin/python deploy/acceptance/control.py preflight --env /absolute/private/acceptance.env`。控制器只接受明确 allowlist；不继承宿主 DATABASE_URL、DOCKER_HOST、云密钥、根 `.env`。仅连接默认本机 socket，禁止切 daemon 绕权限。`config --format json` 仅内存解析，不输出含秘密的配置。
5. `deploy/acceptance/run-checks.sh` 是离线检查，不授予运行通过。八项负面配置回归使用合成配置检查保护拒绝逻辑，下载 Worker 注册表断言使用合成 Celery app；均不作为业务任务/制品或真实运行证据。

## 首次启动与身份

`control.py start --env ...` 顺序：离线目标检查 → Docker 权限检查 → 仅 PG/Redis 启动 → 应用入口真实 SQL 身份检查 → Alembic head → API/Worker/Beat/前端。镜像入口覆盖既有 root/挂载逻辑，应用 UID 10001、cap_drop ALL、no-new-privileges，私有卷从扩展镜像初始化。首次连接后核对实际数据库名/用户/IP/版本，任何异常停止。服务本身在每次启动前再次检查目标、实际身份、有效存储根和门禁。

入口明确禁用 Pydantic `.env`；复制当前 CygnusX.yaml 到容器 tmpfs，仅覆盖 storage 段，因为原 YAML `/data/omichub` 优先于 STORAGE_PATH。有效根必须 `/acceptance-storage`，卷不可写则失败。不挂载生产数据或 socket。API/Worker/Beat 进程统一使用 `ri095_acceptance`；Beat 仅保留两个项目 reconcile。Worker 注册表仅保留四个现有项目 report/export 任务，未知任务拒绝执行。该运行注册表行为尚待真实 Worker 验证。

**空库升级 head 不能替代旧模型升级验收。** RA01 在另一份同样隔离的 disposable 卷上：先迁移到 `bioopsphase5`，通过已授权的脱敏旧模型制品/记录还原旧 Task Report，记录旧报告字节及关系，然后升级 head。保存实际迁移 SQL/日志、`alembic history`、最终 `alembic current` 和 `state.sql` 输出。源码关系为 `projectdelivery01 ← bioopsphase5`，`projectreport01 ← mcpdigestmerge01`，不是直接相邻，必须保留中间迁移。不能用 `stamp` 或 ORM create_all 代替。现有 opt-in `tests/integration/test_project_delivery_postgres.py` 只验证独立 schema 的 delivery 约束，8 个 SQL 事务不算 8 个业务 API；不要把它当完整 RA01–03。

## 按 Gate 执行

先保持写关闭，完成身份、迁移、UID/存储、真实认证基线。通过现有 `/api/v1/auth/register` 创建两个专用测试用户，通过 `/auth/login` 表单登录，使用真实 JWT；不 Mock deps、不直接造 ready Job。如模块权限、邮箱策略、启动依赖阻止操作，保存响应并 BLOCKED，不能跳过权限。使用明确批准的脱敏既有完成任务及原始制品作为 corpus；记录来源和 SHA，不运行分析、不下载科研数据、不使用合成 Task/模拟报告冒充真实链路。缺少合法 corpus 即停在该 Gate。

完成前置条件并保留日志后，操作者仅在私有 env 中启用 ACCEPTANCE_READS/WRITES；PDF 先经实际 Worker 版本与字体检查再启用 ACCEPTANCE_PDF。再次 preflight、start 更新容器。对应真实 Settings 为 research_delivery_read_enabled、research_plan_enabled、project_report_write_enabled、project_export_enabled、project_report_pdf_enabled。research_delivery_write_enabled、agent_download_write_enabled、agent_analysis_write_enabled 始终 false。其他模块 RBAC 与 reports/files 权限仍按现有系统授权，不能为了通过删除安全断言。

| Gate | 运行方法与必留证据 |
|---|---|
| RA01–03 PG | 在真实 PG 执行 XOR、FK、冻结 Manifest/Frozen Claims SQL 失败断言；8 个真实 scientific-summary POST 并发，保留请求/响应及 Job 唯一性；不同来源版本、会话 advisory lock 跨 commit 竞争、项目删除/停用、旧 Task Report 字节/关系兼容。用 `state.sql` 保存最终状态；保存执行 SQL 与 SQLSTATE。 |
| RA04–06 Celery | JWT 创建 Job → Broker 队列记录 → Worker 日志；重复派发、queued 恢复、Beat 恢复、失败重试、ready 不重复。只在 Compose 标签和容器身份都匹配本 project 的 Worker 注入故障；禁止 pkill/celery 全局控制。collecting 是导出阶段；项目报告当前是 validating/rendering/publishing，按实际阶段采证。短阶段无法稳定命中应 BLOCKED，不能伪改 DB 状态算中断成功。发布成功/提交失败需要受控、可复核注入点，此处尚未实现，不应声称覆盖。 |
| HTML/PDF | `control.py versions --env ...` 记录同一 Worker 镜像 Pandoc/Typst/fc-list、镜像 ID；模板 project-summary.v1 / renderer project-summary-adapter.v1，记录文件 SHA。经真实 Job 生成中文、长名称、多任务、分页、空科学结果与四种 provenance 标签，目视及字节验证。PDF 失败保留 HTML 场景需真实失败/恢复日志。静态 HTML 不能代表全部 BioReport/Quarto 科学验收。 |
| 私有存储 | 发布/回读 SHA、FileRecord owner/lifecycle/配额/ReportFile、原子发布和中断、漂移/丢失/重复/无效 symlink、ready 后撤权。只操作专用私有卷；下载重新校验；不以 ready 单字段判定文件有效。对象存储另行授权独立 Bucket 后才可测试。 |
| JWT | 真实登录与创建、API key 创建拒绝、同/跨 owner、跨项目、项目/用户停用、reports/files 撤权、ready 后撤权及再次下载；保留脱敏请求/状态码，不保存 bearer 或登录密码。 |
| M0→M1 | 保存原 M0 JSON、digest、ZIP SHA；选择真实核验 Claim、真实 Worker 生成/登记、创建 M1 并打包；使用 `src/cygnusx/domain/project_delivery_archive.py` 独立 stdlib 验证器核验 ZIP，独立 SHA 工具比对 M0/M1/ReportFile/HTML/PDF/ZIP 成员、missing 与 partial；前后对照旧 M0/ZIP 字节。打包期间确认没有报告重渲染或分析任务。 |
| Browser | `control.py browser-probe --env ...` 仅 Chromium 启动和 1920/768/390 首页可达探针，**不是业务 E2E**。完整业务脚本仍待有真实 corpus 和浏览器环境后完成/运行：登录→项目→交付→Claim→准备→JWT 创建→真实 Job→HTML/PDF→M1→ZIP/SHA，覆盖快切/慢响应/重复点击/刷新/离页恢复/撤权/重试/键盘/焦点/溢出；每宽度保存截图、console、脱敏网络日志、下载原件。不能用首页探针或 jsdom 代替。 |

## 采证、关闭与回滚

执行命令及退出码、时间戳必须逐次保存到 `evidence/runtime-acceptance/<run-id>/`。用 `control.py logs` 保存容器日志（审查和脱敏）；`versions` 收集同一应用镜像内程序版本及 Compose 镜像映射。通过专用 postgres 容器 psql 执行只读 `state.sql`（身份先核对），以及 pg_dump schema/data 到私有 evidence；不得在公网发布用户信息/JWT。SQL 约束测试必须保留失败 SQLSTATE、预期失败与意外失败之别，不能把整条命令 exit 非零当成功。

最终运行 `summarize.py` 为实际存在的证据生成 SHA 索引；它不自动提升状态。results.json 按人工审核过的原始证据登记，缺截图/下载/日志即保留 BLOCKED。

结束时首先 `control.py stop --env ...` 停止所有专用服务；将私有 env 中 READS/WRITES/PDF 全改 false，preflight 留存关闭配置。若需要继续只读验收，再 start 并检查实际 flags 输出。不要只改 env 而留下旧容器运行。保留 PG、Redis、私有卷与 evidence；不要 down -v，不运行迁移 downgrade 删除冻结证据。只有人工确认保留期和完整备份后，才可在本专用环境进行资源清理。

当前实现仅交付隔离配置、检查/采证脚本和操作说明；没有自动化全部业务及故障注入场景，也没有完整业务 Playwright spec。容器 Gate 阻断后不继续伪造运行结果。
