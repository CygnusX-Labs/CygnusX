# 可复现报告 Phase 1 实施与验收记录

本轮在当前工作区实施 RNA-seq 执行证据报告，没有提交、推送、部署或运行生产迁移。任务范围来自附件 Phase 1 要求；活动架构见 [CygnusX_report_architecture.md](../../ARCHITECTURE_DESIGN/CygnusX_report_architecture.md)，最终设计见 [Phase 1 设计](../design/reproducible-report-phase1-design.md)。

**结论：Task → ReportSnapshot → HTML → 现有 ReportsView → 下载的代码闭环与隔离交付验证已完成；真实科研任务和现场异步/存储交付尚未验收。不能据此宣称已具备经过现场验证的真实生产交付能力。**

## Phase 0 八项门槛核验

已读取可行性调查、Phase 0 设计和 Phase 0 实施记录，并以实际四个源模块和测试重新检查。

| 门槛 | 实际证据与边界 |
|---|---|
| Task-first 身份 | DatabaseTaskEvidenceSource 按 Task.id + owner 查询；validate_records 再校验；隔离 ASGI Task 主键最终进入报告正文和快照 |
| Run 可以缺失 | 普通合成 RNA Task 完成全链；Phase 0 确认 Run 关联、错误 Run、歧义/跨 owner 用例保留 |
| Schema 序列化 | Frozen Pydantic、canonical JSON、重新验证 payload/digest；独立 DB 行回读通过 |
| 证据状态 | 六种状态有定义；QC 文件不产生 pass；未重跑恒为 not_run |
| 历史环境隔离 | 缺失输入、软件、镜像和参考库指纹保留缺口；新审计元数据不使用当前 Flow 版本 |
| 不越权读文件 | owner/personal/Task 显式关联、owner 路径边界；新增 pinned FD/O_NOFOLLOW/普通文件检查与目录竞争测试 |
| 稳定指纹 | stable_facts.v1 排除采集时钟；重采同事实复用报告，新字节不依赖 Task.updated_at 产生新版本；旧 optional 空字段不破坏摘要 |
| 区分新旧快照 | 追加 snapshot row、facts digest、redaction v1/v2、Report parent_id/version；发布失败重试仍引用原 snapshot_id |

原始 Phase 0 38 个合成单测全部回归通过。真实普通 Task / 已确认 Run 两种入口仍缺少可连授权环境，不能把合成记录当成真实数据验收。本轮没有发现必须重写 Phase 0 身份协议的 P0 阻塞；补充的是安全读文件、预算和版本化展示标签。

## 修正草稿中影响交付的问题

发现并修正：用户 ID 字符串/UUID 边界错配；Job 未提交即投递；只按 Task.updated_at 忽略新磁盘证据；没有并发 worker 锁；固定输出路径覆盖历史报告；重试重新采集而不是复用冻结快照；快照缓存未显式限定 owner/Task；原始异常消息可能泄漏路径/凭据；legacy tasks 新写入；原报告查询遇到独立审计多版本不再唯一；报告中心按 Task UUID 搜索标题导致错过目标；下载裸链接缺少 Bearer；新窗口 HTML 执行权限；预览请求关闭/切换竞争。

草稿 migration 使用已存在的 b7c8d9e0f1a2 revision，且 ORM 重复定义 ix_report_snapshots_task_id。已改为唯一 reportauditphase1、接在真实 dynamicrouting03 head 后并移除重复索引。没有改写已经存在的历史迁移，也没有执行真实库升级。

## 修改文件清单

