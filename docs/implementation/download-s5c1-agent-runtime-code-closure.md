# S5-C1 Shared Agent Runtime Code Closure

日期：2026-10-17。S5-C1 = **PASS_ISOLATED**，限本文列出的代码与隔离验证范围；静态检查存量错误及 upload 引用测试超时保留。S5-C 不因此成为 PASS_RUNTIME，DOWNLOAD_EXECUTION_READY 仍为 FALSE。

## 1. 当前代码基线

HEAD：`51011118535f782f5282f638b4a54649c79bf6d6`。共享工作树有大量既有改动；基线清单见 `evidence/download-s5c1/status-before.txt`。本轮未提交、推送、部署、迁移、清理工作区或执行真实下载。架构依据为[下载架构](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)、[Gateway 架构](../../ARCHITECTURE_DESIGN/CygnusX_agent_tool_gateway.md)和[执行框架](../../ARCHITECTURE_DESIGN/CygnusX_agent_execution_framework.md)。

## 2. 原 9 项失败逐项归因

已读取原 `evidence/download-s5c/isolated-regression.txt`，并重新运行整个 `tests/unit/test_langgraph_runtime.py`：9 failed、14 passed，见 `reproduce.txt`。以下名称均省略公共前缀 `test_`。

| 用例 | 根因分类与调用位置 | 修复 |
|---|---|---|
| tool_executor_mas_plan_preview_returns_adapter_envelope | A：过时 fixture；进入 Runtime 前失败 | 正式 ChatService 构造 |
| tool_executor_parallel_subagents_rejects_when_case_bound | A：同上 | 同上 |
| tool_executor_parallel_subagents_per_round_guard | A：同上 | 同上 |
| tool_executor_parallel_subagents_emits_started_and_aggregated | A：同上 | 同上 |
| tool_executor_skill_route_emits_started_and_aggregated | A：同上 | 同上 |
| tool_executor_create_agentteams_case_confirmed_run | A：同上 | 同上 |
| tool_executor_create_agentteams_case_records_confirmation | A：同上 | 同上 |
| tool_executor_goal_terminal_tools_delegate_to_service | A：同上 | 同上 |
| persisted_envelope_matches_legacy_fields | A：同上，经持久化信封测试入口 | 同上 |

共同栈为测试 helper → `_stream_agent_chat_langgraph` → 动态模型路由分支 `self._service._db.execute`（复现时第 316 行）。测试使用没有 `_db` 的 SimpleNamespace，且继承了本机动态路由配置。正式 `ChatService(db)` 在构造器注入 `_db`，本次未发现该依赖缺失的生产初始化缺陷；也没有在 Gateway 或业务工具阶段触发这 9 个失败。

修复 helper 使用正式 ChatService 和 AsyncSession mock；历史消息读取显式使用 AsyncMock 空列表，避免协程未等待警告。该模块测试固定静态模型选择，防止无关的本机路由配置影响工具执行测试；不修改生产路由配置，不取消断言或 quarantine。最终集合中原文件 23 项全部通过。

## 3. ToolBridge 上下文派生

通用 Runtime 上下文来自可信 user/session/db，但没有 Gateway scopes。Bridge 在缺少 scopes 时调用原 Gateway.context，要求 platform_ai，再由 invoke 重新读取当前用户、会话、项目及模块权限。已有 scoped context 不重新授予全部权限，继续由原 invoke 做 scope 交集。

新增检查：通用上下文若携带 project_id 或 agent_kind，其值必须与服务端派生值一致。模型额外参数仍由原业务 Schema 拒绝；不引入身份系统，不消费模型提供的 owner/project/scopes。12 个新增 Bridge 场景包括正常派生、有限 scope、错用户/项目、撤权、缺失/归档会话、模块禁用、类型不符、历史恢复、项目改变，以及派生后调用前模块撤权。后者观察两次 context 获取并确认拒绝。

## 4. 实际修改范围

