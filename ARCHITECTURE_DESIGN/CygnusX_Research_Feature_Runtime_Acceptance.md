# 科研功能隔离运行验收

当前验收日期：2026-10-20（Asia/Shanghai）  
当前 Run ID：`20261019-235848-bootstrap`（名称保留 UTC 启动时刻）  
总体状态：`PARTIAL`；生产可用性：`NOT_ACCEPTED`。  
本节为当前结论；下方保留的 `20261019-211549-acceptance` 是历史记录，不能覆盖本节。没有继承任何历史运行 PASS。

## 当前结果与八项结论

| 问题 | 当前实测结论 |
|---|---|
| 1. Docker 真正可用？ | **是，`PASS_RUNTIME`**。默认本机 socket 可访问，Engine 28.3.3 / Compose 2.39.1；实际构建、启动和停止了本轮专用容器。未切换 daemon、未接管原有生产或旧验收容器。 |
| 2. PostgreSQL 迁移通过？ | **是，`PASS_RUNTIME`**。全新专用卷上真实执行 119 次 upgrade 到唯一 head `dwnscope06`，无 stamp。身份为 `ri095_acceptance / project_export_test_ri095`；`mcp_versions` 物理表存在，启动初始化后 8 行。不可变内容、即时外键、主键三项负面检查分别得到预期 SQLSTATE `P0001/23503/23505`，savepoint 回滚。 |
| 3. 科研计划能真实创建与审阅？ | **已验证 owner 人工审阅及计划生命周期，`PARTIAL_RUNTIME`**。真实 JWT/API 创建、修订、历史/幂等、指纹、权限及浏览器审阅通过。发现并修复了 PostgreSQL 修订外键 500。审阅不批准计算/发布；实际 advance 的发布步骤停在 `WAITING_APPROVAL`。未评价独立领域专家审阅质量，也未覆盖 TTL 到期、预算/并发压力或全部 read/prepare 工具组合。 |
| 4. 科研执行记录能真实读取？ | **仅空项目与权限边界通过；真实科研记录 `BLOCKED`**。真实 HTTP/PG 返回空 datasets，跨 owner/项目与撤权拒绝通过。没有获准脱敏既有完成任务、报告、产物 corpus；不以合成 Task 或报告替代真实记录。最终 Task、Report 都为 0。 |
| 5. 项目成果能真实导出？ | **`BLOCKED`**。空 inventory 与只读 prepare 预览实际成功；关闭门下创建 Job 返回 403，浏览器生成按钮禁用。Worker、Beat、私有存储已启动并检查，但 corpus 前置条件未满足，未启用 export/report 写门、未生成 Job/ZIP、未下载或验证 ZIP SHA，不得据预览宣称可导出。 |
| 6. Browser E2E 通过？ | **`PARTIAL_RUNTIME`**。Chromium 131.0.6778.33 的真实 sandbox 启用；最终 13 项断言通过、console/pageerror 为 0；1920/768/390 三宽截图、trace、network、API 与 DB 证据齐备。覆盖真实登录、计划审阅/暂停/恢复/刷新、审计轨迹、空交付及导出预览。计划创建由真实 API 完成；非空交付和 ZIP 下载闭环没有执行。 |
| 7. 哪些门可继续用于隔离测试？ | 在本轮约束、独立身份及专用数据范围内，可重新启动后临时开启 `RESEARCH_PLAN_ENABLED`、`RESEARCH_DELIVERY_READ_ENABLED`、`TOOL_GATEWAY_READ_ENABLED`。不因这些结果开放写执行；Project Export 仍需获准 corpus、独立 Worker/存储与下载验收。本轮现已全部停止，私有 READS/WRITES/PDF 均回到 false。 |
| 8. 哪些生产门必须保持关闭？ | **本轮未授予任何生产开放资格**。Research Plan、Research Delivery 读/写、Project Export、Project Report 写/PDF、Agent analysis/download write 均须继续保持原有关闭策略；`WRITE_RUNTIME_ACCEPTED=False`，不得伪造 `worker_paths_verified`。未修改生产配置或服务。 |

