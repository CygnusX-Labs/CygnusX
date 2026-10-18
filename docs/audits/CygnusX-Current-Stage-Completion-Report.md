# CygnusX 当前阶段完成度审计

审计日期：2026-10-18（Asia/Shanghai）  
审计范围：当前 OmicHub 工作区、RI09.5/RC04 与平台能力 P01–P15  
执行边界：只读取证；本报告及配套矩阵为新增审计文档，不修改业务代码或验收结论。

## 一页速览

| 项目 | 当前结论 | 证据边界 |
|---|---|---|
| 仓库现场 | `/home/zj/zj_code_libarary/OmicHub`，`main`，HEAD `d648f54d24affd2bd3787332a49a5f4c96494cef`；工作树有广泛未提交改动和子模块变化 | `git status --short` 共 22 条状态记录；RI095 运行基线是 `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`，并非当前 HEAD |
| 最近完整的 RI09.5 真实运行 | `ri095-authorized-20261017-attempt1`，2026-10-17 至 18，真实 PG14/Redis/API/Worker/浏览器 | 证据目录 `evidence/runtime-acceptance/ri095-authorized-20261017-attempt1/`，共 69 个文件；运行绑定旧 commit 和专用镜像 |
| 后续最新工作 | `iat-r3-20261018`、`g3-e2-20261018` 是工作区隔离回归、源码审计与只读主机预检 | `evidence/iat-r3-20261018/handoff.md` 明确 `PARTIAL_ISOLATED / RUNTIME_BLOCKED`；没有新 PG/Redis/Broker/Worker/产品浏览器运行 |
| RC04-Core | **PARTIAL，不能接受** | 31/34 浏览器步骤；FI01–FI06 无真实阶段注入与恢复证据；门禁关闭后的有效进程状态无现场证据；源码/镜像不对应当前 HEAD |
| RC04-Full | **BLOCKED_EXTERNAL** | 除 Core 缺口外，缺批准旧库、历史 M0/ZIP corpus、独立 S3 Bucket/凭据、存储异常可信基线、RA04–06 原始定义 |
| Production-Ready | **NOT_APPROVED** | 未完成 RC04 Full、独立安全/运维/备份恢复审查及发布审批；历史验收也明确建议保持生产门禁关闭 |
| 真实科研流程复现 | **NOT_OBSERVED / BLOCKED** | 未发现可核验的真实科研 Run ID 从数据发现、获取、RNAFlow/FlowFrame 到 BioReport/Evidence 的连续执行链 |

**目前真正完成的是什么？** RI09.5 项目交付在 `ri095-authorized-20261017-attempt1` 中完成过一轮真实隔离运行：冻结 M0、生成 HTML/PDF 项目摘要、FileRegistry 登记、M1 ExportSelectionV2、ZIP 校验和 JWT 下载；跨 owner 拒绝、单轮 M0 字节不变也有该轮证据。10 月 18 日又完成多组 IAT-R3/G3-E2 隔离回归和源码/宿主预检。以上均有清晰范围限制，不证明当前 HEAD 已复跑，也不构成真实科研计算复现。

**RC04 真实做到哪一步？** 有 RC04 前置授权轮的一部分核心运行证据，但尚无 RC04 新 Run ID。RC04-00–06 按目标验收契约没有一个可整体判为完成；Core 为 PARTIAL，Full 为 BLOCKED_EXTERNAL。

## 必答问题（12 项）

