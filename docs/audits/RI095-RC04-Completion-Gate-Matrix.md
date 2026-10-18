# RI095 RC04 完成度 Gate 矩阵

审计日期：2026-10-18。状态按 RC04 验收契约核验；历史 `PASS_RUNTIME/PASS_E2E` 保留原名，不等同于当前源码的 `PASS_CURRENT`。未发现 RC04 新 Run ID。

## Gate 判定

| Gate | 当前状态 | 已有证据 | 缺口与判定 |
|---|---|---|---|
| RC04-00 验收门禁归零 | **BLOCKED / 未证明** | `ri095-authorized-20261017-attempt1/rollback/flags.txt`；`containers-after-stop.txt` | 关闭记录为 `ACCEPTANCE_READS/WRITES/PDF=true`，容器 `Exited (0)`。停止容器与关闭持久门禁不同；无当前有效进程状态。 |
| RC04-01a D1–D4 修复固化 | **PASS_HISTORICAL / 当前未冻结** | `docs/audits/RI095-Authorized-Runtime-Acceptance-Results.md` §1、§10；相应回归日志 | 报告称 D1–D4 修复后重跑成功，但修复随未提交工作树；运行源码 commit `d9c92cf…`，当前 HEAD `d648f54…`，工作树仍有广泛变更。 |
| RC04-01b 确定性构建 | **PASS_HISTORICAL / 当前不匹配** | 该报告 §4、`frontend-build/dist-sha256.txt`、`image-digests.txt` | 当时真实 `npm ci`/build 和 digest 有记录，但源码工作树脏、lock/digest 绑定旧运行；当前 HEAD 没有 clean source/build/image/digest 对应记录。 |
| RC04-02a 34 项断言对账 | **PARTIAL (31/34)** | 授权报告 §7；浏览器日志/截图目录 | 未找到 34 条具名旧新映射或新 34/34 结果。三视口历史链覆盖登录、项目详情、预览、刷新、键盘和溢出；不得升格完整通过。 |
| RC04-02b fresh export | **NOT_OBSERVED** | 历史 browser 日志 | 没有从 fresh 状态由真实 UI 创建、等待 ready 并校验 ZIP SHA 的新证据。API 创建/ready 不等价。 |
| RC04-02c existing-ready | **PARTIAL / NOT_OBSERVED** | 历史报告说明幂等创建可直接返回 ready job，但 spec 的 `p[role=status]` 轮询与按钮有竞态 | 没有独立断言证明按钮可用、可下载、不重复发布；不能以预先 API 种 ready 冒充 fresh 测试。 |
| RC04-03 FI01–FI06 | **PARTIAL，六项未获真实证明** | `RI095-Authorized-Runtime-Acceptance-Results.md` §5、§11 明确阶段故障注入尚未实现 | 无 validating/rendering/publishing、发布后 DB commit 前、重复投递、撤权的精确失败及恢复证据。隔离 SQLite 其他故障测试不替代本 Gate。 |
| RC04-04a 文件、权限与交付证据 | **PASS_HISTORICAL（限定范围）** | `chain/` 与 `auth/`：HTML/PDF SHA、V2 ZIP、验证器、JWT、跨 owner 404 | 真实历史运行覆盖本地存储和单轮 M0 不变；当前 HEAD 无复跑，也没有历史多轮不变性。Manifest/证据索引须逐文件核验并绑定运行版本。 |
| RC04-04b seccomp 审查 | **PARTIAL / PASS_HISTORICAL** | 授权报告 §9；`deploy/acceptance/seccomp-browser.json`、`docker-seccomp-default.json` | 有授权记录、窄范围 profile 主张、`cap_drop ALL` 和 sandbox 运行记录；本审计未复核完整 syscall 差分、容器作用域、剩余能力及独立风险意见，也未绑定当前镜像。 |
| RC04-04c 证据索引 | **PARTIAL** | `artifact-index.json`；证据目录与 SHA 文件 | 有索引不自动证明断言语义。须逐项核对 SHA/大小/Run ID、脱敏和对应原始断言；本审计没有复核全部 66 件索引项。目录文件数 69 还包含索引口径以外的报告/外围文件。 |
| RC04-05a 旧库升级 | **BLOCKED_EXTERNAL** | 授权报告 §5、§11 | 缺批准脱敏旧库 schema、Alembic version、数据与制品基线；fresh DB migration 不能替代升级兼容。 |
| RC04-05b 历史 M0/ZIP 不变性 | **BLOCKED_EXTERNAL** | 授权报告 §5、§11 | 只有本轮单次 M0 前后字节不变；缺冻结 corpus 和多轮跨版本对比。 |
| RC04-05c S3 | **BLOCKED_EXTERNAL** | 授权报告 §5、§11 | 无授权独立 Bucket/前缀/凭据和真实上传、回读、撤权证据。 |
| RC04-05d 存储异常 | **BLOCKED_EXTERNAL / NOT_TESTED** | 授权报告 §5、§11 | 缺可信基线与漂移、丢失、symlink、配额隔离 fixture 的真实执行结果。 |
| RC04-05e RA04–06 原始定义 | **BLOCKED / 未能映射** | 授权报告 §11 表示需原始 Gate 定义 | 不根据缩写自行编造；提供原文后逐项映射已有 Worker/Beat/派发证据。 |
| RC04-06 分级验收 | **PARTIAL** | 本矩阵与历史验收结果 | `RC04-Core` 未达到；`RC04-Full` 外部阻断；生产及科学复现为独立 Gate。 |