- `tool_bridge_service.py`：可信派生后的绑定一致性检查；目录 LLM 投影优先排列 runtime_status、write_enabled 和 available_tools，保留完整 UI 结果。原 Legacy 4000 字符护栏曾截掉末尾状态字段；没有增大通用截断上限或伪造能力状态。
- `infrastructure/mcp/client.py`：builtin BioOps 工具保留 Bridge success/is_error；业务拒绝直接返回，不进入重试或替代执行器路径。修复拒绝结果被包装成 success=true 的实际问题。其他 builtin 和外部 MCP 语义保持原分支。
- `test_langgraph_runtime.py`：正式构造 fixture、静态模型选择与历史消息 mock。
- `test_download_s5b_consumption.py`：新增权限矩阵、撤权窗口及双 Runtime 完整轮次。复用原隔离 DB/业务 fixture。
- 本报告及 Gateway 活动文档的接续说明。此前罗盘文件是独立文档交付。

Bridge 还包含其他阶段的既有修改，不能将 HEAD diff 整体归入本轮；格式整理不改变其业务行为。

## 5. Legacy 完整工具轮次

真实 AgentService.assemble_context 装配 research tool pack；确定性 Provider 首轮输出目录 tool call，真实 ChatService Legacy 分派到 MCPClient → builtin Bridge → Gateway → describe_download_capabilities；第二轮检查回灌文本中的服务端 BLOCKED/write_enabled，输出文本并结束。非法 owner_id 分支由 Schema 拒绝，回灌包含失败状态，tool_result.success=false，最终完成错误解释。每例 Gateway.invoke 恰好一次、模型恰好两轮、一个 tool_result、最终 done，无下载调用。

## 6. LangGraph 完整工具轮次

使用同一装配、模型输入和业务链，ChatService 选择真实 LangGraph Runtime/图分派；成功和非法参数拒绝各一例，断言与 Legacy 相同。完整轮次共 4 项。没有用直接 Gateway 调用代替这 4 项验收。

隔离边界：SQLite facade、确定性模型、Agent/Provider 选择与外围计费/消息持久化替身。AgentService 的 Schema 装配、两个 Runtime 工具分派、MCPClient、Bridge、Gateway 和目录业务投影是真代码；不是 HTTP SSE 网络、真实模型、PG 或部署验收。SSE 验证限 ChatChunk 事件终态，未认证浏览器网络流。

## 7. 共享 Schema 与权限

原 S5-A/B、Gateway、Import/Handoff 回归验证同一 CAPABILITY_MODELS、工具名和 Gateway；双 Agent 允许不同 scope。覆盖 downloads.describe_capabilities、dataset.discover、dataset.list_project_assets、dataset.inspect/list_files、tasks.get_status、downloads.prepare、dataset.prepare_import。资产沿原 Dataset/FileRecord 查询，Task 要求归属和会话/项目关联；Prepare 沿原一次确认，未创建实际下载 Task。目录状态继续由服务端配置投影，不将配置开启当作运行认证。

## 8. 自动化结果与日志

日志根目录：`evidence/download-s5c1/`。数字不跨轮累加。

| 日志 | 本次实际结果 |
|---|---|
| reproduce.txt | 9 failed / 14 passed，原失败复现 |
| langgraph-fixed.txt | 23 passed；初版 fixture 的协程警告随后修正 |
| bridge-tests.txt | 21 passed，早期权限矩阵 |
| full-rounds-first 至 fifth | 保留迭代失败与最终当轮 4 passed；暴露文本截断与错误状态包装问题 |
| regression.txt | 合并运行停在 upload 引用，人工终止，exit 130；不是通过结果 |
| regression-split.txt | 213 passed / 7 skipped；真实沙箱 E2E 跳过 |
| final-regression.txt / final-rounds.txt | 测试 Provider 导入整理错误，保留失败；已修正 |
| verified-regression.txt | **214 passed / 2 warnings，8.58s，exit 0** |
| mcp-bridge.txt | **32 passed / 2 deselected / 1 warning，exit 0** |
| workspace-ref.txt | 单独 workspace 引用用例通过 |
| upload-ref.txt | 单独 upload 引用 15s 超时，exit 124，未解决 |
| ruff-final.txt | 四个修改 Python 文件聚焦 Ruff 通过 |
| mypy-verified.txt | 52 errors / 3 files，exit 1，详见下节 |