1. **当前 HEAD、工作树和最近完整 Run ID？** `main` / `d648f54d24affd2bd3787332a49a5f4c96494cef`；工作树有 22 条状态记录，包含多个源文件/证据修改、未跟踪迁移与测试，以及 FlowFrame、RNAFlow、ATACFlow、Treasure-Seeking_Mouse、tools 子模块变化。最近完整的 RI09.5 真实运行是 `ri095-authorized-20261017-attempt1`，不是当前 HEAD；10 月 18 日 IAT-R3/G3-E2 是隔离/静态范围。远端列表为空（`git remote -v` 未输出）。
2. **RC04 新实施/运行报告？** 未找到 RC04 新 Run ID。10 月 17–18 的授权运行是 RC01/02/03 范围并遗留明确缺口；RC04 文件是计划/审计工作单。当前运行结论应写“计划已制定，RC04 现场执行未证实”。
3. **D1–D4 是否固化进可复现源码？** 授权报告称 D1–D4 在当时源码/镜像修复并重跑；同一报告记录修复文件未提交、镜像基于脏工作树。当前 HEAD 比运行基线多两个提交，且当前工作树仍脏；因此只能判 `PASS_HISTORICAL`，不能判当前源码已冻结或可复现。D1/D2 的提交/镜像绑定需从原报告 source manifest 和当前源码逐项重新映射；本审计未把旧主张升级。
4. **READS/WRITES/PDF 是否真实关闭且进程有效？** 授权运行的 `rollback/flags.txt` 明确为 `ACCEPTANCE_READS=true`、`ACCEPTANCE_WRITES=true`、`ACCEPTANCE_PDF=true`；容器随后均 `Exited (0)`。这是旧验收项目关闭后的记录，不能证明当前持久化门禁关闭，也没有当前进程状态。RC04-00 不通过。
5. **31/34 是否补齐？fresh/existing-ready 三视口结果？** 未找到更新后的 34/34 具名断言、fresh 创建结果或 existing-ready 幂等路径新浏览器证据。历史记录为 31/34，在 1920/768/390 三视口分别运行既有业务链，但未覆盖严格 fresh-ready 与 existing-ready 断言。10 月 18 日矩阵也无 RI095 新浏览器执行。状态 `PASS_HISTORICAL (31/34)`，缺口未关闭。
6. **RA02 12/11 差异？** 已查清遗漏项：早期 `evidence/runtime-acceptance/ri095-20261017-attempt1/ra02/ra02-results.txt` 含 `RA02_12 legal update`，期望 `00000`；后期 `ri095-authorized-20261017-attempt1/ra02/ra02-results.txt` 只有 11 项且无合法更新断言。新 11 项全通过不覆盖该行为，未找到等效新测试证据，需补一项并重跑。
7. **FI01–FI06？** 没有真实精确阶段故障注入和恢复证据。IAT-R3 中的 SQLite/隔离故障断言（如 REC-06）属于不同门禁和层级，不能替代项目报告 validating/rendering/publishing、DB commit 窗口、重复投递/撤权的 FI01–FI06。
8. **HTML/PDF/ZIP/JWT/FileRegistry/Manifest 同版本真实证据？** 有，但只对历史授权运行源码 commit `d9c92cf…` 和其镜像 digest 成立。报告记录 HTML/PDF、数据库/磁盘/HTTP SHA、V2 ZIP、ZIP 验证、JWT 下载及跨 owner 404；没有当前 HEAD 对应的镜像或运行证据。不能把当前工作树的改动视作同一版本。
9. **seccomp 审查？** 历史报告称用户授权下从 Docker 默认 profile 派生窄范围浏览器 profile，并保持 `cap_drop ALL`；但独立、可审阅的默认与自定义 profile 差分、安全意见及当前运行镜像关联未在本次独立重核。判 `PASS_HISTORICAL / PARTIAL`，RC04-04b 未闭环。
10. **旧库、历史 M0/ZIP、S3/异常？** 未发现授权材料或新执行证据。旧库升级、跨版本 M0/ZIP 不变性、独立 S3 上传回读/撤权、漂移/丢失/symlink/配额注入均为 `BLOCKED_EXTERNAL`；本地 FileRegistry 不能替代 S3。
11. **科研寻宝鼠到 BioReport 的最长真实连续片段？** RI095 项目交付从项目 M0 → 项目摘要报告 → M1/ZIP → JWT 下载是最长的当前可定位真实运行片段；它是项目交付，不含数据集发现、真实数据下载、RNAFlow/FlowFrame 分析或独立科学 BioReport 结果。科研切片 B 的真实连续通过片段 `NOT_OBSERVED`。IAT-R3 对 Node、PG、Worker、浏览器等明确为 runtime blocked。
12. **Core/Full/生产/真实科研案例接受度？** `RC04-Core: PARTIAL`、`RC04-Full: BLOCKED_EXTERNAL`、`Production-Ready: NOT_APPROVED`、`Scientific Workflow Demonstrated: NOT_OBSERVED`。具体 Gate 见 [RC04 Gate 矩阵](RI095-RC04-Completion-Gate-Matrix.md)。

## 平台能力纵览

四维状态、路径、测试与 Run ID 的逐能力索引见 [Feature Evidence Matrix](CygnusX-Feature-Evidence-Matrix.csv)。下列是总体解释：

