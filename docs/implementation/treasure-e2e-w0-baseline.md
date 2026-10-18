# W0 当前实现与准入基线

2026-10-16；VERIFIED_CODE 仅指当前脏工作树静态核对，不代表生产运行。任务依据为本目录 CygnusX_TreasureMouse_End_to_End_Implementation_2026-10-16.md。

主仓 HEAD 51011118535f782f5282f638b4a54649c79bf6d6；origin 为 github xsx123123/omichub。寻宝鼠子仓 HEAD 88dae95e7294dea5004330203f56e4211776fd74，源码存在未提交 Island 和 Node callback 增量，不能以 HEAD 声称镜像包含增量。完整 status/diff-stat/submodule 清单与拟修改文件副本在 evidence/treasure-e2e/w0。全程不 reset、stash、提交、推送、迁移或部署。

## 复用/缺口矩阵

| 分类 | 真实源码/函数 | 结论 |
|---|---|---|
| Existing | FullPresentation / TreasureOriginalDisplay / TreasureResearchWorkbench | 单一 React 展示树；Vue 持有身份会话项目 SSE；没有 iframe 回退 |
| Extend | DatasetCard / presentation-context / Island contract | 需增加安全 typed actions 与原风格审阅卡，不能向 React 传 token/服务器路径 |
| Existing | research_agent.py / ResearchTreasureService | capabilities、owner 会话、流与文献；保留原 Node 检索 |
| Existing | agent_tools.py / AgentToolGateway.context/invoke/catalog/related | 人工 UI 与 Node 委托、平台 AI 共用；逐次验证 active/session/project/module |
| Extend | AgentToolGateway._dataset_tool / DatasetImportService.discover | discover 当前强制项目；应只放宽公开元数据读取，持久 prepare 仍需项目 |
| Existing | DatasetImportService.prepare/view/decide/execute | 绑定来源/文件/预算/request_key、幂等、确认；不新建第二下载系统 |
| Existing | DatasetAnalysisService.compatible/prepare | 冻结版本、样本与类型、实际 Flow 与 AnalysisFlowToolService 校验 |
| Existing | DownloadService / TaskService / FlowSubmissionValidator | 下载/分析最终边界；不修改统计引擎与执行门禁 |
| Existing | ToolConfirmationService / CurrentJwtUserId | JWT 决策、hash/TTL/CAS/一次性消费；模型无 approve 能力 |
| Existing | research_provenance_service / ReportService / research_delivery.py | 真实 Task、FileRecord、结果与双报告读取；缺失不补造 |
| Not Needed | 新 Dataset 表/下载器/MCP Server/FlowFrame 引擎/Markdown renderer | 本轮不建立 |
| Blocked | Docker/真实 PG/Redis/Worker/MCP transport/浏览器/报告内核 | 尚无本轮 runtime 证据；RG-01–12 不可宣布通过 |

## 三条调用链

- React typed action → Vue API adapter → `/agent-tools/sessions/{session}/invoke` → Gateway → DatasetImportService / DatasetAnalysisService / AnalysisFlowToolService / TaskService。owner/project 来自认证与会话，不作为动作参数。
- Node platform-tools → 固定 `/agent-tools/delegated/invoke` → verify_delegation → 同一 Gateway；不能传自定义 URL/命令。Node source callback 已存在，运行镜像是否包含 UNKNOWN。
- 平台 AI → MCPClient/ToolBridge → 共享 Gateway → 同一服务；不建立寻宝鼠专有执行接口。

## 门禁分别记录

| 层次 | 当前事实 | 状态 |
|---|---|---|
| 源码 | agent_tool_gateway.WRITE_RUNTIME_ACCEPTED=False；Handoff worker_paths_verified=false | VERIFIED_CODE，阻止 execute |
| 本地 Settings | treasure_native_ui_enabled=true | VERIFIED_CODE，仅展示 |
| 本地 Settings | tool_gateway_read_enabled=false；dataset_discovery_readonly=false | BLOCKED，未自动改配置 |
| 本地 Settings | dataset_import_write/analysis_submit_from_dataset/counts_deg_flow_enabled=false | BLOCKED |
| 本地 Settings | research_delivery_read_enabled/research_delivery_write_enabled=false | BLOCKED |
| Compose | 主前端 context 仓根、Dockerfile.frontend；Node context 子仓，chat 镜像默认1ea2f79；旧web服务仍在compose但精确主路由由主SPA接管 | VERIFIED_CODE，实际digest UNKNOWN |
| 权限 | admin/user真实disabled_modules及project owner由DB逐次查验 | VERIFIED_CODE；未读取生产DB，不推测已授权 |
| 运行 | 当前无可信容器/Redis/PG/Worker/双报告/浏览器验收 | BLOCKED |

## 增量顺序与回滚

W1：全局只读 discover 与发现卡 typed action；W2：权威候选选择 + 既有 prepare；W4：已有 DatasetVersion/冻结 Handoff 与兼容 Flow/Prepare；W7：原组件内增强、恢复和乱序保护。W3/W5/W6 保持既有审批/执行拒绝及真实只读引用；W8 独立记录全部阻断。

W0 验收：拟修改接口已定位，写门禁未开启（VERIFIED_CODE）。无法验证运行环境不记 PASS_RUNTIME。回滚按本轮 diff hunk 或 evidence/w0 文件副本逐项恢复，不能整仓/整文件撤销历史变更；不删除用户 Dataset/Task/Report。
