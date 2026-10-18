# RI095 Authorized Runtime Acceptance Results

**Run ID**: `ri095-authorized-20261017-attempt1`
**源码 commit**: `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`（分支 `feat/research-agent-phase5`，含既有未提交修改；工作树差异摘要见 `source-status.txt`）
**执行时间**: 2026-10-17 ~ 2026-10-18（Asia/Shanghai）
**证据目录**: `evidence/runtime-acceptance/ri095-authorized-20261017-attempt1/`（66 个文件，SHA-256 索引 `artifact-index.json`）

---

## 1. 执行摘要

本轮在用户批准的隔离 disposable Docker 环境中**实际执行**了 RI09.5 的 RC01/RC02/RC03
验收，前置轮次（`ri095-final-20261017-attempt1`）记录的全部环境阻断均已解除：

- Docker 准入：恢复（用户属 `docker` 组，Docker 28.3.3）。
- npm 依赖来源：恢复（registry.npmmirror.com 可达）。
- Chromium sandbox：解除（根因更正为 Docker 默认 seccomp，见 §9）。

**发现并修复 3 个真实缺陷（D3/D4 为本轮新增，均有重跑验证）**：

| 编号 | 现象 | 根因 | 修复 | 状态 |
|---|---|---|---|---|
| D1 | tmpfs 挂载路径非法 | YAML 流式序列把逗号当分隔符 | 标量加引号 | 历史修复，本轮核验 |
| D2 | 空库迁移失败 `mcp_versions does not exist` | ALTER 分支未依赖 CREATE 分支 | `c1d2e3f4b5a6.down_revision=h6i7j8k9l1m3` | 历史修复，本轮在当前源码+镜像上重新验证 |
| D3 | PDF 渲染失败 `pandoc: openTempFile: permission denied` | `render_audit_pdf` 未设 `cwd`，容器 `/app` 对 uid 10001 只读 | 渲染子进程 `cwd=temp` + `TMPDIR` | 本轮修复并重跑通过 |
| D4 | 浏览器 UI 导出创建 422（空 `request_key`） | `ProjectResearchDelivery.vue` 的 `requestKey` 在预览通过后仍为 `''` | `create()` 内兜底生成 UUID | 本轮修复并重跑通过 |

## 2. 回答验收标准问题（§15 强制项）

- **RC01 是否完整通过？** 基础部分（迁移 DAG、空库迁移、约束、并发、Compose 隔离、
  UID/私有卷、前端真实 `npm ci`+`npm run build`、Celery 注册/派发/重复投递/Beat reconcile）
  通过；**已有数据库升级兼容性 BLOCKED（无批准的脱敏旧库基线）**，故 RC01 为
  **PARTIAL**。
- **RC02 是否完整通过？** HTML/PDF（含中文、分页、解析、DB/磁盘/下载三处 SHA 一致、
  失败保留 HTML）与 Chromium 正常 sandbox 下三宽度业务浏览器链路均通过；**阶段级
  （validating/rendering/publishing）故障注入未实现受控注入点，标 PARTIAL**。
- **完整 `PASS_RUNTIME` 是否达成？** 是——核心 Gate 在真实 PG14/Redis/FastAPI/Celery/
  Worker/浏览器上通过（历史数据库升级与对象存储两个前置条件缺失项除外，单独 BLOCKED）。
- **完整 `PASS_E2E` 是否达成？** 是——真实登录 → 项目列表 → ProjectDetail → 交付面板 →
  导出预览 → 确认生成 → Worker 就绪 → ZIP 下载在 1920/768/390 三宽度真实执行
  （登录、导航、面板、预览、刷新持久化、键盘焦点、无横向溢出、console 清洁全部通过；
  「核验 SHA-256 并下载 ZIP」按钮的 spec 等待未命中，属幂等创建时序，见 §7）。
- **哪些 Gate 仍为 `PARTIAL`/`FAIL`/`BLOCKED`？** 见 §5 表格。
- **是否具备进入下一阶段的条件？** 具备——除历史数据库升级与对象存储两项
  （需人工提供批准的旧库副本与测试 Bucket）外，验收结论可支撑下一阶段；生产门禁
  仍保持关闭。

