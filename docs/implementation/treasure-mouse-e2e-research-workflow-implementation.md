# 科研寻宝鼠端到端工作流增量实施

2026-10-16。任务依据：CygnusX_TreasureMouse_End_to_End_Implementation_2026-10-16.md。本轮交付原版卡片中的只读/Prepare 接线与真实记录读取；**不声明真实下载→分析→双报告 E2E 成功**。

## 里程碑与工作包

| 包 / 里程碑 | 状态及完成范围 | 未通过 / 回滚 |
|---|---|---|
| W0 / M0 | VERIFIED_CODE；工作树/子仓/开关/接口/复用矩阵见 treasure-e2e-w0-baseline.md | runtime镜像/DB UNKNOWN；无需运行回滚 |
| W1 / M1 | PASS_ISOLATED；DatasetCard 增加核验入口；公开 metadata discover 允许无项目；多Run、样本、来源摘要、缺口；同一实时/历史投影，来源主机策略与GSM/GSE链接 | live来源与完整浏览器 BLOCKED；移除新卡片按钮/optional callback，不撤回原回复组件 |
| W2 / M2 | PASS_ISOLATED；原Dialog权威文件/Run选择、raw/processed、预算、稳定requestKey；调用Gateway→DatasetImportService.prepare，原确认与DownloadService运输；无Task | Redis/Worker运行 BLOCKED；关闭动作接线，保留已保存预案和科研记录 |
| W3 / M3 | PASS_ISOLATED（既有审批回归及分析拒绝增量）；JWT-only原REST；分析新增reject复用相同hash核验与ConfirmationStore；展示批准不执行 | 真实Redis/下载/资产登记链 BLOCKED；可撤UI审批和新增reject分支，不删确认/Asset/Version |
| W4 / M4 | PASS_ISOLATED；读取真实Dataset/version/frozen Handoff、资产与校验缺口；只列服务真实兼容Flow；人工输入物种/参考/链/比较组或counts设计；Gateway→DatasetAnalysisService→AnalysisFlowToolService→统一validator | 不自动将TPM/UNKNOWN变counts，不开放counts运行认证；Worker BLOCKED；回滚分析按钮，保留预案 |
| W5 / M5（只读部分） | PASS_ISOLATED；related只恢复真实task ID/状态与持久分析/导入关联；审批与聊天取消分开 | 无真实执行，所有TaskService源码Gate保持；不自动重投；回滚任务展示不取消Task |
| W6 / M5（只读部分） | PASS_ISOLATED；research.project_delivery→既有ResearchProvenanceService与报告记录，区分scientific/reproducibility、integrity/state；无报告NOT_GENERATED | 无新报告生成或产物导出实现，下载由报告中心已有授权能力承担；真实报告 BLOCKED；回滚读取按钮，不删报告 |
| W7 / M1–M5 UI | PASS_ISOLATED；FullPresentation仍唯一展示树；原DatasetCard/原风格Dialog与typed callbacks；场景、Composer、文献、建议、桌宠/主题/双语保留；移除工作台外重复工具/JSON面板 | 实际视觉/窄屏/键盘 BLOCKED，未最终视觉验收；撤新workflow props/组件即可恢复原展示 |
| W8 / M6–M7 | BLOCKED；RG-01–RG-12逐项记录于 audits/treasure-e2e-release-gates.md | 无真实PG/Redis/Worker/Transport/浏览器/报告证据；所有真实执行仍拒绝 |

## 复用与安全边界

React只发ResearchActionV1；Vue useResearchWorkflow持有平台身份和请求；AgentToolGateway每次重建认证session/project/scopes。Node固定委托callback和平台AI的MCPClient/ToolBridge进入同一Gateway。没有新Agent/MCP server、第二套下载器、Dataset表、Task引擎或报告引擎。Node检索内核、FlowFrame/RNAFlow/Counts统计实现未改。

导入Prepare复用DatasetImportService的来源再查/选定文件/预算/request_key/确认，不叠加downloads.prepare第二审批。原始Run仅服务已支持SRR可选；其他Run仍展示映射与限制。预案不创建队列或数据文件，人工分组不由模型推断。分析只从真实版本与冻结Handoff准备，物种/对比/参考由人工输入，校验继续复用既有服务。

ToolTrace显示检索过程，平台Proposal/Task另外显示；不把LLM发言当Task。Vue只向React投影必要字段，不传normalized_request、内部目录、确认凭据；源URL采用HTTP(S)及明确主机白名单。报告链接用真实ID构造平台路由，目标仍做owner授权。文件导出不构造本地路径。

## 本轮增量文件