## 当前源码、镜像与隔离身份

证据目录：[`evidence/runtime-acceptance/20261019-235848-bootstrap/`](../evidence/runtime-acceptance/20261019-235848-bootstrap/)。机器可读状态见 [results.json](../evidence/runtime-acceptance/20261019-235848-bootstrap/results.json)，每项结论只对应本 Run 的证据。

- Git HEAD：`ac2cdca399d0fdb4b5e777a234b55e24ffbbeb79`。原工作树有大量无关脏文件，未提交或推送，未纳入无关修复。
- 最终构建时 dirty source SHA-256：`04dc7a9698abb5341b59b9d0f67e5c0af6de678f3bac3b9c7a8c49e889b66e75`；清单在 `source-files-fixed.json`，定义为 Git 跟踪/未忽略普通文件（排除 evidence/logs 和子模块内容）。这是**构建时**快照，后续本报告更新不在镜像里。7 个已初始化子模块的 commit 与内容摘要另在 `submodule-content-identity.json`；本轮不运行管线。
- 最终 app digest：`127.0.0.1:32769/app@sha256:e2e5854c23a69323ffc7f831153cfc4b42d6822a4169f8b6181d8566f83ed5db`；API/Worker/Beat 同镜像。运行镜像与构建快照 3614 个源文件逐个 SHA 核验，无缺失或不匹配，见 `image-source-fixed-verification.json`。
- 前端 digest：`127.0.0.1:32769/frontend@sha256:2a64cbf419efd3727a18a3e65450d7a00532c4c52b07394c3db4ae67ba243c81`；本工作树实际 `npm run build` 生成 dist，再构建固定 nginx 基础镜像。dist 清单、锁文件核对、Dockerfile、构建和推送日志均保留。继承固定应用基础镜像的依赖，`pyproject.toml/uv.lock` 哈希一致，未绕锁安装；镜像内缺少 pip/uv 的探针不计依赖完整性 PASS。
- Compose project：`cygnusx-20261019-235848-bootstrap`。使用仓库外 600 权限随机测试密钥 env；不读根 `.env`。运行 staging 是原 acceptance 控制器的独立 project 副本，最终副本保存于 `runner/`。所有业务服务只连专用 internal network，无宿主端口、Docker socket、外部卷或生产数据挂载；Registry 构建助手仅绑定本机回环地址，已停止。
- 应用及浏览器 UID/GID `10001:10001`，cap_drop=ALL，no-new-privileges；Chromium 使用窄 seccomp 配置，未使用 `--no-sandbox`。Redis DB1/2、队列 `ri095_acceptance`；local storage 实际根 `/acceptance-storage`，UID 10001 写入/读回探针成功；不是业务成果验收。
- 运行时仅 plan/read/tool gateway 为 true；交付写、导出、报告/PDF、分析/下载写均 false。源码 `WRITE_RUNTIME_ACCEPTED=False` 未改。最终 PG 有 4 条计划（含首次失败修订留下的原 v1）、Task=0、Report=0、ExportJob=0。原始及最终 DB 状态均保留。

## 本轮发现、修复与实际覆盖

真实 PostgreSQL 最初创建 v2 时返回 500：旧版本的 `superseded_by` UPDATE 先于新版本 INSERT，违反 `research_plans_superseded_by_fkey` 的即时外键。`ResearchPlanService.prepare` 现先 flush 新版本，再更新旧版本链接，两个 flush 留在调用方同一事务内。现有修订回归测试开启 SQLite FK，防止原用例掩盖错误；随后重建镜像，真实 PostgreSQL v2/v3 修订、旧版指针、审阅清空及重新审阅均成功。`api/plan-initial.json` 保留初次失败；`api/plan-fixed.json`、`api/browser-new-version.json` 和 `db-final.json` 记录修复后结果。

