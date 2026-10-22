本轮已完成隔离实施和物证采集，待你验收。实现位于 `/tmp/cygnusx-session-lineage-q2usvvh7/worktree`；现有部署源码、根 .env 和生产数据库未作本轮修改。源码执行硬门仍为 false，试点没有启动 Worker 或真实计算。没有提交、推送或部署。

增量交付为 [implementation.patch](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/implementation.patch)（18 个文件，只包含本任务相对原工作区的差异），已执行 `git apply --check`，未实际应用。逐文件 SHA-256 见 [changed-files.json](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/changed-files.json)。既有阶段 0 和其他脏文件不混入该增量补丁；工作树本身保留任务开始时的基线内容。

只读开放与空状态物证：

- [Part A HTTP](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/part-a-http.json)：科研计划、交付链、inventory 和 capability-status 四个入口，匿名 401、非 owner 403、owner 200，共 12 个实际请求。
- [初始真实 PG 计数](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/part-a-db-counts.json)：research_plans、datasets、dataset_versions、dataset_analysis_links、platform_runs、tasks、reports、project_export_jobs 全部为 0。
- [浏览器结果](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/browser-results.json)、[网络记录](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/browser-network.json)：真实登录后，三卡片分别为空状态，科研接口均为 GET 200，没有自动创建计划，没有页面脚本错误，导出未开放。
- 三张截图：[计划空状态](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/browser-plan-empty.png)、[交付链空状态](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/browser-delivery-empty.png)、[清单空状态](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/browser-inventory-empty.png)。

会话试点使用已登记的双端 FASTQ，服务端从会话解析归属。数据库关联为：

```text
session  4854f3ac-2ccd-45c4-8739-754de33d0f89
project  966b1dcd-43bd-4dd0-8d7c-8d9290c86799
Dataset  53e1f384-3f1f-470a-9a81-68bad70c9010
Version  ff45fe21-9b80-4009-ba14-58505a992b53
Link     c075f3cf-920d-4142-91fe-c184646ee4aa
Run      3994b334-77c9-42b7-998e-c011cf7a3790
Run key  dataset:c075f3cf-920d-4142-91fe-c184646ee4aa
Handoff  81cca2d14ca0362e8e0647bbfde649e531d8e3c6dcda6d2f625959189e341d07
```

- [Part B HTTP](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/part-b-http.json) 包含实际注册、JWT assay/分组审阅、冻结与预案、相同请求复用、改变请求拒绝、JWT 人类审批 API 返回 APPROVED、两入口 execute 返回 403。审批由验收脚本使用隔离 owner 的 JWT 调用既有人类审批端点；模型参数不能提供 approved 或 group_confirmed。
- [最终真实 PG 物证](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/final-db-evidence.json) 含 owner/project、source_snapshot 的真实 session/invocation、review_annotations、完整冻结 Handoff、Link、Run 和共享 request_key。[完整 SQL 与关联记录](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/part-b-db-evidence.json) 保留原始只读查询。
- [inventory](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/part-b-inventory.json) 返回非空链，compute_state=PREPARED、delivery_state=BLOCKED、TASK_NOT_CREATED、task_id=null、export_enabled=false。审批状态在既有确认存储中为 APPROVED；不把 Link 的 PREPARED 或无 Task 当作计算成功。
- [最终源码 HTTP 检查](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/final-http-checks.json) 26 项实际请求：文件/任务/报告权限逐项撤销时三只读接口均拒绝 403、能力状态不可用；inactive 用户 401；未绑定会话、跨用户会话、模型伪造身份与确认字段、项目归档均拒绝；直接 Task API 的 run: 身份返回 409。早期未绑定/跨用户/身份伪造见 Part B HTTP。
- [真实并发重试](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/concurrent-retry-http.json)：两个 HTTP 请求复用同一 Dataset/Version/Link/Run，没有新链或 Task。
- [三重门物证](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/three-gate-evidence.json)：源码 WRITE_RUNTIME_ACCEPTED=false；AGENT_ANALYSIS_WRITE_ENABLED=false、ANALYSIS_SUBMIT_FROM_DATASET=false；冻结 worker_paths_verified=false。真实库调用共用的 Worker 输入检查得到 WORKER_PATHS_NOT_VERIFIED；两 HTTP execute 先被源码门拒绝，确认仍 APPROVED 未消费，冻结 digest 未变。
- [后端访问日志](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/http-access-evidence.log) 保留专用 API 实际 method/path/status，未记录登录密码或 Authorization。