## 必答专项

### D1–D4 与冻结

授权运行报告称 D1–D4 在当时源码/镜像修复和重跑通过；D3（PDF `cwd=temp`/`TMPDIR`）、D4（空 `request_key` 兜底）在报告中被描述为本轮新增修复。D2 迁移顺序、D1 tmpfs 标量也有历史源码依据。报告同时明确相关修复未提交，镜像 digest 基于未提交工作树。当前 HEAD 已到 `d648f54`，工作区有不同于运行基线的提交和本地变更，故当前源码、当前镜像之间没有可审计的一致性证明。

### RA02 12/11 对账

旧运行目录 `evidence/runtime-acceptance/ri095-20261017-attempt1/ra02/ra02-results.txt` 报告 12 assertions，具体包含 `RA02_12 legal update (expect 00000)`。授权运行目录 `evidence/runtime-acceptance/ri095-authorized-20261017-attempt1/ra02/ra02-results.txt` 共 11 条，编号 1–11，其中 `RA02_11 dup source (expect 23505)` 是最后一项，没有 `RA02_12 legal update`。新报告的 11 项期望/实际 SQLSTATE 全匹配，但没有第 12 项的等效结果；差异是**遗漏合法更新断言**，不是已证明合并或已证明等价。下一次 RA02 应恢复该正向用例，并保留清晰稳定的断言 ID。

### Browser 31/34、fresh 与 existing-ready

历史浏览器运行在 1920、768、390 三宽度有三组证据；报告结论 31/34，未命中的 spec 是 `export_ready` 按钮等待。报告推测既有 ready job 的幂等返回与状态轮询有时序竞态，称 API driver 证明后端 ready，但这不足以满足 UI 断言。审计未找到新鲜状态 UI 创建/ready/ZIP SHA 的 fresh 场景，也未找到复用 existing-ready Job 后按钮与下载可用、零重复发布的独立场景结果。三种模式均不能记为 34/34。

### FI01–FI06

没有真实注入运行记录，当前不能将测试 hook、SQLite 异常、worker 普通失败或随机 kill 作为通过。RC04 需要每个 FI 对应明确注入点、真实阶段、持久状态预期、重试/对账恢复、原始日志与产物/DB 证据，并证明生产默认无法激活注入器。授权报告确认阶段级注入仍属 PARTIAL。

### 门禁、交付与安全

- 关闭后 flags 文件记录 `READS=true`、`WRITES=true`、`PDF=true`；所有验收容器停止。不能声称持久门禁已归零或当前运行进程处于安全状态。
- 历史交付链 HTML `6635 B`、PDF `44369 B`/3 页、DB/磁盘/HTTP SHA、V2 ZIP 与 SHA、ZIP 自带验证器和 JWT 下载有真实运行证据。来源是历史运行源码 commit `d9c92cf…` 与历史镜像 digest，不是当前 HEAD。
- seccomp 有显式用户授权及 profile/运行证据，但仍需独立差分和风险审查；本地审计没有重放解析 profile 或模拟 Chromium syscall 集合。
- 历史证据覆盖 66 项索引声明；需要按索引逐一检查 hash、大小、run/source 绑定、脱敏和结论语义，不能以 `sha256sum` 成功代替原始事实审查。

## 分级结论

| 层级 | 判定 | 理由 |
|---|---|---|
| M1 `RC04-Core Accepted` | **PARTIAL / NOT ACCEPTED** | 门禁关闭现场缺失；源码/镜像未冻结到当前 HEAD；浏览器只有 31/34；FI01–06 缺真实注入/恢复；证据和 seccomp 独立复核未完成。 |
| M2 `RC04-Full Accepted` | **BLOCKED_EXTERNAL** | M1 未完成；批准旧库、历史 M0/ZIP、S3、存储异常基线和 Gate 原文仍缺。 |
| M3 `Reproducible Scientific Workflow Demonstrated` | **NOT_OBSERVED** | 未发现真实数据到 RNAFlow/FlowFrame/科学 BioReport 的完整执行、Manifest 与独立重放。 |
| M4 `Production-Ready` | **NOT_APPROVED** | 不得由 M1/M2 或项目摘要 PDF 推导；独立生产安全、备份恢复、监控/告警、数据治理和发布审批未证明。 |

## Input Request

继续推进 Full/Core 验收前需负责人提供或批准：脱敏旧库备份及制品指纹；冻结历史 M0/ZIP corpus；独立测试 S3 Bucket/前缀与专用凭据；存储异常用可信 fixture；RA04–06 原始验收定义；可运行 disposable PG/Redis/Broker/Worker/浏览器环境与清理责任；认可的当前源码冻结 commit 和镜像构建条件。生产凭据无需提供，也不应用于验收。