真实 API 还验证了同 request_key 幂等与冲突409、过期指纹409、旧版不可再审阅、禁止 shell 参数422、跨 owner404、匿名/API-key审阅401、模块撤权403及恢复、暂停/恢复/取消/对账与事件。最终独立边界脚本 **18/18**；真实 session 创建没有调用 LLM，发布步骤 advance 只进入 `WAITING_APPROVAL`。

附件只给出 RP-01–14、RE-01–10、PE-01–12 的范围，未提供各编号的独立用例定义；`results.json` 显式列出本轮编号对应的具体断言、证据和未执行项，不宣称通过了不可见的完整规范。计划 owner 人工审阅通过不等于领域专家评估通过；真实 Task/报告/Worker 科研路径、ZIP、JWT 下载、对象存储/PDF、并发/故障恢复仍有明确缺口。

验收脚本有两处预期修正，保留原始失败而不改产品行为：prepare 在 export 写门关闭时仍是合法只读预览，实际应为200；export 状态入口先检查 feature gate，因此未知 job 在关闭门下应为403，不能据此声称覆盖了启用后的未知 job404。最终已按正确预期重新请求，见 `api/boundaries-final.json`。

Browser 初次受 API 重建后 nginx 地址缓存和脚本用户名错误影响。重启本轮 frontend 并修正测试用户名后流程通过；随后发现 staging nginx 缺 WebSocket Upgrade 转发，补齐并重载，只修改验收 staging 代理。最终重建计划 v3 后重跑完整页面序列 **13/13**，console 清零。attempt5 的已通过页面断言及 WebSocket console 错误仍在 `browser-attempt5/`，最终证据在 `browser/`。390px 页面无横向滚动，但顶部导航换行为可见 UI 限制，不能把溢出断言当作全部移动端视觉验收。

Trace 从登录后开始，仍可能带认证头；发布的 trace 和 console/network 文本已脱敏 JWT/cookie/password，私有原 trace、storageState 和密钥仅留在仓库外 staging，未复制到 evidence 或提交。截图、事件、响应和最终 PG 结果可交叉核对。

## 验证限制与关闭证据

- 本次变更两文件 Ruff 通过；计划相关回归 **52 passed**；迁移静态检查通过；真实前端 production build 通过。
- 全仓 Ruff：277 项错误；mypy：221 文件 997 项错误；全量 unit：**3755 passed / 9 failed / 16 skipped / 63 deselected**。失败清单与日志在 `validation-*`；它们涉及本次两处修改以外的路径，未擅自修复，也未做基线对比证明全部为既有失败。**全量门禁未绿，无提交**；未追加宣称 E2E/集成/bridge 全量通过。
- 缺少获准脱敏科研 corpus，遵守 `deploy/acceptance/README.md` 的 corpus gate，未开启 export/report/PDF 写入；没有伪造完成任务、worker_paths_verified、ZIP 或下载证据。这是后续运行前置条件，不是已经通过的测试。
- 先停止本轮 Compose、独立 browser 和 registry，再将私有 READS/WRITES/PDF 全改 false 并重新 preflight。`closure.json` 实证 8 个专用容器全部停止，三个专用命名卷保留，无 `down -v`、无 downgrade。最后运行时读门曾为 true；停止后未重启，不把 env 变更冒充运行进程已热加载。既有生产容器/配置未修改。

---

## 历史验收记录：20261019-211549-acceptance

以下为上一轮原始结论，只解释历史阻断，不代表当前 Docker 状态或本轮验收结论。


日期：2026-10-19（Asia/Shanghai）  
Run ID：`20261019-211549-acceptance`  
总体状态：`PARTIAL`  
隔离运行状态：`BLOCKED`  
生产可用性结论：未验收，不得据此宣称生产可用。

## 验收范围与源码身份

本次依照受控验收任务检查项目科研计划、科研执行与交付、项目科研成果导出。没有连接 PostgreSQL/外部数据库、启动服务、启用功能或访问生产资源。定向回归测试仅创建临时 SQLite 数据库并执行其测试迁移；Alembic revision planner 只做静态规划，没有执行 PostgreSQL/Acceptance 迁移。工作区中另有 2026-10-17 的 disposable runtime/E2E 记录，已在下文单独核对；其源码 commit 与本次不同，不作为本次源码的验收通过。