最终真实 PG 计数为 Dataset=2、Version=2、Link=1、Run=1，Task/Report/ResearchPlan/ExportJob 均为 0。第二个 Dataset 是先前单端测试文件缺少 R2、被现有 RNAFlow 校验拒绝后留下的未冻结审阅记录；只有双端输入那一条形成完整冻结链。失败记录没有删除或冒充成功，[命名修正记录](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/fixture-correction.txt)、attempt3/attempt4 HTTP 和 [原验证诊断](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/prepare-validation-diagnostic.json) 均保留。

本轮开关与确认：

| 项目 | 隔离状态与理由 |
| --- | --- |
| RESEARCH_PLAN_ENABLED | true；Part A 计划读取与 PLAN_ONLY 空状态 |
| RESEARCH_DELIVERY_READ_ENABLED | true；交付链/inventory 读取 |
| TOOL_GATEWAY_READ_ENABLED | true；读取服务端真实会话上下文并准备元数据 |
| DATASET_DISCOVERY_READONLY | true；含元数据登记、审阅、冻结和预案准备；已先交清单，按你回复“继续”仅用于隔离试点 |
| assay/分组 review、proposal approve | 使用既有 owner JWT 端点；初次声明不自动成为人工审阅或批准 |
| WRITE_RUNTIME_ACCEPTED / worker_paths_verified | false；源码不改，冻结摘要不伪造 |
| 其余科研写门 | 全部 false，完整逐项列表见 gate-review.md 和 flag-history.json |

[先行门禁清单](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/gate-review.md)、[用户回复记录](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/metadata-gate-approval.json)、[实际隔离进程开关历史](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/flag-history.json)、[最终进程开关](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/final-api-handle.json) 可互相对照。DATASET_IMPORT_WRITE、下载、分析提交、科研成果采集、报告/PDF、导出、counts Flow、寻宝鼠写工具和任务取消均没有开放；默认配置未变。

实现位置：

| 文件与行号 | 改法 |
| --- | --- |
| [src/cygnusx/application/schemas/agent_tools.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/schemas/agent_tools.py:60) | 严格 FASTQ 输入契约；拒绝模型身份、确认与审阅字段；目录与路径由服务端解析。 |
| [src/cygnusx/application/services/agent_tool_gateway.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/services/agent_tool_gateway.py:210) | 在既有可信 context 与能力校验后接入元数据准备。 |
| [src/cygnusx/application/services/session_dataset_preparation_service.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/services/session_dataset_preparation_service.py:41) | 锁真实会话、复核 owner/project/active/模块/显式 Sample 与 FileRecord；复用既有四连服务、人工审阅及幂等重试。 |
| [src/cygnusx/application/services/dataset_analysis_service.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/services/dataset_analysis_service.py:528) | execute 仅使用服务端保存的 Run 别名；源码/配置/Worker 门检查保持在写入之前。 |
| [src/cygnusx/application/services/run_plan_service.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/services/run_plan_service.py:70) | 既有 Run 复用 dataset:{proposal} 身份；confirm 委托同一 Dataset 预案/确认；按 Link→Run 顺序锁定。 |
| [src/cygnusx/application/services/task_service.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/services/task_service.py:59) | 服务端 run_id 在 Task 同一事务内绑定 Run/Link/Event，提交后才入队；拒绝客户端 run: 保留身份；旧孤立 Task 返回人工对账，不自动纳管。 |
| [src/cygnusx/application/services/project_service.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/application/services/project_service.py:454) | 统一项目 owner 的 404/403 边界；读能力同时核对 files/tasks/reports，匹配 inventory 权限。 |
| [src/cygnusx/api/v1/research_plans.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/api/v1/research_plans.py:22) | 项目科研计划先验证实际 owner；非 owner 明确 403。 |
| [src/cygnusx/api/v1/research_delivery.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/api/v1/research_delivery.py:241) | 项目交付与 inventory 先验证 owner；交付入口补充 tasks 模块权限复核。 |
| [src/cygnusx/api/v1/runs.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/src/cygnusx/api/v1/runs.py:51) | Dataset Run 别名要求 owner JWT 和原确认 ID，复用 Dataset execute，不消费第二套确认。 |
| [frontend/src/views/ProjectDetailView.vue](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/frontend/src/views/ProjectDetailView.vue:583) | 第三卡片按交付读取能力展示，导出写门独立保持关闭。 |
| [frontend/src/views/__tests__/ProjectDetailResearchContext.test.ts](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/frontend/src/views/__tests__/ProjectDetailResearchContext.test.ts:88) | 覆盖读取开放、导出关闭时挂载清单。 |
| [tests/unit/test_research_plan_storage_phase5.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/tests/unit/test_research_plan_storage_phase5.py:27) | 调整项目 REST 非 owner 期望为 403；内部资源服务原边界不变。 |
| [tests/unit/test_session_dataset_preparation.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/tests/unit/test_session_dataset_preparation.py:98) | 真实 SQLite/文件验证审阅→冻结→预案、复用、参数伪造、权限撤销和输入变化。 |
| [tests/unit/test_run_task_atomic_binding.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/tests/unit/test_run_task_atomic_binding.py:24) | 真实事务检查提交前绑定、入队前可见、回滚不留 Task/Event、幂等不重投、历史孤立 Task 不纳管。 |
| [ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md:5) | 同步四连、Run 身份/事务、权限及隔离门禁事实。 |
| [ARCHITECTURE_DESIGN/CygnusX_research_plan_architecture.md](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/ARCHITECTURE_DESIGN/CygnusX_research_plan_architecture.md:5) | 同步三卡片只读空状态及独立试点边界。 |
| [tests/unit/test_project_lifecycle.py](/tmp/cygnusx-session-lineage-q2usvvh7/worktree/tests/unit/test_project_lifecycle.py:153) | 验证读取能力的 tasks 权限撤销。 |