| 文件 | 实际作用 |
|---|---|
| `application/schemas/report_snapshot.py` | optional 安全文件名、兼容旧摘要、版本化 v2 标签投影 |
| `application/services/report_snapshot_sources.py` | 有界 FileRecord 采集与截断标记 |
| `application/services/report_snapshot_manifest.py` | pinned FD 读取、普通文件约束、时间/字节预算、Unicode 安全标签 |
| `application/services/report_snapshot_builder.py` | 保留 Phase 0 构建、增加名字与缺口、使用显式 redaction v2 |
| `application/services/report_audit_renderer.py` | audit-v1.0.0 八模块、状态、导航、转义、CSP、离线布局 |
| `application/services/report_archive.py` | 本地 FD 原子发布/fsync、受控回读、对象存储 stream 适配 |
| `application/services/reproducible_report_service.py` | owner/终态/Run 校验、请求和事实去重、冻结、状态、恢复发布 |
| `application/services/report_service.py` | 复用报告登记/版本、目录/FileRegistry、SHA-256 预览与下载、安全错误 |
| `application/schemas/report.py` | 类型、版本、证据完整性、Job/快照 DTO、Task 筛选、文件 SHA |
| `infrastructure/database/models/report.py` | 独立 Job、Snapshot、报告关联、唯一约束和 ORM immutability |
| `infrastructure/database/models/__init__.py` | 注册新增模型 |
| `infrastructure/database/repositories/report_repository.py` | Task ID 筛选、旧科学报告查询隔离、Select 返回类型 |
| `infrastructure/celery_app/tasks/reports.py` | 独立报告任务、跨 commit Task 锁、安全失败、恢复扫描 |
| `infrastructure/celery_app/celery.py` | include、analysis 队列路由和 Beat 恢复任务 |
| `core/config.py` | 报告时间/字节/尝试/恢复预算的 Settings |
| `infrastructure/storage/path_factory.py` | 新报告归档调用方登记；路径工厂既有创建语义保留 |
| `api/v1/tasks.py` | 创建报告 Job；可选 Run / UUID Idempotency-Key |
| `api/v1/reports.py` | Job 状态/安全重试、快照、Task 筛选、原下载入口兼容审计字节 |
| `alembic/versions/reportauditphase1_add_reproducible_report_tables.py` | 新表、扩展旧表、索引、不可变触发器、降级 |
| `frontend/src/api/report.ts` | Job / 快照 / 重试、统一鉴权 Blob 下载 |
| `frontend/src/types/report.ts` | 新报告与阶段 metadata |
| `frontend/src/composables/useReproducibleReport.ts` | 单击生成、串行轮询、恢复、失败、离页防护 |
| `frontend/src/views/TaskDetailView.vue` | RNA 终态入口、真实阶段、错误/证据缺口、指定 Report 导航 |
| `frontend/src/views/ReportsView.vue` | 精确报告预览、Task 筛选、鉴权下载 |
| `frontend/src/components/report/ReportCardMinimal.vue` | 类型/报告版本/模板/证据状态 |
| `frontend/src/components/report/ReportPreviewModal.vue` | 空 sandbox、下载、旧预览响应防护、明确 not_run |
| `tests/unit/test_report_snapshot.py` | Phase 0 既有回归文件，本轮保留其断言和局部 executor fixture |
| `tests/unit/test_reproducible_report_phase1.py` | Renderer、缺口、注入、离线、规模、错误/锁/路径/预算/迁移 SQL 等 |
| `tests/integration/test_reproducible_report_isolated.py` | 实际 SQLite ORM + 合成文件 + API、登记失败恢复、版本/去重/权限/下载 |
| `tests/integration/test_reproducible_report_postgres.py` | opt-in 实际迁移、并发唯一键、advisory lock、不可变触发器 |
| `frontend/src/composables/__tests__/reproducible-report.test.ts` | 六个生成/轮询/恢复/权限/离页场景 |
| `frontend/src/components/report/__tests__/report-preview-security.test.ts` | 实际 Vue 预览 iframe 隔离属性 |
| `frontend/src/components/report/__tests__/reports-delivery.test.ts` | 实际 ReportsView 的指定 Report 预览和下载入口 |
| `ARCHITECTURE_DESIGN/CygnusX_report_architecture.md`、`README.md`、`CygnusX_flow_architecture.md` | 活动 as-built 与索引回写 |
| 本文、`docs/design/reproducible-report-phase1-design.md` | 用户要求的设计与实施交付 |

上述后端路径均相对 `src/cygnusx/`（alembic/、tests/、frontend/、文档除外）。工作区原有 AboutView/FlowsView、生态图/Logo、docs/info、子模块 modified content 等其他改动保留，不纳入本报告变更，不声称由本轮修改。

## 数据库与 API