- 后端：agent_tool_gateway.py（公开discover项目可空，其余仍要求项目）；dataset_import_service.py（复用同一discover）；dataset_analysis_service.py（拒绝决策、恢复dataset/version/expiry）；api/v1/datasets.py（JWT reject）。无数据库迁移。
- Vue：useResearchWorkflow.ts（请求/并发/快照/恢复）；TreasureResearchWorkbench.vue（接线、项目列表与会话晚到保护）；datasets.ts（已有分析审批路由客户端）；researchPresentation.ts（可信来源主机）。
- 子仓：contract.ts / presentation-context / index（可选typed callback）；DatasetCard（按钮、编号链接）；ResearchWorkflowPanel（新增原主题Dialog）、requestKey（兼容局域网HTTP的随机UUID）；FullPresentation（挂载）；中英字典。没有重写原展示树。
- 测试：dataset_gateway_phase3全局只读/模块/开关负例；dataset_phase3_review拒绝和恢复；researchWorkflow adapter与项目乱序、完整React挂载卡片Prepare；既有协议/所有权/下载/Flow/报告回归。

## 测试命令与证据

本地日志复制到 evidence/treasure-e2e/verification；无生产凭据进入日志。

- `.venv/bin/pytest tests/unit/test_dataset_gateway_phase3.py tests/unit/test_dataset_geo_validation.py tests/unit/test_dataset_import_handoff.py tests/unit/test_dataset_phase3.py tests/unit/test_dataset_phase3_review.py tests/unit/test_agent_tools_phase2.py tests/unit/test_phase0b_confirmation.py tests/unit/test_research_delivery_phase4.py tests/unit/test_treasure_native_access.py tests/unit/domain/test_flow_submission_validator.py -q`：183 PASS_ISOLATED；SQLite、HTTP/Redis/队列双桩、真实临时文件，非Worker E2E。
- 主前端 `npx vitest run src/components/research`：41 PASS_ISOLATED（jsdom）；原展示树 `--config poc/treasure-island/vitest.config.ts`：15 PASS_ISOLATED。Poc通过子仓真实编译ES module运行。
- 全前端：554通过、7失败（新增nested Task恢复测试后未重跑全量；该新增测试计入相关域41项），仍为agent-teams-room-send/deep-thinking-stream/live-stream-render存量失败，不宣称全仓全绿。
- 子仓 `npm test`：12个文件级单元中11通过、validateSearchQuery启动告警断言失败；单独诊断为预期stderr中没有CHAT_SHARED_SECRET告警。未修改Node内核修复无关行为；platform-tools安全回调文件独立通过（mock fetch，非真实传输）。
- 改动后端4文件 Ruff/mypy通过；check_migrations通过。主Vue与子React类型、独立模块与主生产构建见最终日志。

## T01–T45 逐项记录

下列PASS全部仅隔离；没有一项代表生产或真实科研E2E。命名为上述已实际执行测试文件的简写。

