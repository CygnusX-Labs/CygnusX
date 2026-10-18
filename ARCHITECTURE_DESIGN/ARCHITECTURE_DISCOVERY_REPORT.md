# CygnusX / BioOps 单文件架构审计与批量测试计划主文件

Run ID: `arch-audit-20261018T1940+0800-e78fd1ef`　模式：A（首轮只读调查）　状态：进行中（架构取证完成，批量测试全部未执行）

---

## 1. 摘要、范围、模式与限制

- **审计对象**：OmicHub（CygnusX）当前工作树，HEAD `e78fd1ef`（main），含 4 个脏子模块与 9 个未提交文件改动。
- **范围**：brief 五部分——架构全景、三条纵向切片、架构核验、分层测试策略、批量测试计划。本轮为 A 模式：只读取证，未启动任何测试服务、未执行迁移/下载/计算。
- **主文件**：本文。evidence 根目录：`evidence/architecture-audit/arch-audit-20261018T1940+0800-e78fd1ef/`。
- **限制**：所有结论均为静态证据；未运行 PG/Redis/Worker/浏览器；历史 PASS 保留原始验证层级（PASS_HISTORICAL），不得继承为当前 PASS。测试入口中标注 `UNVERIFIED_COMMAND` 的命令未放入可执行批次。

## 2. 当前基线

| 项 | 值 |
|---|---|
| HEAD | `e78fd1efa1df3ebfcb098be973e81e193b1db224` (main) |
| 脏文件（9 个，+178/−10） | `dataset_import_service.py`（+116）、`dataset.py` 模型 +1 等；完整统计见 evidence `dirty-summary.txt` |
| 脏子模块 | `Protocol/FlowFrame`、`pipelines/ATACFlow`、`pipelines/RNAFlow`（`config/run_parameter.yaml`、3 个 envs yaml、report）、`pipelines/tools` |
| 最近 5 commit | e78fd1ef feat(mcp): research database tools；6a46e5bd fix(chat) 会话标题；d7e634b0 fix Treasure-Seeking_Mouse；621bf678 fix(frontend) randomUUID；d648f54d feat: research agent phase5 |
| 历史运行基线 | RC04 授权运行源码为 `d9c92cf6`（比 HEAD 落后 6 个 commit），镜像基于当时未提交工作树 |
| 历史审计基线 | `docs/audits/RI095-RC04-Completion-Gate-Matrix.md`（2026-10-18）审计时 HEAD 为 `d648f54d`；此后又前进 4 个 commit，**该矩阵结论需按新 HEAD 重验** |
| 单测现状 | 已知 1 个失败：`tests/unit/test_agent_config_consistency.py::test_prompt_files_declared_in_registry_have_required_sections` —— `data/ai/prompts/shania.md`（commit 0c906349 重写）缺少标准章节"知识检索与证据规则"；重写前版本存在于 git 历史与 `legacy_agents/` |

## 3. 既有架构文档清单与章节映射

权威目录 `ARCHITECTURE_DESIGN/`（README 340 行，导航 + 单页地图）。与 brief 五部分的映射：

| brief 要求 | 现有文档 | 状态 |
|---|---|---|
| 系统整体架构 | `CygnusX_platform_architecture.md`（618 行，含 maps  companion） | as-built，本审计沿用其分层事实 |
| Agent/Chat | `CygnusX_agent_architecture.md` / `agent_execution_framework.md`（六执行路径登记表） | as-built |
| 下载 | `CygnusX_download_architecture.md`（251 行，单一权威，核实日 2026-10-16） | as-built，含 S0–S7 阶段状态 |
| 寻宝鼠 | `CygnusX_treasure_mouse_architecture.md`（505 行，基线 2026-10-16 @ feat/research-agent-phase5） | as-built + 准入 BLOCKED |
| Flow/FlowFrame | `CygnusX_flow_architecture.md`（281 行）+ `Protocol/FlowFrame/` 子模块（规范 v2.0） | as-built |
| BioReport/Evidence | `CygnusX_research_delivery_architecture.md`（双报告 + ClaimEvidence v1）+ `report_architecture.md` | as-built，受功能开关保护 |
| MCP | `CygnusX_mcp_architecture.md`（876 行）+ `mcp-server/ARCHITECTURE.md` | as-built |
| 沙箱/Trusted Execution | `CygnusX_sandbox_architecture.md`；Trusted Execution 增量在下载架构 §(S3-E2) 段 | as-built |
| RC04 Gate | `docs/audits/RI095-RC04-Completion-Gate-Matrix.md` | 历史对账（基线 d648f54） |

