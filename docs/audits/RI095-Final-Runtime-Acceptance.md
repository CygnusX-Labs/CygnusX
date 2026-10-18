# RI095 Final Runtime Acceptance

> **2026-10-18 更新**：本文件记录的前置轮次（`ri095-final-20261017-attempt1`）全部
> 环境阻断已由授权执行轮解除。本轮授权执行结果见
> [`RI095-Authorized-Runtime-Acceptance-Results.md`](./RI095-Authorized-Runtime-Acceptance-Results.md)
> （Run ID `ri095-authorized-20261017-attempt1`，证据目录
> `evidence/runtime-acceptance/ri095-authorized-20261017-attempt1/`）。
> 摘要：核心 PASS_RUNTIME 与 PASS_E2E 达成（新增真实缺陷 D3/D4 已修复并重跑验证）；
> 已有数据库升级兼容性、对象存储、历史制品不变性三项前置条件仍 BLOCKED；
> 生产门禁建议保持关闭。以下为前置轮次的原始记录，保留作为历史依据。

本轮 Run ID：`ri095-final-20261017-attempt1`。源码 commit：`d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`，分支 `feat/research-agent-phase5`，含既有未提交修改。执行时间和逐命令退出码见本轮 execution.json；镜像 digest 为 NOT_OBSERVED，不能以历史镜像身份代替。

**（前置轮次结论，已被 2026-10-18 授权执行轮更新）RI09.5 尚未达到完整 PASS_RUNTIME，也未达到 PASS_E2E。当前不具备通过 RC01/RC02 并正式进入依赖其验收结论的下一阶段的条件。** 可继续准备工作，但不能据此开放生产门禁。

## 1. 实际执行环境及准入

用户已授权在专用验收环境执行；实际操作系统/沙箱权限仍不可用。当前 UID/GID 为 1000，组为 zj/nogroup，默认 Docker context；明确探测目标为 `unix:///var/run/docker.sock`。实际探测返回 `operation not permitted`、退出码 1。本轮没有切换 daemon、Podman、提权、修改 socket 或宿主策略。

因此无法核实现存 disposable PG/Redis/私有卷、容器内用户、镜像 digest、测试身份或运行门禁；这些项目标记未观测，不能凭历史记录说不存在或可用。没有读取私有生产 env、连接生产数据库、使用生产 JWT 或凭据，也没有启动/停止任何容器。

构建环境：Node v24.11.0，npm 11.6.1。独立临时目录执行真实 npm ci；离线失败为 ENOTCACHED（zrender 5.6.1），联网尝试失败为 npm Exit handler never called，调试日志显示 registry.npmmirror.com 请求 EAI_AGAIN。不能判定已完成干净安装。

## 2. 本轮 Gate 结果

| Gate | 本轮结果 | 实际观察与证据 |
|---|---|---|
| Docker 准入 | BLOCKED | docker-access.log，真实访问拒绝 |
| 专用 PG/Redis/存储/身份确认 | BLOCKED | Docker Gate 阻断，未观测 |
| RC01 修复文件核对 | PARTIAL | source-state.patch、source-status.txt、source-hashes.json；未整体提交 |
| 空库 upgrade head/版本/约束 | BLOCKED | 未执行 SQL，不继承历史空库成功 |
| 历史数据库升级 | BLOCKED | 无批准的脱敏旧库 schema/version/data 基线 |
| 真实干净 npm ci | FAIL | 离线/联网实际退出码1；缓存和 DNS 失败 |
| 当前源码 npm run build | BLOCKED | clean install 未通过，未使用旧 dist |
| 前端部署产物一致性 | BLOCKED | 无新 dist SHA/镜像 digest/部署核验 |
| Worker HTML/PDF | BLOCKED | 无本轮 Worker、固定依赖镜像或真实制品 |
| PDF 中文/分页/解析/失败恢复 | BLOCKED | 未渲染，未生成或伪造 PDF |
| FileRecord/磁盘/JWT SHA | BLOCKED | 无本轮真实链路和下载 |
| Chromium sandbox Runner | BLOCKED | 无可访问 Runner，未放宽 sandbox |
| 三宽度业务 Browser E2E | BLOCKED | 无本轮 trace/截图/console/网络/下载 |
| M0→Report→M1→V2→ZIP→JWT | BLOCKED | 无批准的真实完成任务 corpus 与历史 M0/ZIP 基线 |

