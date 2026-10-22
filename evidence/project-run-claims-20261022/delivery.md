# 存量转正 / Run 身份 / overview 索引 / 对账视图交付材料

本轮实现位于隔离工作树 `/tmp/cygnusx-run-claims-_vwxmf1u/worktree`，基线为已验收阶段 2 `/tmp/cygnusx-session-lineage-q2usvvh7/worktree`。没有提交、推送、部署或执行生产迁移；主工作区源码、现有部署及 `.env` 未写入。以下是可审阅的实现与实测材料，验收结论由用户决定。

[增量补丁](implementation.patch) 只含本轮 35 个文件，已对上述阶段 2 工作树执行 `git apply --check`，没有应用补丁。[补丁检查及 SHA](patch-check.json)、[文件:行号清单](changed-files.md)、[逐文件新旧 SHA](file-inventory.json)。不要把补丁直接套到缺少阶段 0/2 增量的 HEAD；它依赖已验收基线。

## A–D 实现与证据

| 范围 | 最终行为 | 主要证据 |
| --- | --- | --- |
| A 历史认领 | owner JWT 的 preview → approve → commit；用途必填；实际归档三件套、manifest 文件与 FileRegistry 的存在性/大小/SHA 复核。预审列出计划创建记录及 VERIFIED 引用，人审前没有 Dataset/Run 新建。复用 Dataset/Version/冻结 Handoff/Link，标记 HISTORICAL_CLAIMED，不生成 Task。 | [首次创建 HTTP](attempt1-http-evidence.json)、[最终源码 HTTP](final-http-evidence.json)、[原始 SQL/行](final-db-evidence.json)、[预审无写回归](backend-targeted-final.log) |
| A 幂等/审计 | 重复、改名、复制后删旧目录均复用原 Run/血缘；原 source_snapshot 保留。每次 claim/approve 请求含拒绝独立审计；接受认领还写同事务审计。认领异常 500 也记录拒绝审计。SQL 触发器保护认领审计，响应回执可定位行。 | [改名/移动 HTTP](http-evidence.json)、[复用结果](claim-replay-results.json)、[审计覆盖](claim-audit-coverage.json)、[逐请求回执](claim-audit-receipts.json)、[UPDATE/DELETE/改标/TRUNCATE 拒绝](audit-hardening-proof.json) |
| B Run 身份 | 扩展既有 platform_runs，nullable project_id FK；回填必须同时匹配 user_id/slug，无法匹配留 NULL；attempt_number=0 预留位置。阶段 2 Run/Dataset 提交收口、保留 run: 键和孤立 Task 人工冲突保持原语义。 | [回填三组实际行](migration-backfill.json)、[Run/Task 事务及会话血缘回归](backend-targeted-final.log)、[直接 Task/Run confirm 阻断](final-http-evidence.json) |
| C overview | 原 Run 表物化文件数、字节数、三件套、活动时间；统一归档出口更新，认领、删除、显式同步重算。缺失目录当前统计归零，保留原冻结来源和上次统计。overview 只读 DB 并分页，前端远程翻页。 | [逐项目隔离回填](backfill-project-results-final.json)、[删除重算](delete-invalidation-proof.json)、[同项目公平计时](overview-latency-final.json)、[浏览器分页](browser-results.json)、[GET 无扫描回归](backend-targeted-final.log) |
| D 对账 | GET 返回未认领目录、预期归档缺失、Run/Link/Task 绑定缺口及 next_action；没有自动修复或孤立 Task 纳管。 | [实际三类差异](final-reconciliation.json)、[GET 前后全部查询结果一致](final-reconciliation-readonly-proof.json) |

对账实例中有 **2 条未认领目录、2 条归档缺失、1 条绑定冲突**。普通预案没有归档定位信息时不误报缺失目录。

## 四类历史目录与负路径

