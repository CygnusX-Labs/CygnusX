# 可复现报告 Phase 0 实施结果

分支：`feat/reproducible-report-phase0`，基线 `c68ea9e0d6ecb63cb5678444ad3dd1e2a8a00407`。实现跨 2026-10-12 / 2026-10-13，未提交、未推送。原有子模块 modified content 和 docs/info、既有调查报告保留。

## 实际变更

| 文件 | 作用 |
|---|---|
| src/cygnusx/application/schemas/report_snapshot.py | Task-first 身份、六状态、具名证据、冻结模型、规范 JSON 和稳定摘要 |
| src/cygnusx/application/services/report_snapshot_sources.py | SELECT-only Task/Run/FileRecord/RunEvent 适配器，owner 和显式关联校验 |
| src/cygnusx/application/services/report_snapshot_manifest.py | 有界 ARDP 读取、路径授权、清单绑定、当前 MD5/SHA-256、部分证据投影 |
| src/cygnusx/application/services/report_snapshot_builder.py | 组装 RNA 快照、来源水位、缺口、覆盖状态、冻结 |
| tests/unit/test_report_snapshot.py | 38 个合成用例，包含全部 15 类要求与异常/只读场景 |
| ARCHITECTURE_DESIGN/CygnusX_flow_architecture.md | 登记内部能力及尚未接入业务报告链路的边界 |
| docs/design/reproducible-report-phase0-design.md | 设计、来源映射、权限与投影策略、迁移提案 |
| 本文 | 实施与验收记录 |

没有改动受保护子仓、现有任务执行语义、数据库模型、前端、Agent 权限、锁文件或生产数据。产物仅被读取；测试写入的是 pytest tmp_path 合成目录。新 builder 不调用 LLM、分析执行器、队列提交或现有报告创建逻辑。

## 调用链与已核实事实

已核实 TaskService.submit → TaskModel / 现有队列执行路径，以及 RunPlanService.confirm → TaskService.submit → RunModel.task_id + confirmed_at 显式映射。TaskModel 没有通用 project_id、Run ID 或业务 attempt 字段；QueueJob 不等于 Run。ChatSession / Case 是其他限界上下文，未伪造关联。ReportModel 当前报告版本不能代替历史执行环境。

新路径为 `ReportSnapshotBuilder.build(owner_id, task_id, run_id?)` → `TaskEvidenceSource.read`（实际适配器 DatabaseTaskEvidenceSource）→ `validate_records` → `RNAResultManifestAdapter.read` → typed evidence → `freeze_snapshot`。数据库适配器 Mock 验证查询限定 owner 且只读；文件适配器真实读取合成磁盘内容。普通无 Run Task 和明确确认 Run 两个形态均在合成用例中验证。

清单缺失不走 HTML 回退；既有 FileRecord 仍能独立采集。不存在 FileRecord/清单显式绑定的文件可验证当前字节，但来源保持未知。耗时与版本声明为 estimated；有 QC 文件不产生 QC pass。新算 Hash 是当前采集指纹，执行期指纹与实际 runtime 软件版本仍为缺口。

## 验证结果

使用仓库现有 `.venv` 工具，不安装依赖或更改 lock；以下是实测结果，不表示全仓门禁全绿。

| 检查 | 结果 |
|---|---|
| 新增五个 Python 文件 Ruff | 通过 |
| 新增四个源码文件严格 mypy | 通过 |
| pytest tests/unit/test_report_snapshot.py -q | 38 通过 |
| 报告 repository/versions、路径工厂、安全 fixes/round2 | 48 通过 |
| 包含 test_report_service.py 的相关用例集合 | 新增 38 项通过后挂在既有报告创建用例，90 秒 timeout 退出 124，未完成 |
| scripts/check_migrations.py | 通过，单 head、依赖及拓扑健康 |
| bridge pytest -q | 190 通过，2 跳过 |
| frontend npx vue-tsc --noEmit | 通过 |
| 全仓 Ruff src/ tests/ | 297 个错误，涉及已有文件（如 admin/skills.py B008、cookies.py I001）；未进行无关修复 |
| 全仓 mypy src/cygnusx/ | 1033 个错误 / 231 个文件，新增源码独立检查通过 |
| frontend vitest run | 504 通过、7 失败 / 511；失败位于已有聊天流和协作室发送用例，本次没有前端修改 |
| pytest unit + e2e，not quarantine | 收集 2696 个选中用例；观察到既有 LangGraph/config 失败，随后挂在 test_agent_consultation_service.py 的 asyncio.run 关闭，已中止；没有完整套件成功结论 |
| git diff --check | 通过 |