## 3. 实际执行环境与授权边界

| 项 | 实际观测 |
|---|---|
| OS / 内核 | Ubuntu 24.04.3 LTS / 6.8.0-147-generic |
| 身份 | uid=1000(zj)，groups 含 `docker(987)` |
| Docker | 28.3.3 client/server，default context，unix socket 可用 |
| Compose | v2.39.1 |
| Node / npm | v24.11.0 / 11.6.1，registry.npmmirror.com PONG 140ms |
| 隔离拓扑 | project `cygnusx-ri095-acceptance`，internal 网络，无宿主端口，独占 PG/Redis/私有卷 |
| PG / Redis | `ri095_acceptance/project_export_test_ri095`，PostgreSQL 14.23，redis 7.4-alpine |
| 应用身份 | UID/GID 10001，cap_drop ALL，no-new-privileges，tmpfs `/tmp` + 私有卷回读 PASS |
| 队列 | `ri095_acceptance`，Broker DB1 / Backend DB2 |
| 写门禁 | READS/WRITES/PDF 按阶段开启；RESEARCH_DELIVERY_WRITE、AGENT_DOWNLOAD_WRITE、AGENT_ANALYSIS_WRITE 全程 false |
| 证据保留 | 停止后 3 个卷保留；未执行 `down -v`、未 downgrade、未清空证据 |

本轮未触及生产 `.env`、生产数据库、生产凭据；未改变生产默认门禁。

## 4. 镜像与前端真实构建

| 镜像 | tag | digest (sha256) |
|---|---|---|
| 前端（含 D4 修复） | `127.0.0.1:5000/ri095-frontend-fixd4` | `c23901d6c01f2592d89a62d5d47700018a32bea0118d8bccd38905e431df1e99` |
| 应用 + PDF 工具链 | `127.0.0.1:5000/ri095-app-pdf` | `aa87d0329fb60f2a19ceb422f89706038b722339a6da13bb9a761e409542f7e4` |
| 应用基座（含 D3 修复） | `cygnusx-ri095-app:auth-d9c92cf6ee1c` | `812e0fd8df9d7fba589925afea11b5b09ab7144000a49b45e1a540e962a6e3f5` |
| 浏览器（Playwright 1.49.0 / Chromium 131） | `127.0.0.1:5000/ri095-browser-auth` | `93174f73acae553dd5aa65fc93dc878b3d9302b44c3a616ea5e750d84373d840` |
| PostgreSQL / Redis | `127.0.0.1:5000/ri095-postgres` / `ri095-redis` | `206431915c6d...` / `41a05f1df0e4...` |

**前端确定性构建（真实执行）**：

1. 发现既有 lockfile 三处缺陷：根 name 漂移（`omichub-frontend`→`cygnusx-frontend`）、
   `@esbuild/*` 26 个平台包 0.28.1 vs 需要的 0.28.2 不同步、两个手工补入的 Sass 嵌套
   stub 无 `version` 字段（导致 npm 11 arborist `Invalid Version:` 崩溃——此即历史轮
   误判为"网络阻断"的真实根因）。
2. 以 npm 11 重新生成规范 lock（`npm install`，675 packages，Node20 npm10 与 Node24
   npm11 双重验证 `npm ci` 均通过），`/tmp` 干净目录真实 `npm ci` exit 0。
3. `npm run build`（prebuild 构建 Treasure Mouse 子模块依赖 → `vue-tsc -b && vite build`）
   exit 0；dist 逐文件 SHA 见 `frontend-build/dist-sha256.txt`（680 文件）。
4. `package-lock.json` SHA-256：`995b06832aa2bdea3b31e912e5ddfee64b61e4957808c2f9719f6ee03c56d35e`（D4 修复后前端镜像以此 lock 构建）。
5. 部署镜像内 `/usr/share/nginx/html` 与本轮构建产物一致（镜像即由该构建产出）。

## 5. 逐 Gate 结果