| 能力 | 结论 | 第一个主要断点 |
|---|---|---|
| P01 基础平台 | 有完整代码/部署配置与大量隔离测试；本轮无全栈运行 | 当前服务状态、DB/Redis/Broker/前端真实联通未观测 |
| P02 项目与证据 | 项目、Claim、Dataset、Task、Report/Export、FileRecord 等模型/API 已接入 | 当前 HEAD 的真实 PG 迁移/并发/跨 owner 全链验收未运行 |
| P03 Agent | Legacy/LangGraph/Studio/Worker 路径及工具网关有实现 | 真正生产模型、服务部署、授权写执行及恢复链无本轮证据 |
| P04 寻宝鼠 | UI/BFF/Gateway/Dataset 代码存在；隔离测试覆盖部分合同 | 实际 Node/API/PG/浏览器发现与项目历史链缺新运行证据 |
| P05 下载 | 多来源代码、审批/任务/FileRegistry 契约；隔离回归较多 | 下载运行门禁关闭；HTTP Supervisor 未接线，G3 运行不认证 |
| P06 FlowFrame | 子模块和流程资产可见；平台分析提交有适配实现 | 审批冻结/平台执行与子模块运行证据未形成当前端到端链 |
| P07 标准分析 | RNA/ATAC 等 pipeline 子模块可见，Snakemake 接入代码存在 | 当前 HEAD 的真实任务、产物与结果 manifest 未观测 |
| P08 高级分析 | Sandbox、计划/审批契约及安全隔离实现 | 没有可证明的批准后真实计算与科学结果 |
| P09 BioReport | BioReport adapter 与独立报告链路存在 | 当前真实 RNA 结果到科学报告、镜像 digest、PG/Worker 未验收 |
| P10 项目交付 | RI095 历史真实 HTML/PDF/ZIP/JWT 核心链通过 | 浏览器缺 3 步、FI、安全与外部 Gate；当前源码未复跑 |
| P11 前端 | 主应用与寻宝鼠/项目工作台代码及组件测试存在 | 当前综合浏览器工作流与新 HEAD E2E 未运行 |
| P12 数据治理 | provenance、checksum、owner 与 FileRegistry 设计/代码存在 | 独立 S3、数据保留/删除、异常隔离与真实授权尚缺证据 |
| P13 部署 | Compose、镜像构建和隔离验收工具存在 | 当前镜像构建源码绑定、运行门禁、备份恢复/监控验收未完成 |
| P14 科研复现 | 合成 benchmark 与科学输入验证逻辑有隔离测试 | 0 个审定真实案例；真实 counts/FASTQ→分析→双报告未执行 |
| P15 对外交付 | README/API/部署/许可等资产可见 | 本审计不等同发布审批；当前 release、支持状态、声明与可复现演示未作全量确认 |

## 纵向切片

| 切片 | 最后有证据节点 | 首个缺口 | 独立环境复跑 |
|---|---|---|---|
| A. RI09.5 项目交付 | 历史 RI095 run：M0 → Report HTML/PDF → FileRegistry → M1 V2 ZIP → JWT download | 34 项 UI 完整断言、FI01–06、当前源码镜像绑定、门禁关闭现场、Full 外部 Gate | 历史环境可复核；当前环境未验证 |
| B. 真实科研分析 | 未发现当前范围内真实公开/获授权科研 Run ID | 数据发现/来源验证到获取与真实 RNAFlow/FlowFrame 执行的连续链 | 无证据 |
| C. Agent 控制流程 | 10/18 有 Gateway/Prepare/策略及 SSE 隔离断言 | 人工批准接入持久写准入、真实队列/worker、运行证据登记与交付 | 无证据；IAT-G3 明确 runtime blocked |

## 限制与可信度

- RI095 授权报告的证据索引、Run ID 和摘要是历史报告对运行过程的记录；本轮没有重建容器或重跑测试。运行 evidence 共 69 个文件，与报告声明 66 件索引对象存在计数口径差异（目录包含报告/结果外围文件），不得把文件数当通过率。
- `evidence/iat-r3-20261018/manifest.sha256` 从仓库根执行时列出的文件摘要可核对；当前受跟踪变更涉及部分清单所列文件，manifest 与其原基线并不等于当前工作树快照。不要将它解释为当前全部代码的完整性证明。
- 10/18 IAT 矩阵通过项覆盖不同父/子断言；其 handoff 明确子断言不提升父级 Gate。原始汇总为 78 个父项、42 个子项、120 行；44 BLOCKED、13 NOT_TESTED、3 PASS_E2E、27 PASS_ISOLATED、33 PASS_RUNTIME。
- 本次没有访问生产数据库/对象存储、连接真实业务服务、执行迁移、启动容器或故障注入。远端 `git remote -v` 无输出；独立外部仓库仅按工作区可见子模块状态判断，未主动拉取。

详细行动见 [Next Action Backlog](CygnusX-Next-Action-Backlog.md)。本轮审计到此停止，不自行开发或开启 RC04 门禁。