| 项目 | 本次观察 |
|---|---|
| Git commit | `ac2cdca399d0fdb4b5e777a234b55e24ffbbeb79` |
| Dirty worktree | `git status --short` 共 208 条状态项；含本任务之外的既有修改 |
| 工作区内容摘要 | `e9a4a790c0dc4c0dc6f3e13842f8cf7f73934dee582641498276b2be88c24e0e`；对 `git ls-files -co --exclude-standard` 列出的普通文件 SHA-256 清单再次求 SHA-256，Git 子模块目录内容不在此摘要内 |
| 隔离环境 ID | 未创建；预期 Compose project 为 `cygnusx-ri095-acceptance` |
| 容器镜像 digest | 未提供 / 未构建 |
| 数据库身份 / Alembic 实际 revision | 未创建 / 未读取 |
| 本机 `Settings()` 快照 | 以下九个相关开关均为 `false`；这是本次命令进程从当前工作目录加载 `.env`/默认值所得，不代表任何正在运行的 API 容器 |

本机快照：`research_plan_enabled=false`、`research_delivery_read_enabled=false`、`research_delivery_write_enabled=false`、`project_export_enabled=false`、`project_report_write_enabled=false`、`project_report_pdf_enabled=false`、`agent_analysis_write_enabled=false`、`agent_download_write_enabled=false`、`tool_gateway_read_enabled=false`。本命令进程没有这些同名环境变量覆盖。当前 Docker daemon 不可访问，未能读取目标服务进程的有效 Settings。

## 实现与门禁

配置来自 `src/cygnusx/core/config.py`。`Settings` 使用不区分大小写的环境变量解析并加载 `.env`；操作系统环境变量可覆盖 `.env` 和字段默认值。相关变量名按字段名映射为大写，例如 `RESEARCH_PLAN_ENABLED`、`RESEARCH_DELIVERY_READ_ENABLED`、`PROJECT_EXPORT_ENABLED`。隔离 Compose 只从权限为 600 的专用 acceptance env allowlist 读取镜像、随机测试密钥和 `ACCEPTANCE_*` 标志，再显式映射为应用配置，不读取仓库根 `.env`。

| 功能 | 实现和 API | 有效依赖及当前边界 |
|---|---|---|
| 科研计划与审阅 | `api/v1/research_plans.py`；`ResearchPlanService`；`research_plans` 表及 `bioopsphase5` 迁移 | `research_plan_enabled=true`、当前用户对项目的所有权/访问、`tasks` 与 `reports` 模块权限。查询为只读；创建/修订/审阅/状态控制会写计划记录。审阅计划不批准业务工具写操作。当前架构状态为 `PLAN_ONLY`，advance 最多调用一个只读或 prepare 能力；计划验证会保留 `LIVE_EXECUTION_BLOCKED`，不触发真实下载或计算。Review、advance、control、reconcile 使用 JWT 身份；一般查询依赖当前用户身份。 |
| 科研执行与交付链 | `api/v1/research_delivery.py`；`ResearchProvenanceService`、执行绑定和既有 Task/Report/Worker | 读取需要 `research_delivery_read_enabled=true`、当前用户身份、资源所有权及项目和模块授权；多数读取端点使用 `CurrentUserId`，不是 JWT 专用依赖。写入同时要求 `WRITE_RUNTIME_ACCEPTED`、Agent analysis admission 和 `research_delivery_write_enabled`；源码 `WRITE_RUNTIME_ACCEPTED=False`，配置默认读写开关均关闭。Dataset 分析还要求可信冻结 Handoff 和 `worker_paths_verified=true`；当前代码生成的 handoff 默认该值为 false，禁止伪造。实际 Worker/真实科研案例未验收。 |
| 项目成果与可追溯导出 | 项目交付 inventory/prepare/create/status/retry/download API；`ProjectDeliveryService`；项目导出 Job/Manifest；Celery Worker | `export_enabled()` 先要求科研交付读取开关，再要求 `project_export_enabled=true`。Inventory/prepare/status 使用当前用户依赖；创建/重试/下载使用 `CurrentJwtUserId`。创建/重试会持久化 Job，请求 Worker 生成 ZIP 到存储，下载重新检查身份、权限和字节。项目/资源权限和当前 SHA 校验不可绕过。真实 PostgreSQL/Celery/私有存储/浏览器链路仍未验收；正式项目报告写入与 PDF 另有独立开关。 |