最终主命令使用 `LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib .venv/bin/pytest`，文件集合为 test_langgraph_runtime、chat/test_langgraph_chat_runtime、chat/test_langgraph_context_view、chat/test_runtime_golden_baselines、chat/test_golden_records、test_download_s5a_catalog、test_download_s5b_consumption、test_agent_tools_phase2、test_dataset_gateway_phase3、test_dataset_import_handoff、test_download_transport_contract、test_download_worker_protocol_gate、test_download_registration_contract，均位于 tests/unit，参数 `-q -m "not quarantine"`。

补充命令：同环境下 `timeout 45 .venv/bin/pytest tests/unit/mcp/test_reliability.py tests/unit/mcp/test_client_session_pool.py tests/unit/tools/test_tool_bridge.py -q -m "not quarantine" -k "not upload_ref_resolution and not workspace_file_ref_resolution"`；两个被排除文件引用用例另行用 `timeout 15`、`-vv -k <用例关键词>` 检查，结果如表。未修改旧用例来使其跳过。

warning 为存量 Pydantic Config 弃用和原短 JWT 测试 key。部分独立运行结束后出现 OTel/Loguru closed-stream 导出错误，保留原日志，不改变 pytest 退出码，但不宣称观测系统已验证。

## 9. 静态检查遗留

执行 `.venv/bin/mypy --follow-imports=silent` 检查本轮四个 Python 文件，仍有 52 项：Bridge 3 项（既有 backend 参数未注解、泛型 list/dict），LangGraph 旧测试 AgentState/泛型等 24 项，S5-B 原测试部分 25 项（未注解、Optional 和 features 推断等）。MCP client 无报告；新增权限/完整轮次用例所在区段无报告。新增测试整理过程中引入的错误导入和类型问题已修正，日志保留。未声称 strict mypy 或全仓门禁全绿。

## 10. 仍受阻或未完成的运行检查

upload 引用测试在本环境超时，未定位到业务根因，不归因于本次修复；workspace 引用独立通过。真实沙箱 7 项因环境依赖跳过。真实 Node→FastAPI、PG 事务/行锁、Redis 跨进程确认/防重放、浏览器刷新/断流/撤权均未获得本轮证据。原环境调查见 S5-C，不推断当前外部服务状态。

## 11. 回滚

按本轮 hunk 撤回绑定检查、目录 LLM 排序、MCP BioOps 失败传播及相应测试；回滚前审查是否重新引入错误成功标记或权限问题。不能整文件 checkout 覆盖共享改动，不删 Dataset/FileRecord/Task/审批事实，无新增迁移。

## 12. C1 结论与保护门禁

S5-C1 = **PASS_ISOLATED**：原 9 项失败归因并修复、双 Runtime 真实分派轮次、可信派生与撤权测试及共享能力关键回归通过。该结论不包含第 9–10 节的未通过检查。没有新增下载执行路径，原确认消费机制未变；源码 `WRITE_RUNTIME_ACCEPTED=False`、`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False` 以及默认关闭的 Gateway/Dataset/Agent 写开关保持。fixture 开启读能力不表示生产启用。

## 13. C2 准入条件

另行取得 S5-C2 指令，准备明确授权的非生产 PG、Redis、Node/FastAPI 与 Chromium；先复核基线与 upload 引用超时，再完成双用户双项目、撤权窗口、真实回调网络、PG 事务/并发、Redis TTL/防重放/单次确认、浏览器刷新和 SSE 中断恢复证据。按范围升级状态，不开放实际下载。G3、逐协议认证、传输硬预算和停止恢复对账仍是后续执行准入条件。本轮止于 C1。
