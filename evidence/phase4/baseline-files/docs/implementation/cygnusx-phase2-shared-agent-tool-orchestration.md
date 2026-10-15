# CygnusX BioOps Phase 2 实施报告

本轮完成允许的代码实施：共享工具目录、可信上下文、只读/prepare、人工审批卡、持久调用关联及未来提交适配器。结论为 **CONDITIONAL（隔离代码验证） / BLOCKED（运行验收与写开放）**，不是 READY。所有 Agent 下载、分析、取消操作在后端禁用；源码 `WRITE_RUNTIME_ACCEPTED=False` 与独立配置开关共同拦截，修改环境变量不能自行通过验收。未提交、推送、部署或执行真实下载/分析；未运行数据库迁移。

基线：主仓 HEAD `c68ea9e0d6ecb63cb5678444ad3dd1e2a8a00407`，分支 `feat/reproducible-report-phase0`。继承大量 Phase0/1、报告等未提交修改，本轮仅增量修改相关落点。首次状态、子仓指针及 dirty 列表见 `evidence/phase2/baseline.json`。Treasure 子仓 HEAD `88dae95e`，子仓增量改动尚未提交，父仓没有更新指针。

## PHASE2_PRECONDITION_MATRIX

| 前置事实 | 核验结论 | 证据 / 对本轮约束 |
|---|---|---|
| Phase0B Closure | BLOCKED | 读取现有 Closure；不能把 isolated service 测试当运行验收 |
| 人类确认 / owner 基线 | PASS（隔离） | JWT、参数哈希、TTL、CAS 沿用原确认服务；本轮 HTTP ASGI 负例 |
| 真实 Redis 多进程 | BLOCKED | 主机无 redis-server、套接字限制；运行测试 skipped，无内存降级放行 |
| 真实 PostgreSQL / migration | NOT TESTED | 本轮 SQLite 合约验证，迁移拓扑通过；无真实 upgrade/drift 证明 |
| 外部 MCP STDIO/HTTP/SSE | BLOCKED | in-process 4 pass，4 transport skipped；不得写成外部 E2E |
| Worker 二进制 / mounts / queue | BLOCKED | Docker socket 不可访问；EBIDownload 源码版本不代表容器实际版本 |
| Treasure 源码 / 镜像一致性 | BLOCKED | 现有默认镜像 SHA `1ea2f79` 与子仓 `88dae95e` 不一致，无镜像运行证明 |
| Phase1 可信身份 / BFF / Node runtime | PASS（隔离），运行 BLOCKED | 保留 Node/TS loop；复用 owner session，补充 project 撤权检查 |
| 双用户全栈与原生 UI 上线 | BLOCKED | 原生入口和本轮 read flags 默认关闭，未部署；DOM/ASGI 不能代替 live E2E |

## P2-A 至 P2-F 变更与证据

| 包 | 实际实施 / 代码落点 | 测试与交付结论 |
|---|---|---|
| P2-A | `application/schemas/agent_tools.py` 为单一 capability/schema；ADR、JSON schema 导出；读取前置证据 | 唯一工具名、写工具不可发现、动态 registry/bridge schema 同源通过；运行门禁 BLOCKED |
| P2-B | `agent_tool_gateway.py` 从 principal/session/project 推导 scope；`agent_tool_delegation.py` 签发短期 token；API、ToolBridge、preset 和 Node adapter 接入 | 伪造身份/项目/工具字段、撤权、token 篡改/重放、Redis 故障、无权限直调负例通过；真实 transport BLOCKED |
| P2-C | 复用 `AnalysisFlowToolService` 与 `ToolConfirmationService`；SRR/PRJNA 仅格式候选，GSE/GSM 明示需展开；共享 proposal card 和 JWT 人类 approve/reject | 参数展示、审批错误、过期及后端关闭通过；approve 不自动提交；无真实下载支持声明 |
| P2-D | `require_agent_write_gate` 保护 gateway、MCPClient、API-Key 写入口、旧 analysis submit；未来 execute 复用 DownloadService/TaskService，先持久 SUBMITTING 再提交 | 门禁无目录/Task/队列/新调用行副作用通过；测试临时解锁源码、使用 business doubles 验证一次消费、并发去重及超时；真实写验收 BLOCKED |
| P2-E | 新 `agent_tool_invocations` SQL 表 + migration；owner/session/project 查询、实际 TaskService 状态、TTL 过后摘要恢复、不明提交人工对账 | SQLite 关联恢复/跨 owner 隔离通过；真实 PG 并发和队列原子性 NOT TESTED；进度未知返回 unavailable，不伪造百分比 |
| P2-F | 聚焦/回归测试、默认关闭配置、回滚说明、G0–G14 矩阵与本报告 | 定向测试通过，但全仓存量失败和环境阻塞存在；无发布批准或 READY 结论 |