| ID | 状态 | 本轮证据或限制 |
|---|---|---|
| T01 | PASS_ISOLATED | platform-entry混合GEO/文献卡含DOI/PMID/meta/链接 |
| T02 | PASS_ISOLATED | 原四场景8示例、真实Composer发问POC |
| T03 | PASS_ISOLATED | 流中核验提示展开显示未证实编号 |
| T04 | PASS_ISOLATED | 原SuggestionBlock点击追问经Vue发送新一轮，未调用业务工具 |
| T05 | PASS_ISOLATED | researchPresentation字节分割UTF8/CRLF/多行/尾帧 |
| T06 | PASS_ISOLATED | 无终态仅DONE返回false，BFF保留interrupted |
| T07 | PASS_ISOLATED | 统一投影与metadata合并/历史恢复 |
| T08 | PASS_ISOLATED | 安全主机/协议/凭据负例；GEO/DOI正确链接 |
| T09 | PASS_ISOLATED | 原桌宠/主题/国际化与ShadowRoot DOM |
| T10 | BLOCKED | Chromium启动退出，无真实16组合截图/焦点验收 |
| T11 | PASS_ISOLATED | Gateway全局无project元数据核验+POC |
| T12 | PASS_ISOLATED | 项目列表迟到与旧会话/操作响应不覆盖 |
| T13 | PASS_ISOLATED | dataset_phase3 owner/project/file/挂接负例 |
| T14 | PASS_ISOLATED | agent_tools_phase2伪造身份参数拒绝 |
| T15 | PASS_ISOLATED | 委托与目录过滤隔离测试；真实传输BLOCKED |
| T16 | PASS_ISOLATED | 受控schema/注入负例；真实callback BLOCKED |
| T17 | PASS_ISOLATED | nonce/CAS重放及故障拒绝双桩；真实Redis BLOCKED |
| T18 | PASS_ISOLATED | 共享Flow catalog、schema、ToolBridge/Gateway |
| T19 | PASS_ISOLATED | disabled capability首屏无多余请求 |
| T20 | PASS_ISOLATED | treasure_native_access真实ASGI模块拒绝 |
| T21 | PASS_ISOLATED | geo_validation多GSM/Run与源证据fixture |
| T22 | PASS_ISOLATED | no raw / no supplementary缺口 |
| T23 | PASS_ISOLATED | 官方processed候选不猜链接/类型 |
| T24 | PASS_ISOLATED | import_handoff真实SQLite Prepare无Task/目录/队列 |
| T25 | PASS_ISOLATED | import request_key复用/内容冲突+UI并发阻止；分析不声称同键幂等 |
| T26 | PASS_ISOLATED | 来源变化/参数hash不符拒绝 |
| T27 | PASS_ISOLATED | JWT-only ASGI批准及API key/自批负例 |
| T28 | PASS_ISOLATED | source Gate早于审计/队列/Task写入 |
| T29 | PASS_ISOLATED | 跨owner文件/符号链接隔离拒绝 |
| T30 | PASS_ISOLATED | 部分文件与任务双桩对账PARTIAL，非真实下载 |
| T31 | PASS_ISOLATED | 真实临时文件SHA、FileRecord、样本与冻结Handoff |
| T32 | PASS_ISOLATED | 既有归档展开/穿越/链接/资源预算负例 |
| T33 | PASS_ISOLATED | 真RNA validator+临时FASTQ Handoff Prepare无Task |
| T34 | PASS_ISOLATED | 证据raw counts/分组/真实Flow Prepare无Task |
| T35 | PASS_ISOLATED | TPM/FPKM/UNKNOWN/非法矩阵拒绝与兼容列表为空 |
| T36 | PASS_ISOLATED | 冻结版本不可改/新修订保留旧证据/源变化拒绝 |
| T37 | PASS_ISOLATED | 确认操作类型绑定及UI分开调用分析批准/拒绝 |
| T38 | PASS_ISOLATED | domain FlowSubmissionValidator与最终路径校验 |
| T39 | PASS_ISOLATED | Analysis execute源码Gate拒绝，无Task |
| T40 | PASS_ISOLATED | 既有确认竞态/隔离submit最多一次；真实PG/Redis BLOCKED |
| T41 | PASS_ISOLATED | owner/session/project Task状态恢复及UI无伪ID；真实Task运行BLOCKED |
| T42 | PASS_ISOLATED | report phase4缺manifest/报告不造结果；UI NOT_GENERATED |
| T43 | PASS_ISOLATED | counts科学交付Job失败后重试不重算 |
| T44 | PASS_ISOLATED | 既有owner报告/文件鉴权负例；真实下载BLOCKED |
| T45 | BLOCKED | 无真实来源→下载→分析→双报告ID/hash/环境证据，不宣布成功 |

## 最终能力状态（运行层）

| 状态 | 结果 | 解释 |
|---|---|---|
| DISCOVERY_READY | 否（运行未验收） | 代码/隔离通过；当前Dataset/Gateway read关闭、live来源未验收 |
| PREPARE_READY | 否（运行未验收） | 只读/Prepare UI与服务隔离通过；真实Redis/PG前置未通过 |
| APPROVAL_READY | 否 | JWT与Store隔离通过，真实Redis CAS未通过 |
| DOWNLOAD_EXECUTION_READY | 否 | RG门禁与源码写Gate关闭 |
| ANALYSIS_EXECUTION_READY | 否 | Worker路径/镜像/真实Task未验收 |
| REPORT_DELIVERY_READY | 否 | 只读记录可展示，不等于真实双报告交付 |
| VISUAL_RELEASE_READY | 否 | 浏览器启动失败，真实视觉待验收 |

## 恢复与回滚

当前脏树含大量本轮前已有成果。基线 evidence/treasure-e2e/w0；只按本轮hunk撤销：先断开Workbench workflow props，再撤DatasetCard optional action/新增Panel，最后撤公开discover/reject等最小服务hunk。移除新增文件须确认没有后续编辑，不得整文件覆盖原dirty内容。不得删除任何用户文件、FileRecord、DatasetVersion、确认、Task、Report或冻结证据。运行回滚保持写Gate关闭、只读已有证据可查；不要回退到布尔确认或内存生产审批。

本轮没有提交、推送、部署、生产迁移、真实下载、分析或报告生成。剩余P0为RG真实准入与视觉验收；剩余P1为完整样本审阅/复杂参数表单体验、原站统计连接、真实交付下载体验。它们不授权自动打开写操作。