同一 Gate 的必需场景未完成，故没有任何完整运行 Gate 标 PASS_RUNTIME/PASS_E2E。历史88项证据哈希在本轮复核全部匹配，但完整性不证明其断言，也不把历史局部运行提升为本轮通过。

## 3. 修复代码与迁移验证边界

以下为此前已存在的修复，本轮只核对、留存摘要及差异，不冒称本轮新增：

- `c1d2e3f4b5a6.down_revision=h6i7j8k9l1m3`，保证 ALTER 依赖 CREATE；h6 历史 revision 本轮未修改。
- Compose 三处 tmpfs 完整标量加引号。
- control/runtime/checks 的 UID/GID、tmpfs、私有卷回读入口。
- frontend 锁文件两个 optional Sass 嵌套条目。
- audit_migrations.py 离线规划审计。

本轮新增最终报告和独立证据目录，没有新增业务功能，也没有整体提交工作树。当前工作树大量既有修改保留。静态 DAG 或升级规划不能证明数据库物理 schema；不得 stamp/reset/downgrade 或重放 CREATE/ALTER 掩盖问题。必须在批准的旧库隔离副本上保留升级前后 schema、version、数据与报告字节。

## 4. 前端真实构建

本轮在全新 `/tmp` 目录执行 npm ci，未调用工作区旧 node_modules/dist。安装失败后不执行 npm run build，因此 dist SHA 与前端 Docker digest 均为 NOT_OBSERVED。package-lock SHA 已写入 source-hashes.json。实际 Dockerfile 是 deploy/docker/Dockerfile.frontend，frontend/Dockerfile 不存在。后续必须在依赖来源可用时完整执行 npm ci、npm run build，记录产物逐文件 SHA 并与真实部署镜像比对。

## 5. PDF 运行验收

现有调用链为 BioReportAdapter→report_audit_pdf_renderer→Pandoc→Typst，指定 Droid Sans Fallback；不需要凭空添加 LaTeX/Quarto。历史 Worker 缺少 Pandoc/Typst/fontconfig 的结果只作历史参考。本轮没有可访问 Worker，未构建/补齐依赖镜像。依赖固定版本、镜像 digest、中文 PDF、解析/字体/分页检查、数据库/磁盘/JWT 下载 SHA 及 PDF 失败保留 HTML 全部待执行。HTML 成功不能代替 PDF 成功。

## 6. Browser 与 M0/M1/ZIP

历史 Chromium 为 No usable sandbox，涉及 AppArmor userns 限制；本轮无法启动 Runner，没有改变 AppArmor、user namespace、seccomp 或加入 --no-sandbox。必须提供支持正常 sandbox 的隔离 Runner及匹配 Playwright/Chromium。首页探针不能替代业务 spec。登录、项目/Claim、报告、Job更新、HTML/PDF、M1/V2、ZIP、JWT/撤权、刷新和失败重试均需1920/768/390真实执行。

批准 corpus 与旧 M0/ZIP 信任基线仍未提供，不得造科研结果。必须真实确认 M0/历史ZIP不变、M1正确引用、HTML/PDF关联及成员/下载SHA一致。历史默认 evidence ZIP未包含项目报告，不能作为 V2 链路已通过证据。

## 7. 证据、阻断与生产建议

本轮证据目录：`evidence/runtime-acceptance/ri095-final-20261017-attempt1/`。execution.json 和 frontend-online-execution.json 记录 Run ID、commit、目标环境、命令、起止时间、退出码、观察与证据路径。镜像未观测明确写 NOT_OBSERVED。本轮索引 index.json 为实际文件 SHA，不代表通过。

解除条件：批准且实际可访问的 disposable Docker；可用的受控 npm/镜像依赖来源；批准的旧库副本与完成任务 corpus；专用用户与独立JWT配置；带固定 Pandoc/Typst/中文字体的 Worker镜像；支持 Chromium sandbox 的隔离Runner；完整业务和阶段故障注入执行器。

本轮未启动服务，因此没有需要停止的本轮容器；无法读取daemon，不能声称历史容器当前均已关闭。未修改生产或验收 env，未执行 down -v、清空证据、删除历史Manifest/ZIP、drop/downgrade。生产准入建议保持关闭，完整真实Gate通过且人工验收后再评估下一阶段准入。