两端共享同一 gateway 和真实业务 schema，未实现新 GEO/SRA/文献引擎、Dataset、counts-only DEG 或 BioReport 新功能。Node 接收仅由可信 BFF 提供的只读工具投影，delegation token 不进入模型；回调 URL 由 operator 配置，禁止模型指定 URL、重定向和自动重试。传统 ToolTrace/SSE 卡保留，新增 `platform_tool` 事件和 `ui_payload.bioops` 卡。

下载目标由真实用户/项目生成并做 realpath containment，不创建目录；bytes/quota/runtime 支持未验证则如实未知。分析复用当前 RNA/ATAC schema 和最终 validator；gateway strict 模式要求真实 owner FASTQ 路径，拒绝矩阵输入、缺失路径和逃逸。当前检查不能证明完整 FASTQ 内容、所有样本配对、Worker 挂载和参考资源可用，写操作因此仍关。Task 原模型不扩充 project 字段，新增显式调用关联不能以路径 slug 替代授权。

确认持有完整规范化参数；SQL 审计仅保存白名单摘要和 digest。owner/project/session/operation/parameters 全部绑定；项目撤权后旧 proposal 不可继续调用。SQL 与 Redis/queue 不跨系统事务：SUBMITTING 不明状态保留并人工对账，不自动重放。不同 proposal 不宣称全局参数去重。成功只读/prepare 进入新增审计表，拒绝调用沿用入口错误/审计体系，未宣称新增表记录所有失败。

## G0–G14 验收矩阵

| Gate | 状态 | 实际证据与缺口 |
|---|---|---|
| G0 前置环境 | BLOCKED | Redis/PG/真实 Worker/外部 MCP/live E2E 未就绪 |
| G1 工具复用 | PASS（代码/隔离） | 两端 gateway、单一 schema、原 Services，无平行 engine |
| G2 用户身份 | PASS（隔离） | JWT-only approve；delegation 当前 user/token version/nonce 复核；live 未测 |
| G3 项目权限 | PASS（隔离） | owner/session/project 复核、撤权、Task 关联负例；双用户全栈未测 |
| G4 能力契约 | PASS | 严格 inputs、结果契约、scope、版本、错误；JSON schema 与 registry parity |
| G5 只读检查 | PASS（隔离） | prepare 无业务 Task/目录/队列，原 analysis 默认确认行为保留 |
| G6 人工审批 | CONDITIONAL | JWT/哈希/TTL/CAS 负例通过；真实 Redis 多进程 BLOCKED |
| G7 幂等 | CONDITIONAL | 原 proposal 单消费、隔离并发与超时验证；PG/真实 queue BLOCKED |
| G8 下载提交 | BLOCKED | 仅候选 accession 预案；真实支持/DownloadService/Worker 未验收 |
| G9 分析提交 | BLOCKED | RNA/ATAC prepare 通过；真实 Task/Worker 闭环未验收 |
| G10 异步与恢复 | CONDITIONAL | 关联查询与真实 Service 状态逻辑通过；测试 Task doubles，无真实投递 |
| G11 UI 体验 | CONDITIONAL | 两端共享卡、过期/错误、会话切换保护，DOM 4 pass；live 未测 |
| G12 安全负例 | PASS（隔离） | 身份/路径/URL/参数/审批伪造拒绝，门禁先于副作用；外部 transport 未测 |
| G13 回归质量 | BLOCKED | 聚焦通过；全仓既有失败及完整后端超时如实记录 |
| G14 发布与回滚 | CONDITIONAL | 默认关闭、独立开关和回滚设计具备；真实迁移/部署/回滚未执行 |