执行写入、下载写入和 Agent admission 不会因打开 Research Plan 或 Project Export 开关而打开。配置开关不是运行验收结果，也不会替代用户权限、Approval、Admission、Budget 或 Worker 校验。

## 检查结果

### Phase 0：源码与配置调查 — `PASS_STATIC`

已检查配置、科研计划服务、执行绑定、项目交付服务、两份 as-built 架构文档、页面组件、API 路由、权限依赖、核心模型和 Alembic 迁移，以及相关隔离测试。当前源码存在功能实现和隔离测试，但默认关闭且运行条件尚未验收；不能据配置项或单元测试推断完整科研功能可用。

迁移静态规划：`deploy/acceptance/audit_migrations.py` 报告 119 个 revision、唯一 head `dwnscope06`、无重复 base upgrade 步骤。它没有连接数据库或执行 SQL。`projectreport01` 的父链包含 `mcpdigestmerge01`，该 merge 汇合 `projectdelivery01` 与 `c1d2e3f4b5a6`。此前关注的 `mcp_versions` 物理表/迁移顺序只能通过隔离数据库上的真实升级与 schema 检查判断；本轮没有数据库，未予确认，也没有使用 `stamp` 或修改版本记录。

### Phase 1：隔离环境 — `BLOCKED`

- Docker 客户端可用（Engine 28.3.3、Compose v2.39.1），但连接 `/var/run/docker.sock` 返回 `permission denied` / `operation not permitted`。
- `deploy/acceptance/acceptance.env.example` 仍是占位模板；没有权限 600 的私有 acceptance env、审查过的镜像 digest 或经批准的隔离真实数据 corpus。
- `deploy/acceptance/README.md` 规定该环境只能连接专用内部网络、`project_export_test_ri095` 数据库和私有 local storage；目前没有环境可供身份核验。
- 因容器不可用，按门禁停止，不启动 PG/Redis/API/Worker/Beat/Frontend，不执行数据库迁移，不继续依赖真实数据库的模块测试。

### 本地离线检查 — `PASS_STATIC`

- `.venv/bin/ruff check deploy/acceptance`：通过。
- `.venv/bin/ruff format --check deploy/acceptance`：11 个文件格式检查通过。
- `deploy/acceptance/checks.py`：隔离 Compose 静态校验通过；拒绝发布数据库端口、外部数据库、分析写入、外部网络、Docker socket、错误 tmpfs、root UID 和未批准环境变量等 8 项负面用例通过；合成 Celery 注册表检查通过。均为 `PASS_STATIC`，不证明业务任务已运行。
- `node --check deploy/acceptance/browser-preflight.cjs`：通过语法检查，不代表浏览器启动或业务 E2E。
- Alembic revision planner：单 head 静态规划通过，不代表 PostgreSQL 迁移通过。

### SQLite / jsdom 回归 — `PASS_ISOLATED`

- `.venv/bin/pytest tests/unit/test_research_plan_phase5.py tests/unit/test_research_plan_storage_phase5.py tests/unit/test_research_plan_gateway_phase5.py tests/unit/test_research_delivery_phase4.py tests/unit/test_project_delivery.py tests/unit/test_project_delivery_stabilization.py -q -m 'not quarantine'`：115 passed。测试使用 SQLite、临时文件和测试替身/隔离依赖；覆盖计划状态、权限边界、manifest、ZIP、SHA、幂等与恢复逻辑。它不使用 PostgreSQL 或真实 Celery Broker/Worker。
- `npx vitest run src/components/research/__tests__/ResearchPlanWorkbench.test.ts src/components/research/__tests__/ResearchDeliveryChain.test.ts src/components/__tests__/ProjectResearchDelivery.test.ts`：17 passed。使用 jsdom，不启动真实浏览器，不代表 Browser E2E。
- 后端 pytest 有 3 条既有警告：Pydantic class Config 弃用、一个同步测试带 asyncio marker、恶意 ZIP 测试故意创建重复成员名；均未导致失败。