| Gate | 状态 | 实际证据 |
|---|---|---|
| Compose 隔离 + 八项负例拒绝 | PASS_STATIC | preflight + `checks.py` 六项 + 未授权变量拒绝 |
| 实际容器 UID/GID / tmpfs / 私有卷回读 | PASS_RUNTIME | `environment/permissions.txt`：uid 10001，写→fsync→回读 PASS |
| Alembic DAG（111 revs，唯一 head `projectreport01`） | PASS_STATIC | `audit_migrations.py`；CREATE 先于 ALTER |
| 空库 upgrade → head | PASS_RUNTIME | `migration-results/fresh-db-upgrade-head.log`：111 revs，当前源码+镜像 |
| **已有数据库升级兼容性** | **BLOCKED — LEGACY DATABASE BASELINE MISSING** | 无批准的脱敏旧库 schema/version/数据/制品基线；禁止以空库成功代替 |
| RA02 PostgreSQL 约束（11 断言，精确 SQLSTATE） | PASS_RUNTIME | `ra02/ra02-results.txt`：23514×5、23503、P0001×2、23505、00000×2，PG14.23 |
| RA03 并发/幂等/advisory lock | PASS_RUNTIME | `ra03/e2e-ra03.log`：8 并发真实 API 全 200 → 唯一 job，attempt_count 一致 |
| RA04–06 Celery | PASS_RUNTIME（部分范围） | 真实 Broker/Worker/Beat；注册表限 4 任务；重复投递幂等；Beat reconcile 正常；**阶段级故障注入未实现，标 PARTIAL 范围** |
| Report HTML | PASS_RUNTIME | Worker 生成 6635 B；DB/磁盘/HTTP 三处 SHA 一致；中文+provenance |
| **Report PDF** | **PASS_RUNTIME** | `pdf_status=PDF_GENERATED`，44369 B，3 页，中文可提取，`DroidSansFallback` 嵌入；DB/HTTP SHA 一致（`chain/report.pdf`、`report.pdf.txt`） |
| PDF 失败保留 HTML | PASS_RUNTIME（机制） | 渲染器抛 `AuditPdfRenderError` 时 HTML 已发布不受影响（源码路径核验 + D3 修复前失败保留行为） |
| 私有存储/FileRegistry | PASS_RUNTIME（本地范围） | 原子发布→回读；owner 归属；**漂移/丢失/symlink/配额注入需可信基线，未覆盖** |
| **对象存储** | **BLOCKED — 无授权测试 Bucket** | 本地后端通过不能替代 |
| JWT / 授权 | PASS_RUNTIME | 10 步全过：JWT/API key 契约按真实 `CurrentUserId`/`CurrentJwtUserId` 核验；跨 owner 404；无认证 401（`auth/e2e-auth.log`） |
| **M0 → Report → M1(V2) → ZIP** | **PASS_RUNTIME** | `chain/`：ExportSelectionV2 schema `cygnusx.project_delivery.v2`；`report_artifacts` 含 HTML+PDF；ZIP 成员含 `project_reports/<job>/report.html|pdf`；`verify_archive` OK；M0 字节前后不变；跨 owner 下载 404 |
| **历史制品不变性（多轮间）** | **BLOCKED — 需冻结历史 M0/ZIP 基线 corpus** | 无批准 corpus，不伪造 |
| **Browser sandbox 启动** | **PASS_RUNTIME** | `chromiumSandbox:true`，Chromium 131.0.6778.33，零 capabilities（CapEff=0）；解锁方式见 §9 |
| **Browser 业务链路三宽度** | **PASS_E2E（31/34 步）** | 登录/项目列表/详情/交付面板/预览/细节/刷新持久化/键盘/无溢出/console 清洁 ×1920/768/390 全过；`export_ready` 按钮 spec 等待未命中（幂等创建时序，非产品缺陷，见 §7） |
| 阶段级故障注入 | PARTIAL | 未实现受控、可复核注入点；未以随机 kill 冒充 |

## 6. PDF 真实验收（RC02 核心）

工具链在**同一 Worker 镜像**内探测（`environment/versions.txt`）：
`pandoc 3.1.11.1` / `typst 0.13.1 (8ace67d9)` / `fontconfig 2.15.0`，
`Droid Sans Fallback`（`/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf`）
+ Noto CJK 全家族。构建锚定 `Dockerfile.pdf`（TYPST 0.13.1 musl 二进制，SHA-256 校验通过）。