注意：`docs/` 其余为历史档案；`*_plan`/vision/deprecated 不作现状依据。

## 4. 系统架构、部署与模块矩阵

分层（源码 `src/cygnusx/`，40+ API 路由文件、407 个测试文件）：

```
Vue3 frontend → /api/v1 (FastAPI) → middleware(Auth/RBAC/ModuleGate/Audit/RateLimit)
  → application/services (150+ 用例) → domain/* → infrastructure/*
  → PG(pgvector, 115 alembic versions) / Redis / MinIO / RocketMQ / Celery
```

部署：`deploy/docker/docker-compose.yml`（uvicorn 8000 ×2 worker、celery beat、flower 5555、redis 密码、minio 9001、rocketmq 5.3.2）；隔离验收栈 `deploy/acceptance/compose.yml` + `control.py`（fail-closed：项目名固定 `cygnusx-ri095-acceptance`、镜像强制 sha256 digest、四独立 32B hex 密钥、READS→WRITES→PDF 级联布尔门禁、浏览器 seccomp 固定路径白名单）。

| 模块 | 关键代码 | 契约 | 状态 |
|---|---|---|---|
| Chat 执行 | api/v1/chat.py, chat_service | SSE, 事件状态机 | 主干稳定 |
| Agent 运行时 | data/ai/*.yaml(19), agent_loader | execution_path 六路径 | 稳定；prompt 一致性测试当前红 |
| 下载 | download_service, tasks/download.py, download_execution.py(3 模型: Nonce/Budget/Admission) | 四阶段, FileRegistry SHA 登记 | S0–S2 落地, S3-E2 代码存在 |
| Trusted Execution | download/trusted_execution.py(380 行), supervisor_client.py(240 行) | 签名回执+nonce 单次消费 | 客户端未接 Worker 生命周期, 无 Supervisor 服务端, G3 = PARTIAL_CODE/RUNTIME_BLOCKED |
| 寻宝鼠 | research_agent 全链 + React Island | 三段分离 PREPARE/DECIDE/EXECUTE | 代码集成, 写门禁关闭 |
| 写门禁 | agent_tool_gateway.py:47 `WRITE_RUNTIME_ACCEPTED = False` | 源码级硬门禁 | 关闭（静态确认） |
| Dataset→Flow | dataset_import_service(+116 未提交), submission_validator | FlowSubmissionValidator 统一校验 | 未提交改动处于工作树 |
| BioReport | report_architecture, scientific/reproducibility 双 ReportModel | 报告失败不重跑 Task | 契约型，运行证据为历史 |
| Evidence | research_delivery: Manifest v1, ClaimProvenance v1, ResultObservation | 字节级 SHA 冻结 | 契约型 |

## 5. 逐模块事实

### 5.1 Agent / MCP
- 19 个启用 Agent（`data/CygnusX.yaml agents.enabled`），YAML 数据驱动，无基类继承。
- MCP：内置 preset 22+10+26 工具；`cygnusx_prepare/cygnusx_submit` 固定工具已双端落地；确认凭证一次性+绑 SHA-256 参数哈希，双端对等由 `test_mcp_dual_surface_parity.py` 守护。
- 最新 commit e78fd1ef 新增 research database MCP tools（本次审计范围内未见对应架构文档回写——记为文档漂移 F-06）。

### 5.2 Trusted Execution（下载执行受信观察）
静态证据：`trusted_execution.py` 实现签名回执验证（attempt/execution/epoch、policy/binary/artifact SHA、nonce）；SQL nonce repository + 唯一约束迁移；Worker direct-link 在 FileRegistry 登记前校验签名回执与输出 manifest，同事务消费 nonce。`supervisor_client.py` 强制 HTTPS+mTLS、禁代理继承/重定向、响应体 64 KiB 上限。
**缺口**：客户端 start/observe/renew/stop 未接入 Worker 生命周期；无匹配服务端；迁移未上真实 PG；隔离回归 99 项通过（PASS_ISOLATED）。

### 5.3 寻宝鼠与下载链
四阶段（发现→传输→登记→资产）+ 三 tab 共用 Task 链。身份全部从认证态派生；三段分离；Task success ≠ Dataset READY ≠ 报告交付 ≠ 可复现。

### 5.4 FlowFrame / RNAFlow
`Protocol/FlowFrame` 为 Flow 强制规范 v2.0（子模块 head 977ad657）。`pipelines/RNAFlow` head 19f5068c（feat/result-manifest 分支，已生成 ARDP result_manifest.json 对接报告中心），工作树有 run_parameter/envs 未提交修改——科学重放的输入冻结当前不成立。

### 5.5 BioReport 与 Evidence
科学 HTML/counts BioReport 与不可变 ReportSnapshot/Evidence job 分离；ProjectDeliveryManifest v1 记录实际文件字节（大小/SHA）；claim_provenance v1 区分 VERIFIED_VALUE/SUPPORTED_CLAIM/AI_INTERPRETATION/NOT_VERIFIED，自由文本恒 false。全部为受开关保护的契约实现，运行证据仅限历史 RC04 链。

## 6. 三条纵向切片与最长真实连续链

1. **交付切片（历史真实）**：登录→项目→交付面板→导出→Worker PDF→ZIP——授权运行（d9c92cf，2026-10-17）真实执行过，31/34 浏览器步、HTML/PDF 三处 SHA 一致。**当前 HEAD 未复验**。
2. **真实科研切片（从未真实贯通）**：Research Question→寻宝鼠→DatasetCard→受控下载→FlowFrame 冻结→RNAFlow→BioReport→Evidence→重放。静态链路代码齐全（research_data_service 356 行 + dataset 服务 + Flow 接入），但 RNAFlow 工作树脏、无真实运行记录。**首个断点：受控下载→FlowFrame 审批执行从未有 PASS_RUNTIME 证据**。
3. **Agent 控制切片（部分真实）**：任务→编排→专家批准→Admission/预算→Gateway→执行→证据。Gateway/审批/Admission 模型（Budget/Admission/Nonce 三表）齐备；真实端到端仅在 mcp-server 单元层验证。

**最长真实连续链** = 切片 1 历史链（版本 d9c92cf）。当前版本的最长真实链未知——需要新一轮 B03 批次重建。

## 7. 架构核验发现（Finding 登记）

| ID | 严重度 | 置信度 | 发现与证据 | 修复建议 |
|---|---|---|---|---|
| F-01 | P0 | 高 | **源码/镜像未冻结**：RC04 授权运行绑定 d9c92cf + 未提交工作树；当前 HEAD 又前进 4 commit 且工作树有 9 文件未提交改动（含 dataset_import_service +116 行）。无任何当前构建/镜像 digest 对应记录。 | 冻结当前 commit、clean worktree、重建镜像并记录 digest，方可开 B03。 |
| F-02 | P0 | 高 | **shania prompt 回归**：`data/ai/prompts/shania.md` 丢标准章节，`test_agent_config_consistency` 红。阻塞 T01/T02 全绿。 | 按历史版本补回"知识检索与证据规则"章节并经管理端 API 发布。 |
| F-03 | P0 | 高 | **验收门禁归零未证明**：RC04-00 关闭时 flags 仍 READS/WRITES/PDF=true，仅容器 Exited(0)。持久门禁状态无当前证据。 | 复用 `deploy/acceptance/control.py` 做显式归零与进程核对（B00 前置）。 |
| F-04 | P1 | 高 | **Trusted Execution 半成品**：客户端未接线、无服务端、PG 迁移未应用。G3 = PARTIAL_CODE/RUNTIME_BLOCKED。但下载 Worker 已依赖签名回执校验登记路径——若部署链路绕过校验语义需确认回退行为。 | 明确 fallback 语义测试；服务端实现前不开任何执行开关。 |
| F-05 | P1 | 中 | **RA02 缺第 12 项**：历史运行 11/11 匹配但缺 "legal update (00000)" 正向断言（对账见 docs/audits/RI095-RC04-Completion-Gate-Matrix.md）。 | 恢复 RA02_12 后重跑；工作区内未找到对应 pytest 用例（rg 无命中），需新建。 |
| F-06 | P2 | 高 | **文档漂移**：e78fd1ef 新增 research database MCP tools 无架构文档更新；download_architecture 核实日 2026-10-16 早于多个相关 commit。 | 活文档增量回写。 |
| F-07 | P2 | 中 | **RNAFlow 输入未冻结**：run_parameter.yaml + 3 envs 未提交修改，阻塞 T07/T10 科学重放。 | 冻结参数与 envs、记录 SHA。 |
| F-08 | P2 | 中 | **FI01–06 无受控注入点**：src 内 rg 未发现注入器代码（仅 events/registry 命中）。 | 设计注入点时保持生产默认不可激活（环境变量+编译期门禁）。 |

## 8. RI09.5 RC04 Gate 对账

沿用 `docs/audits/RI095-RC04-Completion-Gate-Matrix.md`（原始定义来源），叠加本审计对 HEAD 漂移的重验：

| Gate | 历史状态 | 本审计更新 |
|---|---|---|
| RC04-00 门禁归零 | BLOCKED | 维持；且 HEAD 前进后更无从证明 |
| RC04-01a/01b 冻结/确定性构建 | PASS_HISTORICAL | 维持 HISTORICAL；F-01 恶化（又 +4 commit） |
| RC04-02a 34 项 | PARTIAL 31/34 | 维持 |
| RC04-02b/02c fresh / existing-ready | NOT_OBSERVED | 维持 |
| RC04-03 FI01–06 | PARTIAL | 维持（F-08） |
| RC04-04a/04b/04c 交付/seccomp/索引 | HISTORICAL/PARTIAL | 维持 |
| RC04-05a–e 旧库/M0/S3/存储/RA04-06 定义 | BLOCKED_EXTERNAL | 维持 |
| RC04-06 分级 | M1 NOT ACCEPTED / M2 BLOCKED_EXT / M3 NOT_OBSERVED / M4 NOT_APPROVED | 维持四层结论 |

解除条件：见 docs/audits Input Request（旧库备份、M0 corpus、S3 bucket、RA04-06 原文、disposable 环境）。

## 9. 分层测试策略与测试矩阵

已核实入口（存在且可直接引用）：

- T01: `uv run ruff check src/ tests/`、`uv run mypy src/cygnusx/`、`make check-migrations`、`make validate-image-mapping`
- T02: `uv run pytest tests/unit -q -m "not quarantine"`、`cd frontend && npx vitest run`
- T03: `uv run pytest tests/unit/test_mcp_dual_surface_parity.py` 等契约单测；`scripts/test_studio_agent_runtime.py`
- T04: `uv run pytest tests/integration`（需真实 PG/Redis，CI 不跑）
- T06: `deploy/acceptance/compose.yml` + `control.py`（浏览器三视口）
- UNVERIFIED_COMMAND：任何 Playwright 直接命令、S3 fixture 脚本、FI 注入器入口——未在仓库核实，不入批次。

完整矩阵（Test ID / 层级 / 命令 / 依赖 / 断言 / 证据 / 状态）按 brief §6.2 字段落在本节；抽样关键字段：

| Test ID | 层级 | 命令(cwd=repo) | 前置 | 状态 |
|---|---|---|---|---|
| T01-01 | Static | ruff+mypy | 干净依赖 | READY（当前有已知红：F-02 属 T02） |
| T02-01 | Unit | pytest tests/unit -m "not quarantine" | — | READY，预期先红（F-02） |
| T03-RA02 | Contract | 新建 RA02 12 断言用例 | disposable PG | PLANNED（F-05） |
| T04-01 | Integration | pytest tests/integration | PG14+Redis 实例 | PLANNED |
| T06-B34 | Browser | control.py 驱动 compose 栈 | 镜像 digest ×5 + 密钥 | PLANNED，需授权 |
| T07-SCI | Scientific | RNAFlow 小切片 | 冻结输入（F-07） | BLOCKED |
| T08-FI | Fault | 依 F-08 注入点 | 隔离栈 | PLANNED，待注入器 |
| T09-PROV | Provenance | artifact-index 逐项 SHA 对账 | 历史 evidence | READY（只读） |
| T10-REP | Repro | 干净环境重放 | 冻结源码/镜像 | BLOCKED（F-01） |

## 10. 批量执行顺序（B00–B06）

按 brief §7.2。当前仅 B00/T09 只读项可在 A 模式继续；B01 起需 B/C 授权：

- **B00 基线预检**（部分已做）：源码身份已存 evidence；剩余——`make check-migrations`、门禁归零核对（F-03）、镜像现状。
- **B01 快速隔离**：T01–T03。准入条件：F-02 修复授权。
- **B02 集成**：T04 + RA02。准入：disposable PG/Redis 凭据与端口。
- **B03 RC04 正常链**：需冻结 commit + 5 镜像构建（网络/磁盘授权）。
- **B04 异常与证据**：FI01–06（待注入器）+ T09。
- **B05 真实 RNA-seq**：F-07 解决 + 科学执行授权。
- **B06 收尾**：门禁恢复 + 清理核验。

停止条件、并发与重试规则照 brief §7.3；本轮未获授权的批次一律停留计划状态。

## 11. 实际运行结果与 evidence 索引

本 Run ID 下**无任何测试执行**。已存只读取证：

| 文件 | 内容 | 脱敏 |
|---|---|---|
| `source-head.txt` | HEAD SHA | 无敏感 |
| `dirty-summary.txt` | git diff --stat 尾部 | 无敏感 |

历史 evidence（只读引用，未改动）：`evidence/runtime-acceptance/ri095-authorized-20261017-attempt1/`（66 项 artifact-index）、`ri095-20261017-attempt1/`、`evidence/iat-r3-runtime/`。T09-PROV 对这些索引的逐项核验尚未执行。

## 12. 外部阻断项与下一轮优先级

| 阻断 | 影响 | 解除条件 |
|---|---|---|
| 源码/镜像未冻结（F-01） | 所有 T05+ 批次 | 用户确认冻结 commit + 授权 clean 构建 |
|  disposable PG/Redis 未准备 | T04/RA02 | 提供端口/凭据或授权本机 docker |
| RA04–06 原始 Gate 定义缺失 | RC04-05e | 负责人提供原文 |
| 旧库/S3/M0 corpus | RC04-05a–d | 脱敏备份与专用 bucket 授权 |
| RNAFlow 输入未冻结（F-07） | T07/T10 | 冻结并提交参数/envs |

**优先级**：P0 = F-02 修复授权 + F-01 冻结决策；P1 = B01/B02 授权执行；P2 = Full 外部条件（单独管理，不阻塞 Core）。

## 13. 更新记录

| 日期 | Run ID | 基线 | 变化 |
|---|---|---|---|
| 2026-10-18 | arch-audit-20261018T1940+0800-e78fd1ef | e78fd1ef (dirty, 4 submodule drift) | 初版：架构取证 + 测试计划 + 批次定义；零测试执行 |