| 实际夹具 | 观察到的结果 |
| --- | --- |
| 完整归档 | 人类 JWT 预审、批准、提交后得到真实 Dataset/Version/Link；后续重复返回同一 ID。原完整目录经改名、复制后删除旧目录，当前名为 `moved-historical-archive`，仍复用 Run `23d98b95-2739-4317-b0f6-24253e5ba5a0`。 |
| 缺 manifest | HTTP 422，明确 `manifest.json` 缺失，不创建血缘。 |
| 文件篡改 | 实际字节与 manifest 不同返回 409；即使临时把 manifest 改到吻合篡改字节，FileRegistry SHA 不同仍 409。批准后再改变字节，commit 再校验阻断。 |
| 已认领 | HTTP 200，reused=true，复用 Run `d98922f8-96d1-49ca-b80d-b7a84223a603` 及原血缘。 |

匿名 401、非 owner 403、编码的跨目录注入 422/404、用途缺失 422；files/tasks/reports 任一撤权时认领及对账拒绝；阶段 2 非历史 Link 不被覆盖。详见 [原场景 HTTP](http-evidence.json)、[最终场景 HTTP](final-http-evidence.json) 和 [实际 API 状态日志](api-access-status.log)。

最初四类夹具产生 2 条有效历史血缘；后续增加一条最终源码专用完整夹具，最终库为 **Dataset=3 / Version=3 / Link=3 / Task=0 / Report=0 / ExportJob=0**。这 3 条仅是历史元数据认领，未观察计算执行。原始计数与来源分别见 [认领前](db-before-claims.json)、[原场景后](db-after-claims.json)、[最终 SQL](final-db-evidence.json)。最终源码夹具 Run 为 `728f9648-604b-4acd-8c87-5b57d05f29c2`，Dataset 为 `921b102c-a69d-4651-9167-710b8e337414`。

冻结 source_snapshot 含原目录、manifest SHA、用途、actor/time 和来源引用；最终源码新增记录同时包含批准消费回执。Handoff 的 worker_paths_verified=false，实际 assay/样本科学缺口保留，dataset_ready=false。历史 Link 没有可执行 TaskSubmitRequest，inventory 为 HISTORICAL_CLAIM / HISTORICAL_REFERENCE、compute=NOT_OBSERVED。浏览器截图：[归档状态](browser-historical-run-status.png)、[历史 inventory](browser-historical-inventory.png)、[交付展示](browser-historical-delivery.png)、[远程分页](browser-indexed-pagination.png)。

## 迁移与开关

迁移没有新增表：

1. `project_run_identity01`，前驱 `project_lifecycle01`：稳定 project_id 与精确回填、Attempt 预留、归档物化列/索引、认领审计行保护。
2. `project_run_claim_audit02`，前驱 `project_run_identity01`：补足审计改标及 TRUNCATE 防护。

两项已在空专用库执行全量 upgrade → downgrade 到 project_lifecycle01 → upgrade；[升](migration-empty-all-up.log)、[降](migration-empty-all-down.log)、[重升](migration-empty-all-reup.log)。有认领审计的专用库 downgrade 如实拒绝，[保护日志](migration-retention-block.log)。这类库不能通过删除审计强行回滚。[迁移链静态检查](migration-check-final.log)、[schema drift 检查](schema-drift.log)、[实际退出码](schema-check-status.json)。**生产迁移未执行，执行时点由用户决定。**

**零新增开关**。源码 Settings、`.env.example` 和默认 YAML 相对已验收基线未变。隔离环境仅开既有 `DATASET_DISCOVERY_READONLY`（允许 JWT 元数据登记）和 `RESEARCH_DELIVERY_READ_ENABLED`；计算、下载、报告、导出写开关均 false，源码 WRITE_RUNTIME_ACCEPTED=false、冻结 worker_paths_verified=false。完整矩阵与 DB 计数见 [flags](flags.json)、[最终门禁证据](final-gate-proof.json)。没有启动计算 Worker 或提交科研计算。

## 索引回填与性能

一次性回填仅遍历已登记的专用库项目，每项目独立事务；[最终报告](backfill-project-results-final.json)：主项目 5 个目录约 34.95 ms、其他 owner 的空项目约 0.83 ms、基准项目 100 个目录约 366.43 ms，均 INDEXED，无错误。不自动创建项目或猜测所有权。超时统计返回 PARTIAL；当前实现按 stat 统计大中间文件，字节 SHA 校验仍遵守既有读取预算。