### 历史 disposable 运行记录

以下记录来自工作区现有证据，不属于本次 Run ID，也不证明当前 HEAD/dirty source：

| 历史 Run | 证据与结果 | 限制 |
|---|---|---|
| `ri095-20261017-attempt1`，source `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33` | [`results.md`](../evidence/runtime-acceptance/ri095-20261017-attempt1/results.md) 记录真实 PostgreSQL 14、迁移、约束、部分并发、JWT、本地私有存储、HTML 报告和 M0→M1 ZIP 的 `PASS_RUNTIME`。Fresh DB 首次迁移曾因 `mcp_versions` ALTER 顺序失败，随后在该 run 的隔离源码上修复并通过；tmpfs 配置也曾失败后修复。 | RA04–06 仅部分覆盖；获批科研 corpus 缺失；当时浏览器 sandbox、PDF renderer 和对象存储被阻断；不能代表当前 119-revision HEAD。该 run 记录测试 flags 已关闭、容器停止、卷保留。 |
| `ri095-authorized-20261017-attempt1`，source `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`，前端镜像 `sha256:02fec0d33e1f8035238ddc248dd7d9c83ff90f4f1a8060152aa1f09ad1b9d7d5` | [`delivery-chain/results.json`](../evidence/runtime-acceptance/ri095-authorized-20261017-attempt1/delivery-chain/results.json) 记录报告 HTML/PDF、M1 导出、JWT 下载、ZIP 校验及跨 owner 404；浏览器在 1920/768/390 访问项目页、计划 API、科研交付 API、inventory 和导出预览。D4 UI 空 `request_key` 422 在该 run 发现并修复；修复后 browser attempt2 为 31/34，console error 清零。 | 34 步中 3 个 `export_ready` UI 断言未通过（已有幂等 ready Job 令按钮轮询断言未命中）；API 驱动链成功。不证明 plan 创建/审阅或真实分析/下载执行；没有获批真实 corpus。历史 evidence 中该授权 run 的 flags 文件仍记为 ACCEPTANCE_READS/WRITES/PDF=true，而容器记录为 Exited；不要把该文件状态当作关闭后的当前配置。 |

历史证据说明这些实现曾在特定旧源码和 disposable 环境中跑过若干 runtime 路径；它同时记录了真实缺陷、部分浏览器断言失败和未完成项。它解释了“已实现但仍看起来未开放”：验收时临时开的是隔离 acceptance 配置，当前本机配置默认 false；历史 run 也没有授予生产开放资格。

### Phase 2–5：业务和浏览器测试

由于 Phase 1 被阻断，下列测试没有真实运行；上面的 SQLite/jsdom 用例只按 `PASS_ISOLATED` 记录，未计作真实服务或浏览器运行证据。

| 范围 | 状态 | 未执行原因 |
|---|---|---|
| RP-01–RP-14：计划创建、查询、修订、审阅、权限、幂等、PLAN_ONLY、刷新恢复 | `BLOCKED` | 无隔离 PostgreSQL/API/JWT/浏览器环境；当前开关关闭 |
| RE-01–RE-10：真实项目记录读取、资源关系、权限隔离、写门禁 | `BLOCKED` | 无真实隔离 API/数据库和授权测试主体；读取开关关闭 |
| 真实分析/下载及 Worker admission | `BLOCKED` | `WRITE_RUNTIME_ACCEPTED=False`；analysis/download write 关闭；`worker_paths_verified` 未被运行时验证 |
| PE-01–PE-12：项目成果、Job、Manifest、ZIP、SHA、JWT、跨项目拒绝、恢复 | `BLOCKED` | 无隔离 PostgreSQL/Celery/storage、JWT 和可验证测试产物；导出/读取开关关闭 |
| 本次 Browser 业务 E2E 与截图、trace、network/console/API/DB 证据 | `NOT_TESTED` | 本轮 Docker/browser runner 不可用；旧源码有独立的部分历史 E2E，见上表 |
| 对象存储 / PDF | `NOT_TESTED` | 本轮配置仅为 local storage；对象存储未授权，PDF 依赖实际 Worker 工具链和字体验收 |

