# RI09.5 RC04-Core Gate Results

日期：2026-10-18（Asia/Shanghai）  
结论：**BLOCKED；不得签收 RC04-Core。**

## 当前 attempt

当前候选源尚未冻结，主仓基线为 `621bf678c58eae1e527d6dc5a105c561a4655130`，工作树包含用户的其他变更及本轮 `deploy/acceptance/ra02_runner.py` 修改。前端源码无相对该 commit 的差异；全量单测、类型检查和 build 已使用已有依赖通过，但 clean `npm ci` 因 registry DNS `EAI_AGAIN` 未完成。没有当前候选的镜像、镜像 digest 或 `RC04` Run ID。Docker daemon 身份不可访问，且没有隔离验收 env，因此本表中所有运行门禁均未在当前源上执行。

| Gate | 当前结果 | 已有证据 / 限制 |
|---|---|---|
| RC04-00 源码与环境准入 | BLOCKED | Docker `info` 权限拒绝；无 `ACCEPTANCE_APP_IMAGE` 和隔离 env；源码候选未获确认、未冻结。 |
| RC04-01 环境隔离、身份与初始 flags | BLOCKED | 不能检查实际 PG/Redis、容器身份、卷、有效 flags 或进程；不得凭历史快照推定当前状态。 |
| RC04-02 迁移与 RA02 数据库断言 | BLOCKED | D2 静态链位正确；RA02 runner 加入第 12 项正向 `attempt_count` 更新断言，尚无授权 PG 可执行。 |
| RC04-03 RA03–RA06 / FI01–FI06 | BLOCKED | 旧 Run 的 RA03 证据仅属历史；FI 运行需准确阶段注入器。计划明确 RA04/05/06 定义待核，不能推测补齐。 |
| RC04-04 报告与交付链、权限和恢复 | BLOCKED | 旧 Run 留有 HTML/PDF、M1/ZIP、JWT 与链路记录，但其源版本不同于当前；本轮未重跑。 |
| Browser E2E：34 条记录 / 3 viewport | BLOCKED | 历史授权 Run 为 31/34；当前全量 Vitest 597/597 是单元/组件测试，不是完整浏览器 E2E。 |
| Frontend install/build | PARTIAL | 全量 Vitest 597/597、`vue-tsc --noEmit`、`npm run build` 通过（现有依赖）；干净临时前端快照 `npm ci` 因 registry DNS `EAI_AGAIN` 阻断。 |
| Docker image build / digest | NOT_RUN | 未 build；没有当前候选的 image ID/digest。 |
| Security review / rollback | BLOCKED | 本轮只做 seccomp 配置结构差异审阅；没有独立安全签核。旧 Run `rollback/flags.txt` 记录 READS/WRITES/PDF=true，当前实际 flags 和容器状态未知。 |

## 本轮静态检查

| 检查 | 结果 | 适用范围 |
|---|---|---|
| D1 compose tmpfs scalar 与拒绝拆分值 | PASS_STATIC | 配置/验证器静态及离线负例；无容器运行。 |
| D2 Alembic down revision | PASS_STATIC | 源码链声明；不代表某数据库已迁移。 |
| D3 PDF renderer temp HOME/TMPDIR/cwd | PASS_STATIC | 当前文件静态检查；不代表 Worker 镜像实跑。 |
| D4 request key | PASS_ISOLATED | 当前 HEAD frontend 全量 597 tests、type-check 和 production build 通过；非 frozen candidate、非 E2E。 |
| Acceptance Ruff check / format | PASS_STATIC | `deploy/acceptance`。 |
| Acceptance config/registry checks | PASS_STATIC | `checks.py` 明确将 runtime 标为 NOT_RUN。 |
| Browser preflight syntax | PASS_STATIC | `node --check`，不是 Playwright 执行。 |
| 历史 artifact index | PASS_INTEGRITY | 68/68 路径、字节数与 SHA-256 匹配；仅证明历史文件完整性。 |
| 历史源文件哈希对照 | PARTIAL | 8/13 与当前工作副本匹配；5 项不匹配。不能将历史运行归因于当前源码。 |

## Browser Assertion Inventory

历史 `browser-results.json` 的 34 条记录由 `browser-e2e.cjs` 的 1 条启动检查及每视口 11 条检查构成。它不是“34 项均通过”的清单：每个视口的 `export_ready` 均失败；ZIP 下载被写在 ready 条件分支内，所以失败时 `zip_download` 没有记录，也没有形成固定失败断言。