基准项目相同 PG/存储和 **100 条归档、9,899 个文件、1,335,128 字节**，两端均返回全部 100 条，逐记录文件数/字节数一致，各预热 3 次再测 25 次，无人为延时：

| overview | 中位数 | p95 |
| --- | --- | --- |
| 已验收基线递归扫描 | 102.87 ms | 108.88 ms |
| 最终源码 DB 索引 | 9.57 ms | 10.69 ms |

这是该隔离夹具的结果，不外推生产容量。完整采样在 [overview-latency-final.json](overview-latency-final.json)。浏览器确认前后页各 10 条 Run.id 不重叠，总数 100，导航没有写请求、没有 pageerror。

## 验证边界与存量红项

| 检查 | 实际结果/日志 |
| --- | --- |
| 本轮相关后端及阶段 2 回归 | **128 passed**，含未索引预审无写、冻结途中改字节回滚、缺失目录统计及原证据保留、异常 500 审计；[输出](backend-targeted-final.log) |
| 最后文件删除类型收尾回归 | **37 passed**；[输出](backend-last-change.log) |
| 全仓 unit 检查点 | **3988 passed / 7 failed / 16 skipped / 63 deselected**；随后新增 3 个回归用例包含在上面的最终 128 项中；[输出](backend-unit-full.log) |
| 同环境已验收阶段 2 全仓 unit | **3982 passed / 相同 7 failed / 16 skipped / 63 deselected**；[输出](baseline-unit-full.log) |
| Bridge | **190 passed / 2 skipped**；[输出](bridge-tests.log) |
| 最终前端全量 | **92 文件 / 631 passed**；type-check 与 build 均 exit 0；[逐命令退出码](frontend-final-status.json)、[测试](frontend_tests-final.log)、[类型](frontend_typecheck-final.log)、[构建](frontend_build-final.log) |
| 本轮 Python Ruff | exit 0；[输出](ruff-feature-final.log) |
| 无既有诊断的 15 个变更源码文件 mypy | exit 0；[输出](mypy-clean-scope-final.log) |
| 19 个变更源码文件 mypy | 25 个存量诊断，基线对应文件 28 个，无新增诊断；[当前](mypy-feature-final.log)、[基线](mypy-existing-baseline.log) |
| 全仓 Ruff / mypy | 未全绿：Ruff 最终 269，基线 271；全仓 mypy 收尾前报告 1006 个存量问题。没有顺手修复无关模块；[Ruff](ruff-full-final.log)、[mypy](mypy-full.log) |
| 实际 HTTP / PG / Redis 场景 | 最终源码 **26 项**；含实际业务状态、审计回执、拒绝、SQL 保护、GET 只读；[运行日志](final-runtime.log)、[HTTP](final-http-evidence.json)、[SQL](final-db-evidence.json) |
| 浏览器最终构建 | 远程分页、历史语义、无导航写入、无 pageerror；[结果](browser-results.json)、[运行输出](browser-run-final.log) |

[机器可读基线比较](baseline-comparison.json) 列出相同 7 个失败：skills 分类数量、并行 token 汇总、embedding provider 路由、工具包数量、Studio 审批工具集、Studio manager 参数、Redis 事件循环复用。全仓门禁因此仍红，不能称为“全绿”。没有运行依赖生产秘密的 live E2E；本轮验收场景是实际专用 API/PG/Redis 与沙箱浏览器，非只跑单测。

早期环境/证据脚本的失败输出原样保留为 `attempt*-*.log/json`：包括专用 PG 初次就绪探测、夹具名称/slug、SQL JSON 冒号参数解析、证据脚本 expire_on_commit 与 DELETE 状态期望。随后修正辅助脚本并复查持久记录；未以重复建血缘消除失败，最终仅 3 条有效历史血缘。它们不能替代最终源码日志。

隔离服务收尾见 [closure.json](closure.json)：专用 API、预览及 PG/Redis 停止，容器/数据库数据与私有 0600 凭据保留，没有销毁证据。交付文件校验和见 [artifact-sha256.json](artifact-sha256.json)。
