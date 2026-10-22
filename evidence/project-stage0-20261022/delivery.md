# 阶段 0 施工交付与用户验收入口

状态：A–F 已实现，附自动验证及隔离运行证据；**待用户验收，不代表用户已接受或生产已部署**。

现有 cygnusx 部署、根 .env 和科研开关未修改；生产数据库未执行本次迁移。测试 API/PG/Redis 使用独立实例和随机私有凭据，不读取现有业务数据。阶段 1 按用户要求只读调查，结论在对话交付，不写入本文件或改其业务代码。

## 根因 → 改法 → 定位

| 项 | 根因 | 实现与定位 |
| --- | --- | --- |
| A | 删除保留目录，list/count 隐式回填又重建身份 | `src/cygnusx/application/services/project_service.py#delete_project` 原子记录 tombstone；list/count 只读；`sync_from_disk` 显式同步、跳过删除身份/隐藏目录/符号链接；create/delete/sync 共用 owner 行锁 |
| A 取舍 | Task、FileRecord、报告、Studio、协作室与工具均引用 slug 目录，移动目录有兼容成本 | 采用独立 `project_tombstones`，保留 project_id/user_id/slug/deleted_at，不重命名物理目录。已删 slug 不可复用，防止新身份冒领旧数据。路径引用全文见 path-references.txt |
| B | overview 服务和 DTO 均漏传 settings，前端也不回填 | `project_overview_service.py#_load_project` + `schemas/project.py#ProjectMetaDTO` 返回 settings/status；`ProjectDetailView.vue#loadOverview` 按当前响应恢复开关；设置保存响应也有项目 generation guard |
| C | NULL 与 active 双表示 | `alembic/versions/project_lifecycle01.py#upgrade` 回填 NULL，设置 NOT NULL DEFAULT active；ORM 同步。读取 NULL 兼容保留至 lifecycle02 |
| D | PATCH 不支持 name/description，settings 整体替换；多字段更新分两次提交 | `project_service.py#update_project` 行锁后先完整校验、一次提交；RFC 7396 递归合并/数组替换/null 删除，根 settings:null 显式清空。name/description 校验与创建一致，slug 不变 |
| E | 活文档状态、删除、runs 发现描述漂移 | 就地更正 `ARCHITECTURE_DESIGN/CygnusX_project_workspace_architecture.md`，补“项目当前为刻意单所有者模型，无 project_members 表是设计决策而非缺陷”；随本次生命周期补充对应 API 与说明 |
| F | 三卡片不知服务状态，挂载即发必失败请求；错误混为一谈 | `projects.py#project_capability_status` 独立 owner-scoped 端点；`ProjectCapabilityPanel.vue` 先判能力再创建子组件；三卡片分型为服务未启用/当前用户无权限/暂无数据/请求失败 |

选择独立 `GET /projects/{id}/capability-status`，保持 overview 的会话/运行聚合职责；该端点不受科研功能开关自身拦截。只返回三个能力的 enabled/allowed/reason；有效导出能力同时考虑其读取依赖。匿名 401、非 owner 403、owner 200。它只投影状态，不改变开关或授权。

## 改动文件清单（仅本任务）

1. `alembic/versions/project_lifecycle01.py`
2. `src/cygnusx/infrastructure/database/models/project.py`
3. `src/cygnusx/application/services/project_service.py`
4. `src/cygnusx/application/services/project_overview_service.py`
5. `src/cygnusx/application/schemas/project.py`
6. `src/cygnusx/api/v1/projects.py`
7. `frontend/src/api/projects.ts`
8. `frontend/src/api/projectErrors.ts`
9. `frontend/src/components/ProjectCapabilityPanel.vue`
10. `frontend/src/views/ProjectDetailView.vue`
11. `frontend/src/components/ResearchPlanWorkbench.vue`
12. `frontend/src/components/ResearchDeliveryChain.vue`
13. `frontend/src/components/ProjectResearchDelivery.vue`
14. `tests/unit/test_project_lifecycle.py`
15. `tests/unit/test_project_delivery_stabilization.py`（旧缓存断言 None→active，撤权断言保留）
16. `tests/integration/test_project_lifecycle_http.py`
17. `frontend/src/views/__tests__/ProjectDetailResearchContext.test.ts`
18. `frontend/src/components/research/__tests__/ResearchPlanWorkbench.test.ts`
19. `frontend/src/components/research/__tests__/ResearchDeliveryChain.test.ts`
20. `frontend/src/components/__tests__/ProjectResearchDelivery.test.ts`
21. `ARCHITECTURE_DESIGN/CygnusX_project_workspace_architecture.md`（在任务开始的已有内容上局部修订）
22. `evidence/project-stage0-20261022/`：采集器、隔离验证驱动、日志、截图、交付说明及 SHA 清单。

原有无关脏文件列于 status-before.txt，未纳入本任务改动，也未提交/推送。

## 用户手测路径与已有证据

正式操作前先选择测试环境；本次未迁移生产。迁移前备份 projects 表，并核对当前 head 与本次 down_revision。新迁移必须先于新服务部署。存在 tombstone 时 downgrade 主动拒绝，防止删除决策丢失后旧代码回填复活。