迁移新增 report_snapshots、report_generation_jobs，扩展 reports 的 report_kind/snapshot_id/template_version/evidence_partial 和 report_files.sha256。快照按 owner+Task+digest 唯一，报告按 owner+snapshot+template 唯一；活跃 Job 部分唯一约束、六状态检查约束；快照 ORM 和 PG trigger 拒绝更新。完成的 Report 通过已有版本树串联。实际库迁移执行与线上 schema drift 对账未运行。

| API | 行为 |
|---|---|
| POST `/api/v1/tasks/{task_id}/reproducibility-reports` | HTTP 202；owner + RNA 终态校验；可选 Run 与请求键；返回 Job |
| GET `/api/v1/reports/jobs/{job_id}` | 当前用户的生成阶段、错误、证据状态与最终 Report |
| POST `/api/v1/reports/jobs/{job_id}/retry` | 有界、可分类安全重试；保留原 snapshot_id |
| GET `/api/v1/reports/{report_id}/snapshot` | owner/Report 关联/内容校验后的脱敏快照 |
| 既有 GET `/reports` | 增加可选 task_id 筛选 |
| 既有 `/reports/{id}/preview`、`/reports/{id}/files/{file}/download` | 复用；审计 HTML 字节完整性校验、attachment 下载 |

项目成员资格没有被当作 owner 权限的替代；未开放分享/团队投影。不可任意传入服务器路径。非法 UUID 为 422，不存在/跨 owner 来源和快照返回 404，身份/完整性冲突拒绝。

## 验证结果

使用已有 `.venv` 和 frontend/node_modules，没有安装依赖或修改 lock。以下是实际执行结果；各类测试的证明范围不同，不合并成现场 E2E。

| 检查 | 结果与范围 |
|---|---|
| Phase 0 回归 | 38 通过：身份、Run 缺失、序列化、摘要、历史环境、脱敏、路径 |
| Phase 1 单测 | 24 通过：八模块/缺失/转义、离线、4000 产物、固定错误/恢复、worker 锁分支、迁移 SQL、FD/预算、旧字段兼容、Unicode 标签、对象存储错误、重试上限、Celery 注册 |
| 隔离集成 | 7 通过：Task 到实际 Snapshot/HTML/ReportService/API 下载，事实去重、新证据版本、存储/登记失败重试、访问/篡改/删除、不变性、数据库唯一约束 |
| 既有报告/版本/路径/安全相关 | 54 通过（环境局部 inline executor shim，原测试断言保留） |
| 新增与 Phase 0 合并验证 | 69 通过、3 个 opt-in PostgreSQL 测试跳过；最终命令见下文；既有相关 54 项另行通过 |
| 前端新增报告域 | 8 通过：6 轮询状态 + 实际 Vue 隔离预览 + 实际 ReportsView 交付 |
| 相关 Python Ruff | 通过 |
| 相关 15 个源文件严格 mypy | 通过（含 ReportService、repository、API） |
| migrations、alembic heads | 通过；唯一 reportauditphase1 head；新迁移 SQL 可编译 |
| storage paths 守卫 | 通过 |
| frontend vue-tsc --noEmit / npm run build | 通过，生成 dist；没有浏览器手工 E2E 结论 |
| bridge pytest | 190 通过、2 跳过 |
| 全仓 Ruff src/tests | 297 个存量错误，未清理无关文件 |
| 全仓 mypy | 1024 个错误 / 228 文件；本轮 touched 报告路径已通过独立 strict 检查 |
| 全前端 Vitest | 512 通过、7 个存量失败 / 519；失败在协作室发送、deep-thinking-stream、live-stream-render |
| 全 unit+e2e，not quarantine | 当时收集 2715 个选中用例，50 秒 timeout 退出 124；已观察 LangGraph、Agent 配置、handoff 的存量失败，无全绿结论 |
| git diff --check | 通过 |

报告域最终验证：

```bash
.venv/bin/pytest tests/unit/test_report_snapshot.py \
  tests/unit/test_reproducible_report_phase1.py \
  tests/integration/test_reproducible_report_isolated.py \
  tests/integration/test_reproducible_report_postgres.py -q

# 既有报告/安全用例再加入 report_service、repository、versions、storage_path_factory、
# security_fixes、security_round2；本 managed sandbox 需局部 executor shim。
cd frontend
npx vitest run src/composables/__tests__/reproducible-report.test.ts \
  src/components/report/__tests__
npx vue-tsc --noEmit
npm run build
```