真实业务链路生成（`chain/`）：

```text
scientific-summary job (format=html_pdf) → Worker 消费 → html 6635 B + pdf 44369 B
pdf_status = PDF_GENERATED
html sha256: 35cc6c13289b46c128588b4054119efaba2247f33da28bde555a4c438c39161b（DB=HTTP=磁盘）
pdf  sha256: e829440a2ca232726b34b7ca2a2cf0d413583337db0036d4ac8f79d60c7a7e83（DB=HTTP=磁盘）
pypdf 解析：3 页，1752 字符，中文可提取（report.pdf.txt 前 25 行为真实正文）
```

独立渲染探针另证：24057 B `%PDF-`，pypdf fonts=`/DroidSansFallback`，分页正确。

## 7. 浏览器业务 E2E（RC02/RC03 核心）

- 运行方式：Playwright + **真实 Chromium sandbox**（`chromiumSandbox: true`；**未使用
  `--no-sandbox`**），容器内 `cap_drop ALL` 生效（`CapEff: 0000000000000000`）。
- 三宽度 1920/768/390 × 每宽度 11+ 步；截图 8 张/宽度、console.json、network.json 全部留存。
- 通过项：登录（真实表单）→ 项目列表 → ProjectDetail → 交付面板（刷新科研成果）→
  导出预览（3 个 details 区块）→ 刷新持久化 → 键盘焦点 → 无横向溢出（0px）→
  console 清洁（业务错误 0；仅 cookies/ws WebSocket 为 acceptance nginx 无 WS 代理的环境产物）。
- `export_ready`：按钮等待未命中。诊断结论：该项目在 API 驱动器阶段已对同一 M0 摘要
  创建过导出，UI 确认时幂等创建直接返回既有 ready job；spec 的 `p[role=status]` 轮询
  与按钮渲染存在竞态。**后端 ready 行为由 API 驱动器 30 步全 200 证明，非产品缺陷**。
- 本轮修复 D4 后：422 消失、业务 console 错误清零（`attempt2-fixed/browser-e2e.log`）。

## 8. M0 → Report → M1(V2) → ZIP 完整交付链路（RC03 核心）

`chain/` 15 步全过（`e2e-chain.log`）：

```text
M0（默认 evidence 导出 ZIP，7372 B）→ HTML+PDF 报告 job → ready
→ ExportSelectionV2（schema cygnusx.project_delivery.v2，source_manifest_job_id + project_report_job_ids）
→ M1 manifest.report_artifacts = [{html, sha…61b}, {pdf, sha…e83}]
→ V2 导出 ZIP 60429 B，archive_sha256 b112317efde17e3e2b07d2847771bd52f03d3ed6785a36295be5594db7ee2a2c
→ ZIP 成员：ProjectDeliveryManifest.json / README.md / checksums.sha256 /
   project_reports/c3698987-…/report.html / project_reports/c3698987-…/report.pdf / verify_project_delivery.py
→ 仓库自带 stdlib 验证器 verify_archive OK
→ JWT 下载 SHA = DB archive_sha256；跨 owner 下载 404；M0 字节前后不变
```

历史轮记录的「默认导出 ZIP 不含项目报告」缺口，本轮以真实 `ExportSelectionV2`
验证关闭：**ZIP 内包含 HTML 与 PDF 报告原件**。`evidence_status=partial` 如实声明。

## 9. Chromium sandbox 解锁（含授权记录）

历史轮的「宿主 AppArmor 限制非特权 userns」诊断**不完整**。本轮实测：

- 宿主 `apparmor_restrict_unprivileged_userns=1`，容器内 `unshare -U` 失败；
- 但**有效阻断者是 Docker 默认 seccomp profile**——它把 `unshare/clone(CLONE_NEWUSER)`
  等命名空间 syscall 限制在 `CAP_SYS_ADMIN` 之后；
- Playwright 默认 `chromiumSandbox:false`，历史轮与本轮早期的"成功"均为无沙箱。

处置（**用户已明确授权**"Authorize narrow container seccomp"）：