没有发现可在本次环境修复并复测的业务缺陷；没有代码或配置修复。本次唯一阻断是验收环境和获批测试材料不可用，不能把该阻断修饰成测试失败或成功。

## 最终判断

| 问题 | 判断 |
|---|---|
| A. 科研计划现在能否正常使用？ | `BLOCKED`：当前本机快照开关为 false；旧源码的浏览器证据只证明页面调用过计划查询 API，没有证明创建/审阅完整流程。即使在隔离环境启用，能力范围仍是 PLAN_ONLY。 |
| B. 科研执行与交付链能否查询真实记录？ | `BLOCKED`：当前读取开关关闭；本轮未连接记录库。旧浏览器证据发出过 research-delivery 查询，但未覆盖真实科研 Task 的端到端执行/溯源验收。 |
| C. 是否具备正式执行的安全条件？ | `BLOCKED`：不具备验收证据；运行时写门禁 false，分析/下载写入关闭，Worker 路径未验证。生产执行必须继续关闭。 |
| D. 项目科研成果能否正常导出？ | `PARTIAL`：旧源码 commit 的隔离 PostgreSQL/Celery/local storage 曾通过 M1 ZIP/JWT 下载和校验；当前源码尚未复验，获批真实 corpus 与对象存储范围也未通过。当前本机开关关闭。 |
| E. 三个模块是否完成真实浏览器测试？ | `PARTIAL`：旧源码项目页/交付预览/导出浏览器流程有 31/34 步通过，仍有 3 个 export-ready UI 断言未通过；科研计划创建审阅和真实科研执行链没有完整浏览器闭环。当前源码未跑 E2E。 |
| F. 还缺少哪些运行条件？ | 容器 daemon 权限；权限 600 的专用 acceptance env 和唯一镜像 digest；专用 disposable PG/Redis/private storage；真实迁移与 `mcp_versions` schema 证据；真实认证用户/权限；经批准的脱敏既有 Task/报告/产物；浏览器 runner；必要时同一 Worker 镜像的 PDF 工具/字体证据。 |
| G. 哪些功能可以在测试环境继续开放？ | 隔离环境完成 preflight、身份、迁移、权限和存储核验后，可先开 acceptance-only 只读门及计划工作流测试；Project Export 写 Job 需再单独通过 Worker/存储前置检查和获批测试产物。不得把测试开关带入生产。 |
| H. 哪些生产门禁必须保持关闭？ | 未获准前保持科研计划、科研交付读取/写入、项目导出、项目报告写入/PDF，以及 Agent analysis/download/write admission 关闭；`WRITE_RUNTIME_ACCEPTED` 继续 false，`worker_paths_verified` 只能由真实验证流程产生。 |

## 证据与后续门槛

本次机器可读状态和静态检查摘要见 `evidence/runtime-acceptance/20261019-feature-acceptance/results.json`。本次没有新建容器日志、数据库快照、API 响应、JWT、ZIP、截图或 Browser Trace；历史运行物仍保存在各自 Run 目录，不覆盖或合并进本次结果。

继续运行验收需先在有 Docker daemon 权限的隔离主机准备本目录约定的私有 env、固定 digest 的自建/审查镜像和获批测试 corpus。之后从专用 PG 身份检查和真实 Alembic upgrade 开始；任何迁移或身份失败都应停止后续数据库测试。写操作须通过独立验收前置条件，生产配置及安全默认值保持不变。