沙箱独立 asyncio.to_thread wakeup 在 Phase 0 已证实不可用。本轮新测试沿用只在测试内执行相同文件操作的 inline fixture；既有报告相关命令额外加载 `/tmp/report_test_executor.py` 的局部 plugin。没有修改旧测试或屏蔽断言。这能验证实际取证/存储代码和结果，不能证明生产线程/事件循环调度。SQLite facade 使用真实 ORM/约束/文件系统，将 PG-only repeatable-read 指令显式留为不模拟，并只对测试适配 JSONB 与 UTC 类型；没有把它等同实际 PostgreSQL。

## 真实环境探针与未验收项

只读数据库配置不存在，授权 disposable report_test DSN 不存在；只读 endpoint 探针为 gaierror（不输出 URL/凭据）。Docker socket 被当前沙箱拒绝访问。没有查询真实 Task/Run，没有扫描其他用户目录，没有启动或重跑分析、部署服务或改历史科研结果。

因此：**真实 RNA-seq E2E 未通过验收；实际 PG advisory lock / trigger / 并发事务、实际 Celery/broker/Beat、实际 S3 发布、浏览器手工 E2E 均尚未验收。** opt-in PG 测试明确跳过，SQLite 冲突和 mock worker 锁分支不是现场并发证明。以下命令需可连、授权的独立数据库（数据库名 report_test*），不能指向生产配置：

```bash
CYGNUSX_REPORT_TEST_DATABASE_URL='<授权 disposable asyncpg DSN>' \
  .venv/bin/pytest tests/integration/test_reproducible_report_postgres.py -q
```

本轮未提交，因为全仓提交门禁未全绿；不将上述存量失败扩展成无关重构。没有现场 PostgreSQL 迁移、schema drift 对账或真实报告 ID 可以提供。

## 能力、限制与最终检查点

| 检查点 | 当前结论 |
|---|---|
| 1 Phase 0 数据契约 | 代码核验与 38 回归通过；真实来源验收依然缺环境 |
| 2 Task 详情生成入口 | 已接入、前端状态测试通过 |
| 3 Celery 异步取证和 HTML | 独立 worker/route/Beat 代码已接入；业务 worker 集成验证通过；现场 Celery 未验收 |
| 4 持久化/现有报告中心 | 实际隔离 ORM、磁盘、目录/FileRegistry 与版本验证通过 |
| 5 安全查看/下载 | ASGI 到实际 bytes 与 ReportsView 入口/空 sandbox 通过；真实浏览器现场未验收 |
| 6 八模块 | 实际冻结快照、缺口、Hash、时间、not_run、规模和离线测试通过 |
| 7 不伪造历史 | 保留来源/缺口；未使用当前环境/LLM/推造步骤；QC 无 pass，复现未运行 |
| 8 重复/失败/并发 | 请求复用、事实唯一、重试冻结、登记恢复通过隔离验证；PG 现场并发测试未运行 |
| 9 相关安全/回归 | 报告域和既有相关测试通过；全仓门禁有明确存量失败 |
| 10 真实 RNA E2E | 未通过验收，已按任务允许的无真实环境分支完成隔离集成并明确说明 |

当前能够在迁移和依赖就绪的授权环境中使用生成入口、独立 Job、冻结快照、八模块离线 HTML、版本归档、报告中心预览/下载。功能实现不能代替现场交付承诺。

实现边界：owner-only；历史 RNA 证据只读本地，S3 输出适配不代表远程证据适配；无可信项目关联时不猜项目；自由标签可脱敏；跨 DB/FS 无统一原子快照；digest 不是签名；未新建孤立 private 归档/快照自动 GC；禁用平台预览中的科学报告脚本交互，保留下载；没有导出日志/Prompt、分享、PDF、重运行或结果比较。

进入 Phase 2 的前置条件是：授权可连的 PG/broker/存储，实际迁移与锁/恢复测试，一份真实成功 RNA Task（最好另含显式 Run）的浏览器闭环与下载核验。科学复现等级提升还需执行期输入/环境/参考版本、工具与步骤 IO、QC 阈值/决定/豁免，以及固定 BioReport 输入/渲染版本契约。Phase 2 功能本轮没有提前实现。