- 生成 `deploy/acceptance/seccomp-browser.json`：以 Docker 默认 profile 为基，
  **仅移除 namespace syscall 组的 `includes.caps=[CAP_SYS_ADMIN]` 门**并显式放行
  Chromium 命名空间沙箱所需 syscall；其余规则逐字保留。
- compose `browser` 服务加 `security_opt: [no-new-privileges:true, seccomp=…]`，
  `cap_drop ALL` 保留；control.py 校验 profile 路径 + 不许放弃 cap_drop。
- 结果：**Chromium 真实 userns 沙箱启用**（`chromiumSandbox:true` 启动成功），
  零有效能力，`--no-sandbox` 从未使用。此为**启用**沙箱，非绕过；未修改任何宿主
  安全策略（AppArmor/sysctl 未动）。

## 10. 修复文件与最小 diff（均未提交，随工作树）

| 文件 | 修复 |
|---|---|
| `frontend/package-lock.json` | 规范重生成（修 D4 前置：Invalid Version / esbuild 不同步 / 根 name 漂移） |
| `src/cygnusx/application/services/report_audit_pdf_renderer.py` | D3：`cwd=temp` + `TMPDIR` |
| `frontend/src/components/ProjectResearchDelivery.vue` | D4：`request_key` 兜底生成 |
| `deploy/acceptance/Dockerfile.pdf` | 新增：PDF 工具链（pandoc/typst/fonts，digest 校验） |
| `deploy/acceptance/seccomp_browser.py` + `seccomp-browser.json` + `docker-seccomp-default.json` | 浏览器沙箱解锁（已授权） |
| `deploy/acceptance/compose.yml` / `control.py` | browser seccomp 配置 + 校验 |
| `deploy/acceptance/browser-e2e.cjs` / `run-browser-e2e.sh` / `probe-create.cjs` / `ra02_runner.py` / `e2e_driver.py` / `repro422.py` / `seccomp_browser.py` | 本轮新增验收/诊断执行器 |

## 11. 未解决问题与解除条件

| 阻塞项 | 解除条件 |
|---|---|
| 已有数据库升级兼容性 | 提供批准的脱敏旧库副本（schema/`alembic_version`/数据/制品基线），在隔离卷上升级前后留证 |
| 对象存储 | 授权独立测试 Bucket/凭据/前缀后单独验收 |
| 存储 漂移/丢失/symlink/配额注入 | 随 corpus 提供可信基线摘要 |
| 历史 M0/ZIP 多轮不变性 | 提供冻结的历史 M0 + ZIP 基线 corpus |
| 阶段级故障注入 | 实现最小受控注入点并审查目标与清理方式 |
| RA04–06 逐 Gate 原文定义 | 提供原始 Gate 定义（本轮只报告可观测行为，未自行重编号） |
| 浏览器 `export_ready` spec 时序 | 幂等创建路径下按钮轮询逻辑可后续改进；非产品缺陷 |

## 12. 回滚与资源清理记录

- `rollback/flags.txt`：READS/WRITES/PDF 当前 true（等待人工决定是否保持只读继续验收）；
  保护性执行 flag（delivery/download/analysis write）全程 false。
- `rollback/containers-after-stop.txt`：6 容器全部 Exited(0)。
- 3 个卷（postgres-data / private-storage / redis-data）保留；未执行 `down -v`、
  未 downgrade、未 prune；开发栈（cygnusx-web/worker/beat/nginx 等 37 容器）未受影响。
- 开发栈此前存在的一次 acceptance 项目 stop/down 复用为本轮 fresh-DB 重验做数据卷
  重置，仅作用于 disposable 验收库。

## 13. 生产准入建议

**保持关闭。** 本轮达成核心 PASS_RUNTIME 与 PASS_E2E，但：历史数据库升级兼容性、
对象存储、历史制品不变性三项前置条件缺失仍未解除；且全部修复文件未提交、镜像
digest 基于未提交工作树。建议顺序：提交修复 → 补旧库副本与测试 Bucket → 复跑
剩余 BLOCKED 项 → 人工复核本报告与 `artifact-index.json` 后再评估下一阶段准入。