| 项 | 用户可重复的手测路径 | 已有证据 |
| --- | --- | --- |
| A 删除不复活 | 登录测试账号 → POST /api/v1/projects 建项目 → 放入 runs/README.md → DELETE /projects/{id} → 连续刷新列表及 GET /projects/count → 记录不出现、物理文件仍在 | runtime-results.json：create_project、deleted_refresh_0/1/2、explicit_sync；后端持久化测试 |
| A 显式同步 | 在同账号 projects 下创建真正缺失的历史目录 → POST /projects/sync-from-disk → created=1，已删目录计入 skipped_deleted → 再同步 created=0 | runtime-results.json / explicit_sync；integration-http.log 的 tombstone 用例 |
| A 并发边界 | 并发写同一项目的 settings.parallel.first 和 settings.parallel.second → GET 项目核对两键都在 | integration-http.log：真实 PG 行锁 + 并发 HTTP 用例 |
| B 刷新回填 | PATCH settings.research_mode.enabled=true → 打开项目详情 → 开关为开 → 刷新仍为开 | browser-results.json：saved_true_is_visible、saved_true_survives_refresh；browser-research-mode-true-gates-closed.png |
| B 切项目 | 在同一个 Vue 页面实例中切到保存为 false 的项目 → 开关为关 | browser-results.json：same_view_project_switch_resets_saved_false；browser-research-mode-false-gates-closed.png |
| B 页面修改 | 在项目页点击开关 → 刷新 → GET overview 核对服务器保存值 | browser-results.json：ui_toggle_persisted_by_real_patch；browser-network.json 中 PATCH |
| C 迁移 | 在旧 schema 放入 NULL 项目 → alembic upgrade head → 查询 status 与 information_schema → 尝试写 NULL 应拒绝 | pg-old-upgrade.log、pg-lifecycle-upgrade.log、runtime-results.json；36 条为独立库中的模拟旧记录，绝非声称生产 36 条已改 |
| D 改名/描述 | PATCH {name,description} → GET 项目及 overview → 新值返回、slug 原值、runs 路径与文件不变 | runtime-results.json：两次 patch_project、overview |
| D 局部合并 | 先存 unrelated 与 research_mode.render_mode → PATCH 仅 enabled → 其他键保留；嵌套键传 null 则只删除该键 | runtime-results.json；test_project_lifecycle.py 的嵌套/数组/null 测试 |
| D 原子失败 | PATCH 同时给新 name 和非法 research_mode.enabled → 422 → GET name 未变化 | integration-http.log：真实 HTTP 原子性用例 |
| E 文档 | 对照活文档 §2.1/2.2/2.4、§9 与源码；项目状态和会话状态不可混淆 | workspace-architecture-before.md 与本次活文档局部 diff |
| F 认证/所有权 | 无 Token GET capability-status → 401；另一个用户 → 403；owner → 200，仅三项能力 | runtime-results.json：capability_anonymous/non_owner/owner |
| F 关闭降级 | 三科研开关保持 false，打开详情 → 三个说明条 → Network 无 research-plans/research-delivery/delivery-inventory 请求 | browser-results.json、browser-network.json、browser-plan-service-disabled.png、browser-delivery-service-disabled.png、browser-export-service-disabled.png |
| F 其他状态 | 在组件隔离测试中模拟 enabled=true/allowed=false、空结果、网络失败 → 分别显示无权限/暂无数据/请求失败；不为测试改现网功能开关 | frontend-targeted.log / frontend-all.log；后端能力裁剪见 test_project_lifecycle.py |

## 执行结果与限制

- 定向后端：84 passed。见 backend-targeted.log。
- 新增真实 HTTP 集成：3 passed，访问本轮独立 PostgreSQL API，无依赖替身。见 integration-http.log。
- 前端：92 个文件、628 passed；type-check 通过；生产构建输出到 /tmp/cygnusx-project-stage0-build，没有覆盖线上挂载的 frontend/dist。
- 本次业务改动的 Ruff 与五个后端源文件 mypy 定向检查通过；迁移静态校验通过、单一 head 为 project_lifecycle01。
- 真实 Chromium 开启 sandbox、以 UID 10001 运行；浏览器结果和每卡片截图保留。页面脚本错误为 0。登录初始化/导航时序的早期驱动失败保留于 attempt*，修正的是测试准备与等待，不是产品行为。
- 全量 unit：3975 passed / 9 failed / 16 skipped / 63 deselected；未以局部结果替代全量门禁。九项失败在仅还原本任务后端文件的基线中逐项重现（baseline-nine-failures.log）；基线通过 pytest pythonpath 注入源码，不向子进程额外提供 PYTHONPATH。
- 全仓 Ruff 275 项、mypy 1014 项错误，均保留完整输出；没有顺手修改无关模块。失败基线对照另见 baseline-identity.json、baseline-nine-failures.log、baseline-full-unit.log。
- 整套测试搬迁到临时目录的 full baseline 有额外路径敏感失败，不能作为等价全量基线；保留原始日志，只将当前九项的同条件定向基线用于回归归因。
- integration-http.log 还记录了测试进程退出时 OpenTelemetry exporter 对已关闭流写入的告警；不将其描述为无告警运行。
- 本轮未运行真实科研分析、生成科研导出包、调用模型或放开任何科研运行门禁。用户仍保留最终验收权。

## 复跑与收尾

`runtime_validation.py` 会新建专用 PG/Redis（仅回环端口 55434/16381），完整迁移至旧 head、准备模拟旧记录，再升级本次迁移，运行本轮 API（18002）；完成后等待私有根目录的 stop 文件。`preview.py` 在回环 18003 提供本次独立构建与 API 代理；`run_browser.py` 用本轮私有登录凭据执行真实浏览器验证。runtime-handle.json 不含凭据，仅记录私有根和进程号；凭据不复制进仓库。

收尾以 runtime-results.json 的 closure 及 closure.json 的实际进程/容器检查为准；专用数据库卷保留，不删除业务数据或既有容器。snapshot.json 是本轮开始时现有部署的只读开关快照，flags-after.json 是结束时复核。