## 需求测试逐项映射

以下 PASS 均限定在列出的隔离测试层；不表示 runtime READY。主证据为 `tests/unit/test_agent_tools_phase2.py`，其中 39 个参数化案例、SQLite ORM + AsyncSession facade、显式 MemoryStore、Service doubles、ASGI transport。原 confirmation/MCP/Flow 回归另行执行。无真实 Redis、PostgreSQL、queue、Worker 或外部网络。

| ID | 状态 | 证据 / 限制 |
|---|---|---|
| TOOL-01 | PASS | shared_flow_catalog；dynamic_mcp_registry_bridge |
| TOOL-02 | PASS | hidden_capability_direct_call_denied |
| TOOL-03 | CONDITIONAL | 原卡保留；Node 新事件和共享 DOM 测试，旧卡全栈未测 |
| TOOL-04 | PASS | model_control_fields_rejected；strict Pydantic |
| TOOL-05 | PASS | prepare/analysis 无 business Task 副作用断言 |
| TOOL-06 | PASS | contract_unique；dynamic registry parity / 冲突拒绝 |
| AUTH-01 | PASS（ASGI） | JWT HTTP BFF 未登录/Key 负例；外部 MCP live BLOCKED |
| AUTH-02 | PASS | owner_project；task_link_status_scoped |
| AUTH-03 | PASS | 非 owner project context 拒绝 |
| AUTH-04 | PASS | model spoof inputs；ASGI header/Key 不能 approve |
| AUTH-05 | CONDITIONAL | delegation token expiry/revocation 校验；真实登出全栈未测；writes 永关 |
| AUTH-06 | CONDITIONAL | MCP 全 transport 写门禁及 Node 无写投影；真实直连 BLOCKED |
| AUTH-07 | PASS | owner_project_and_revocation_rechecked |
| APPR-01 | PASS | extra args 拒绝；write gate 无 business effect |
| APPR-02 | PASS（隔离） | expired_rejected；原 confirmation suite；真实 Redis BLOCKED |
| APPR-03 | PASS | bound_parameters_and_operation_tampering；owner/project 重查 |
| APPR-04 | PASS（ASGI） | JWT-only approval；API-Key 拒绝 |
| APPR-05 | CONDITIONAL | concurrent_isolated_execute；真实 PG 并发未测 |
| APPR-06 | CONDITIONAL | isolated_submit_dedupe_and_ambiguous_recovery；business doubles |
| APPR-07 | PASS（隔离） | Redis failure fail closed；真实 Redis 故障注入未测 |
| APPR-08 | PASS（隔离） | SUBMITTING 保留、RECONCILIATION_REQUIRED、不 replay |
| APPR-09 | PASS | source lock + all env flags true 仍拒绝；business/audit/directory 无副作用 |
| DL-01 | BLOCKED（runtime） | SRR/PRJNA format prepare 通过，但 runtime_verified 空，无 CLI 支持证明 |
| DL-02 | PASS | GSE/GSM NEEDS_METADATA_RESOLUTION |
| DL-03 | PASS | arbitrary URL/injected accession reject |
| DL-04 | PASS | symlink/owner derived target + forged path拒绝 |
| DL-05 | BLOCKED | 无真实 DownloadService/queue 提交；仅未来适配器 double |
| DL-06 | PASS（隔离） | scoped task state，progress unavailable |
| DL-07 | CONDITIONAL | 同 proposal 幂等 double；真实下载不执行 |
| DL-08 | NOT TESTED | 未创建下载 FileRecord，未新增 Dataset |
| AN-01 | PASS | real flow discover/schema parity |
| AN-02 | PASS（prepare） | RNA/ATAC real validator + temporary owner FASTQ dir |
| AN-03 | PASS | missing/escape/unknown flow/owner negative |
| AN-04 | PASS | raw matrix input rejected |
| AN-05 | BLOCKED | real isolated Task/queue 未创建，只有 double |
| AN-06 | BLOCKED | Worker mounts/最终参数运行证明缺失 |
| AN-07 | PASS（代码/隔离） | 原 TaskService final validation 复用；Phase0B isolated regression |
| UX-01 | PASS（隔离） | Discovery card inspect → panel prepare；持久 audit |
| UX-02 | PASS（隔离） | shared bridge/schema/analysis prepare；LLM live未测 |
| UX-03 | PASS | DOM normalized args/digest；server hash binding |
| UX-04 | CONDITIONAL | SQL restore/status double；真实创建和重开页面 BLOCKED |
| UX-05 | PASS（隔离） | owner/session/project + delayed old-session DOM negative |
| UX-06 | PASS（隔离） | approval fail/expiry/no retry；unknown status/reconcile |
| UX-07 | CONDITIONAL | RouterLink /tasks + backend owner check；live navigation未测 |
| UX-08 | PASS | disabled UI + server source gate |