验证结果：

| 检查 | 输出 |
| --- | --- |
| 相关后端回归 | [69 passed](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/backend-targeted-final.log)；含新增会话/事务测试与项目能力门 |
| 既有交付/执行证据回归 | [34 passed](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/backend-delivery-regression.log) |
| Bridge | [190 passed、2 skipped](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/bridge-tests.log) |
| 前端全量 | [92 文件、629 passed，复跑 exit 0](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/frontend-all-recheck.log)；首次存在 ResizeObserver/jsdom 清理异常而 exit 1，原始输出保留在 frontend-all.log |
| 前端类型与构建 | vue-tsc 与 Vite build exit 0；[类型检查](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/frontend-typecheck.log)、[构建](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/frontend-build.log)；构建目录为 /tmp/cygnusx-session-lineage-build |
| 迁移 | [检查通过](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/migration-check.log)；[唯一 head=project_lifecycle01](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/alembic-heads.log)，本任务没有新增表或迁移 |
| 变更域 Ruff | [通过](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/ruff-targeted.log)，另含 project_lifecycle 权限测试检查 |
| 变更域 mypy | [2 个错误](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/mypy-targeted.log)，为 TaskService 既有 user 变量复用；[影子基线同 2 个错误](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/mypy-task-baseline.log) |
| 全仓 Ruff / mypy | 未全绿：[Ruff 271](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/ruff-full-final.log)；[首次全量 mypy 1008](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/mypy-full.log) |

全量后端也未全绿：[初次 unit+e2e](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/backend-full.log) 为 3986 passed、15 failed、22 skipped；[完整配置的隔离 unit](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/backend-unit-canonical-final.log) 为 3975 passed、14 failed、16 skipped；[完整配置的隔离 e2e](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/e2e-canonical-isolated.log) 为 5 passed、7 failed、6 skipped。未把这些失败计为通过，也没有提交或发布。7 个既有 unit 失败在原工作区源码复现，[基线对比](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/baseline-eight-unit.log)；Provider 单跑通过但全量失败仍保留，未作豁免。7 个 LangGraph e2e 失败在原源码、同隔离依赖下复现，[e2e 基线](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/e2e-baseline-isolated.log)。补充隔离全量因 telemetry 禁用、私有存储和 Redis 缓存产生的差异及精简配置的 37 个失败均原样保留，[环境说明](/home/zj/zj_code_libarary/OmicHub/evidence/project-session-lineage-20261022/unit-isolation-note.txt)。本任务的真实 HTTP/PG/Redis 和浏览器物证独立保留，不以单测结果替代运行验收。

专用服务在物证采集完成后关闭；专用 PostgreSQL/Redis 容器及数据保留，详见 closure.json。重放所需的测试账号与连接环境只放在 runtime-handle.json 所指私有目录（0600），不在交付文档中公开。验收结论及后续发布准入由你决定。