| Named assertion | 1920 | 768 | 390 | 备注 |
|---|---|---|---|---|
| `browser.launch_sandboxed` | PASS | — | — | 历史 Chromium 版本见结果 JSON。 |
| `login` | PASS | PASS | PASS | 仅登录路径。 |
| `project_list` | PASS | PASS | PASS | 至少两行项目。 |
| `project_detail` | PASS | PASS | PASS | 进入项目详情。 |
| `delivery_panel_present` | PASS | PASS | PASS | 面板存在。 |
| `export_preview_available` | PASS | PASS | PASS | 可打开预览。 |
| `preview_shows_details` | PASS | PASS | PASS | 详情段落存在。 |
| `export_ready` | FAIL | FAIL | FAIL | 未观察到 ready 按钮/状态；总失败数 3。 |
| `refresh_persists` | PASS | PASS | PASS | 页面仍在项目详情。 |
| `keyboard_focus` | PASS | PASS | PASS | 有焦点元素；未验证完整键盘操作。 |
| `no_horizontal_overflow` | PASS | PASS | PASS | 历史测得 0 px。 |
| `console_clean` | PASS | PASS | PASS | 忽略了 WebSocket 错误；`pageerror` 和失败网络请求没有单独断言。 |

以下所需断言在历史结果中**未出现或未证明**：Fresh Export、Existing Ready Job、ZIP Download、下载字节与期望 SHA-256 比较、重复创建返回同一 Job/无重复发布、错误状态轮询、撤权后下载拒绝。脚本仅记录 ZIP 哈希，不拿它与 API/Job 期望摘要比较。当前浏览器 Gate=BLOCKED；目标 34/34，不能把历史 31/34 或上述静态存在性提升为通过。

## FI Definition Audit

两份权威计划没有 `FI01`–`FI06` 的编号定义或逐项预期行为，因此本报告不自行分配编号。`RI095-Final-Runtime-Acceptance.md` §RC03 明确列出下列测试维度；`RI095-Runtime-E2E-Acceptance-Plan.md` §S2 要求注入器能绑定目标 Job/阶段、确认触发时刻并可解除。源码检索未发现 acceptance 专用阶段注入器。

| 权威计划中的故障维度 | 预期需要观察的状态 | 当前状态 |
|---|---|---|
| validating 阶段失败/中断 | 目标 Job 进入契约定义的失败/可恢复状态，重试不改变冻结身份或重复发布 | BLOCKED；无精确注入器/运行证据 |
| rendering 阶段失败/中断 | HTML/PDF 与 Job 状态、保留文件及 retry 行为一致；允许的 HTML 保留行为需按契约核实 | BLOCKED；无精确注入器/运行证据 |
| publishing 阶段失败/中断 | 原子发布与 FileRegistry 记录不出现幽灵/重复对象，reconcile 可恢复 | BLOCKED；无精确注入器/运行证据 |
| 发布成功、DB 状态提交失败 | 已发布文件与 Job 状态可由 reconcile 收敛，不重复发布；明确注入点未实现 | BLOCKED；计划明确需受控注入 |
| 重复任务投递 / Beat reconcile | 同一 Job 幂等，`attempt_count` 与实际执行一致，无重复发布 | BLOCKED；没有当前 Worker 运行 |
| 撤权后的重试/下载 | 重新校验当前权限并拒绝越权读取，不泄露制品；状态码遵从 API 契约 | BLOCKED；无本轮 JWT/Worker 运行 |

不得将这些公共检查自行映射成 RA04/RA05/RA06；计划明确三 Gate 的逐项原定义仍待核。

## Security Evidence Review

完整性校验为历史 artifact index 68/68 文件路径、大小、SHA-256 匹配；该结果不代表内容脱敏。只读扫描在两份历史日志中发现 JWT 形态凭据及 `access_token`/`refresh_token` 字段：`auth/e2e-auth.log` 与 `delivery-chain/e2e-all.log`。原文件内容未改动，权限已收紧为 `0600`；脱敏副本 `evidence/rc04-core/redacted-history/e2e-auth.redacted.txt`、`evidence/rc04-core/redacted-history/e2e-all.redacted.txt` 均未检出 JWT 形态值。任何审阅/外发仅使用副本。凭据失效/处置仍待安全负责人确认，Security Gate 仍 BLOCKED。

历史运行 `ri095-authorized-20261017-attempt1` 的 31/34 浏览器结果和实际 HTML/PDF/M1/ZIP/JWT 产物可用于追溯，但不构成本次 RC04 通过。其来源提交为 `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`，不是当前 `HEAD`；详细索引见 [Evidence Index](../../evidence/rc04-core/RC04-Core-Evidence-Index.json)。

不得开始 staging / publishing / CI 发布或声称 Core accepted，直到候选源确认、隔离环境可用、必需 gate 执行通过，且回滚状态由本次运行的只读证据确认。