## 实际命令、环境与结果

证据在本地 `evidence/phase2/`；日志不是部署证明。Python 使用已有 `.venv/bin/pytest`/ruff/mypy，未改变 lock；前端现有 Node 工具链，Node runtime 保留原 test runner。命令与测试替身可从测试源码复核。

| 命令 / 范围 | 结果 | 日志与边界 |
|---|---|---|
| `.venv/bin/pytest` Phase2 + confirmation + security + analysis + bridge + isolated Phase0B focused，`-m 'not quarantine' -k 'not test_upload_ref_resolution'` | 116 PASS，1 deselected | backend-focused-final.log；upload_ref 原测试先运行挂起、人工停止，未声称通过 |
| Phase2 + database + Flow validator | 55 PASS | final-contract-tests.log；包含 39 个 Phase2 案例 |
| report snapshot/Phase1/delivery/PDF/isolated integration | 78 PASS | reports-regression.log；仅验证存量，未新增报告功能 |
| integrations/agentteams/bridge pytest | 190 PASS，2 SKIPPED | bridge.log |
| 两个新增前端 DOM suites | 4 PASS | frontend-focused-final.log；proposal 3、session isolation 1 |
| 前端全 Vitest（此前观察） | 515 PASS，7 FAIL / 522 | frontend-full.log；3 个存量失败 suite，AIChat cachedOutput 与 AgentTeams，Phase1 已有同类记录；新 isolation case 后未再完整重跑 |
| vue-tsc --noEmit / build | PASS | frontend-types-final.log；build artifact 实物核对；最新构建另见 frontend-build-final.log |
| Node 全 tests，`--test-isolation=none` | 85 PASS，1 FAIL / 86 | node-full.log；validateSearchQuery startupwarning 子进程 stderr 未产生预期输出；默认 isolation 只报 file count 不算真实 86 case 证据 |
| 新 Node adapter suite / TS | 3 PASS / PASS | node-focused-final.log、node-types-final.log；fetch mocks，无实际 BFF 网络 |
| MCP runtime test | 4 PASS，4 SKIPPED | mcp-runtime.log；in-process，外部 STDIO/HTTP/SSE blocked |
| Redis runtime test | 1 SKIPPED | redis-runtime.log；BLOCKED，不能算通过 |
| check_migrations / validate-image-mapping | PASS（静态） | migrations.log、image-mapping.log；不代表镜像实际可运行 |
| focused ruff / focused mypy | PASS / PASS | ruff-focused-final.log、mypy-focused-final.log；5 个新增 backend 核心文件 |
| full ruff / mypy | FAIL：301 / 1043 errors | ruff-full-final.log、mypy-full-final.log；存量全仓问题，新增 gateway 文件无错误；未扩展本轮清理范围 |
| tests/unit + tests/e2e full not quarantine | BLOCKED / 超时 | backend-full.log，180s exit124，约12%；不得称全绿 |
| agent config 独立回归 | 9 PASS，1 FAIL | agent-config-regression.log；未修改的 shania.md 缺知识检索规则 |
| git diff --check（主仓/子仓） | PASS | 仅工作区 diff；未提交 |

聚焦后端命令（按日志实际收集文件）：