运行环境限制：独立 `asyncio.run(asyncio.to_thread(lambda: 42))` 在 8 秒 timeout 后退出 124。线程已结束但事件循环无法被唤醒。新增测试使用本文件局部 autouse fixture 将 to_thread 改为同步执行，验证相同读取/权限/哈希实现；生产 builder 保留线程卸载。此调整不降低已有测试断言，不能证明生产线程调度或真实 DB 集成。

通过的既有相关测试为 `test_report_repository.py`、`test_report_versions.py`、`test_storage_path_factory.py`、`test_security_fixes.py`、`test_security_round2.py`。全量检查受既有失败和沙箱限制阻断，不宣称提交门禁达标。

## 真实数据与未运行项

只读连接配置探针显示 readonly_database_url 未配置，现有数据库 endpoint 的 socket 连接因 gaierror（DNS 解析失败）不可达。仅报告配置状态和异常类型，未输出 URL、凭证或宿主细节。未查询生产数据库、未扫描其他用户目录。

| 入口 | 实际数据验收 |
|---|---|
| 普通 TaskService.submit 已完成 RNA Task | 阻断，未获取实际 Task/参数/结果/清单/QC/环境 |
| FlowAgent 受控 Run 确认已完成 RNA Task | 阻断，未获取实际 Run 与 Task 关联及产物 |

tests/integration 依赖真实 DB/Redis，本环境未运行；没有手工报告 E2E、PDF、前端 build 或真实分析执行。合成 Fixture 不属于真实 E2E 证据。

## 证据缺口和 Phase 1 接入清单

基础协议与最小 RNA 适配路径满足进入 Phase 1 的代码设计条件；真实报告上线验收仍有前置条件：授权只读 DSN 可连、Task/Run 明确主键、owner 存储挂载可访问、真实 ARDP 与产物读取成功。不得借助分析重跑补足本次验收。

未解决：历史输入文件身份/执行时 Hash、工具命令与调用序列、实际镜像 digest/软件/参考版本、QC 规则版本和决策、完整步骤水位、原子跨 DB/文件冻结，以及其他存储后端、Agent/Case 接入。默认 reproducibility 为 insufficient_evidence。当前路径防护不声称抵御恶意并发目录替换；Phase 1 应采用目录 FD 和 worker 预算加固。

下一阶段具体集成位置：

1. DB：新增 snapshot/job 模型与 Alembic 迁移；关联 `infrastructure/database/models/report.py`、`task.py`、`run.py`，采用独立不可变版本，Run 可空，不按路径回填。详见设计文档迁移提案。
2. 用例与 repository：`application/services/report_service.py`、`infrastructure/database/repositories/report_repository.py`、`application/schemas/report.py`，冻结事实后再渲染，以 snapshot_id 固定事实；复用现有队列。
3. API：`api/v1/reports.py`，新增受 owner/现有报告权限约束的快照状态/版本元数据；不可开放原始日志或分享旁路。
4. BioReport：新增渲染适配器仅消费已冻结 ReportSnapshot，不回读当前 Flow/Task；渲染失败与证据状态分离。不得反向修改 FlowFrame/RNAFlow 计算语义。
5. 前端：`frontend/src/api/report.ts`、`types/report.ts`、`views/ReportsView.vue`、`components/report/ReportPreviewModal.vue`，展示版本、缺口和验证范围；沿用报告中心，不另建页面。

Phase 0 八项验收：身份、版本 schema、证据协议、RNA 适配、相关新增单测、只读边界、缺口语义、Phase 1 清单均已提供。真实 RNA 验收与全仓门禁仍有上述明确阻断，本轮不宣称可交付首个生产 E2E 报告。