```bash
.venv/bin/pytest -q tests/unit/test_agent_tools_phase2.py \
  tests/unit/test_research_treasure_phase1.py tests/unit/test_phase0b_confirmation.py \
  tests/unit/test_phase0a_security.py tests/unit/test_mcp_dual_surface_parity.py \
  tests/unit/tools/test_analysis_flow_tool.py tests/unit/tools/test_tool_bridge.py \
  tests/unit/domain/test_flow_submission_validator.py \
  tests/integration/test_phase0b_http.py tests/integration/test_phase0b_services.py \
  -m 'not quarantine' -k 'not test_upload_ref_resolution'
cd frontend
npx vitest run src/components/research/__tests__/AgentToolProposalCard.test.ts \
  src/components/research/__tests__/TreasureSessionIsolation.test.ts
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit
node node_modules/vue-tsc/bin/vue-tsc.js -b
node node_modules/vite/bin/vite.js build
```

最终 direct build exit 0；`frontend/dist/index.html` mtime 为本轮构建时间，生成的 `TreasureMouseView-GUy1mC5C.js` 含共享禁用写卡与检索卡入口。该环境构建 stdout 为空，以进程退出码和实际产物核实，不将空日志单独视作成功。最后新增文件 Ruff 检查通过，见 `ruff-final-new.log`。

## 变更索引、发布条件与回滚

新增后端：schemas/agent_tools.py、services/agent_tool_gateway.py、services/agent_tool_delegation.py、api/v1/agent_tools.py、models/agent_tool_invocation.py、migration bioopsphase2；新增导出脚本和 Phase2 tests。修改既有 router/auth/deps/config、AgentService/ToolBridge、MCPClient/presets、AnalysisFlowToolService/FlowSubmissionValidator、Phase1 Treasure service/adapter，以同一边界复用原服务。旧 confirmation tests 仅用显式 monkeypatch 验证旧确认行为，不能作为开放写的证据。

新增前端 API、AgentToolProposalCard、AgentToolPanel、两套 DOM tests；修改 McpToolCallCard、DiscoveryProposalCard、TreasureMouseView（含会话切换时 abort/迟到响应保护）。修改 `.env.example`、compose 的默认关闭配置。Treasure 子仓新增 platform-tools.ts 和 3 cases，修改 runtime dispatch/SSE、local trusted header、callback 示例和 ARC 架构页；没有子仓提交。已有未提交 Phase1 文件上只添加本轮增量，不将其整体声称为本轮新增。

权威现状见 `ARCHITECTURE_DESIGN/CygnusX_agent_tool_gateway.md`；ADR 见 `docs/architecture/cygnusx-phase2-shared-tool-gateway-adr.md`；契约见 `docs/contracts/cygnusx-agent-capabilities-v1.md`、生成的同名 schema.json、`cygnusx-agent-task-link-v1.md`。README 已登记架构文档，runtime provenance manifest 附加 Phase2 隔离观察，保留旧 unknown。

默认配置：tool_gateway_read_enabled=false；agent_download_write_enabled=false；agent_analysis_write_enabled=false；agent_task_cancel_enabled=false；Node callback 空。仅在经过身份/模块/环境核验的隔离环境可启用 read gateway/callback 观察；写开放需要逐项真实 G0/G6–G10 验收、正确 SHA 镜像、PG migration/drift、Redis CAS、多进程并发、双用户全栈、真实最小 Task/Worker 和队列证据，随后单独代码审查源码门禁与独立开关。取消未来实现仍缺失，不可因其他工具验收而开放。

回滚先关闭 gateway/write flags 与 Node callback，保留 Task/审计事实；还原仅本轮增量，不覆盖原有 dirty 文件。数据库代码回滚保留新增表；`downgrade reportauditphase1` 会删表，必须先保全记录并确认无在途关联，不作为默认回滚步骤。迁移接既有未提交 reportauditphase1，发布包必须一起审查依赖。SUBMITTING 无法证明未投递时持续人工对账，不向模型提供解锁重试端点。

## Phase3 准入

**BLOCKED。** 当前满足 Phase2 安全只读/prepare 和隔离代码验证范围，不能据此进入 GEO processed-data Adapter、Dataset 或 counts-only DEG 实施，更不能启用 Agent 写任务。需先补齐上述真实运行门禁和相关回归，再重新作准入判断。本轮到此停止。
