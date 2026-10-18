# S5-C2 Shared Agent Runtime Integration & Readiness Acceptance

日期：2026-10-17。结论：**S5-C2 = BLOCKED**；本轮完成可独立开展的超时归因、只读环境核验、隔离回归和交接。未取得 PASS_RUNTIME / PASS_E2E；DOWNLOAD_EXECUTION_READY = FALSE，G3 仍为 PARTIAL_CODE / RUNTIME_BLOCKED。

## 1. 当前基线

HEAD：`51011118535f782f5282f638b4a54649c79bf6d6`。已阅读 [C1 报告](download-s5c1-agent-runtime-code-closure.md)、[C 调查](download-s5c-agent-runtime-acceptance.md)、[B 报告](download-s5b-agent-capability-consumption.md)、[Gateway 架构](../../ARCHITECTURE_DESIGN/CygnusX_agent_tool_gateway.md)及[执行框架](../../ARCHITECTURE_DESIGN/CygnusX_agent_execution_framework.md)。共享工作树原始状态保存于 `evidence/download-s5c2/status-before.txt`。历史 214/32 项不计入本轮测试数量。

## 2. upload 超时根因与处理

原用例 `tests/unit/tools/test_tool_bridge.py::test_upload_ref_resolution` 在本轮单独复现，25 秒限时结束，exit 124；8 秒时抓取全线程栈，见 upload-reproduce.txt。日志已经进入 tool_invocation，线程池工作线程停在空闲取任务，主线程仍在 selector.select；没有进入 pytest teardown。

调用链是 Bridge._resolve_upload_refs → _read_chat_upload → LocalStorageBackend.list/read → asyncio.to_thread。存储同步读使用 with 关闭文件。用例不经过模型 Runtime，也没有下载、确认或网络服务等待。OTel 工作线程在定时等待，Loguru 工作线程在队列读取，栈没有证明二者阻塞业务；不能据独立运行的 closed-stream 日志认定它们是本次超时根因。

进一步运行完全不导入项目的最小程序：`asyncio.run(asyncio.to_thread(lambda: print("thread finished")))`，线程打印完成后程序仍超时（thread-minimal.txt，exit 124）。启用 asyncio debug 并加一个一次性定时器后，thread-wakeup.txt 明确显示 `_write_to_self` 中 `csock.send` 抛出 `PermissionError: [Errno 1] Operation not permitted`；定时器唤醒 selector 后得到 result 42 并正常退出。

**分类：测试执行环境问题。** 沙箱阻断事件循环跨线程 self-pipe 通知，工作已完成但等待者没有被唤醒。该因果可在项目外复现；未发现业务代码死锁或不合理外部依赖等待。线程池 shutdown 也使用跨线程通知，属于同一环境约束。定时器仅用于最小诊断程序，没有加入业务或测试，也没有借它宣布原用例修复。

处理：不修改业务为同步 I/O、不增加测试 timeout、不删断言、不 quarantine。原 upload 用例仍 **BLOCKED**，需要允许本地 IPC/self-pipe send 的执行环境重跑，不能声称已修复。

## 3. 实际修改文件

仅新增本文及 `evidence/download-s5c2/` 本地证据；未修改生产代码、原测试、配置或前端。环境调查完成后不再开发等价 Mock 框架。没有提交、推送、部署、安装高权限组件、迁移、操作业务数据库或执行真实文件下载。

## 4. Node Callback 运行证据

Node v24 安装存在，但本机 HTTP listen(0, 127.0.0.1) 返回 EPERM，见 node-listen.txt。Python TCP 与 Unix socket 创建/绑定也返回 Operation not permitted，见 environment.json。没有明确授权的非生产 FastAPI/Node callback 运行地址，未使用默认业务服务。

真实 Node → FastAPI → Gateway 及 Catalog、GEO/SRA/ENA、Dataset、FileRecord、Task、Prepare、超时、过期、防重放、切换项目和模块关闭全部 **BLOCKED**；没有以 fetch 替身充当真实 Callback。未访问外部元数据来源。

## 5. Legacy / LangGraph 运行证据

本轮重跑 C1 完整轮次所在 S5-B 测试及原 LangGraph/聊天 Runtime 测试；确定性模型、隔离 DB 和外围服务替身边界不变。真实装配与分派代码仍经过 AgentService → Runtime → MCPClient/Bridge → Gateway → 目录业务服务 → 结果回灌 → 最终 ChatChunk。成功、非法参数、事件失败标记及调用计数用例通过。

这是 **PASS_ISOLATED**；没有真实 PG、应用 HTTP SSE、部署配置或浏览器网络链证据，因此两种 Runtime 的 C2 运行验收均 **BLOCKED**。不将模型解释拒绝后正常 done 等同业务工具成功。

## 6. PostgreSQL / Redis 验收

environment.json 记录 E2E_DATABASE_URL、TEST_DATABASE_URL、TEST_REDIS_URL、REDIS_TEST_URL 均未提供，PATH 未找到 postgres 或 redis-server。局部只读程序搜索未发现可用于本轮的服务端程序；不推断机器所有位置均无安装。没有读取或打印 .env 凭据，也不将默认数据库当作获授权的隔离资源。

未创建 User A/B、Project A1/A2/B1。DatasetVersion/FileRecord/Task 归属、ImportProposal 持久化、并发事务和回滚的真实 PG 验证均 **BLOCKED**。Redis 的真实防重放、TTL、单次确认、多进程竞争、故障拒绝、撤销和持久 token_version 一致性均 **BLOCKED**。现有独立 Redis 集成测试为 **1 skipped / 1 warning，0.05s，exit 0**，原因是 redis-server unavailable，详见 redis.txt；skip 不算通过。

## 7. Chromium E2E

Snap Chromium 启动失败：无法创建只读 `/run/user/1000/snap.chromium`，exit 46，见 browser-probe.txt。发现缓存原生 Chromium 后再次尝试，crashpad setsockopt 返回 Operation not permitted，进程 exit 133，见 cached-browser.txt。Node 当前解析路径未找到 playwright、playwright-core、puppeteer，Python 也未找到 playwright/selenium；不据此排除其他目录可能有工具。

浏览器工作流 **BLOCKED**。没有关键截图、服务端请求、Task/Proposal 浏览器关联证据；没有以 jsdom 或离线页面充当 C2 E2E。现有 React Presentation 未改。

## 8. 权限与撤销

本轮隔离集合保留错用户/项目、有限 scopes、项目/会话变化、模块关闭、派生后撤权、委托过期/防重放、原 Import/Handoff 归属检查。真实双用户三项目、并发撤权和浏览器迟到响应矩阵未运行。测试中的身份替身不能替代服务器认证；模型不签发 JWT、委托或扩权。

## 9. 工具错误传播

C1 的 builtin BioOps success/is_error 传播及拒绝不 fallback 逻辑未改，本轮完整轮次与 MCP reliability 回归通过。非法参数不会被 tool_result 标记成功，每例 Gateway 调用次数为一。已有有限权限不会在 Bridge 派生中扩张；工具返回不构成人工批准。真实应用网络链上的业务错误与 SSE 中断仍未验收。

## 10. 分能力验收矩阵

| 能力 | 已有证据级别 | 本轮 C2 运行结论 | 缺少证据 |
|---|---|---|---|
| Catalog Query | PASS_ISOLATED | BLOCKED | 真实双入口与持久身份 |
| Metadata Discovery | PASS_ISOLATED | BLOCKED | 授权有界外部来源与真实回调 |
| Dataset Read | PASS_ISOLATED | BLOCKED | 真实 PG 归属与切换 |
| FileRecord Read | PASS_ISOLATED（历史 C1） | BLOCKED | 真实 PG/FileRegistry 与浏览器 |
| Task Read | PASS_ISOLATED | BLOCKED | 真实持久 Task 关联 |
| Import Prepare | PASS_ISOLATED | BLOCKED | PG Proposal、Redis 原确认 |
| Node Callback | PASS_ISOLATED（历史 B） | BLOCKED | 实际 HTTP 与委托链 |
| Platform AI Legacy | PASS_ISOLATED | BLOCKED | 实际应用配置、PG 与 SSE 网络 |
| Platform AI LangGraph | PASS_ISOLATED | BLOCKED | 同上 |
| Browser Workflow | 本轮 NOT_TESTED | BLOCKED | 可启动 Chromium 与完整测试部署 |

任何一项都未获得本轮 PASS_RUNTIME 或 PASS_E2E。DOWNLOAD_EXECUTION_READY 始终 FALSE。

## 11. 最小资源与剩余阻断

1. 允许 asyncio socketpair/self-pipe send、TCP loopback 和 Unix IPC 的非生产执行器；无需开放任意外网。
2. 明确标识的专用 PG 数据库/角色及 Redis 实例，提供测试地址、生命周期和清理范围；与业务数据隔离，允许两用户三项目、并发及失败回滚测试。
3. 版本明确的 FastAPI 与 Node Research Runtime，固定 callback、可信服务端签发委托；仅启用获授权的测试读/Prepare 配置，执行门禁继续关闭。
4. 可运行的 Chromium 与自动化驱动，可写的 profile/runtime 目录，访问测试 UI/API；保存截图、浏览器日志及服务端关联。
5. 如测试真实 GEO/SRA/ENA，提供明确允许来源、请求数/响应大小/超时边界；不获取科学文件、不启动下载 Worker。

以上当前未具备。不自动部署替代，不向默认数据库试写，不使用模拟结果提升状态。

## 12. 测试与日志

根目录 `evidence/download-s5c2/`：status-before.txt、upload-reproduce.txt、thread-minimal.txt、thread-wakeup.txt、environment.json、node-listen.txt、browser-probe.txt、cached-browser.txt、isolated-regression.txt、redis.txt。

本轮隔离回归 **144 passed / 2 warnings，4.45s，exit 0**。命令前缀 `LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib .venv/bin/pytest`，集合为 tests/unit 下 test_download_s5b_consumption.py、test_download_s5a_catalog.py、test_langgraph_runtime.py、chat/test_langgraph_chat_runtime.py、mcp/test_reliability.py、test_agent_tools_phase2.py、test_dataset_gateway_phase3.py、test_dataset_import_handoff.py，参数 `-q -m "not quarantine"`。warning 为存量 Pydantic Config 与短 JWT key。部分进程退出后仍有存量 OTel/Loguru closed-stream 导出日志，保留但不当作本轮业务通过证据。

原 upload 命令：同环境前缀，外加 `timeout 25`，用例名为 test_upload_ref_resolution，参数 `-vv -s -o faulthandler_timeout=8`。Redis 命令为原 tests/integration/test_phase0b_redis.py 加 `-q -rs`。没有生产代码修改，本轮未重跑全仓静态检查；C1 的 mypy 存量错误继续保留，不能声称全量门禁全绿。

## 13. 回滚

仅撤回本次新增报告和本地证据即可，无程序、数据库或部署回滚。不整文件恢复其他阶段改动，不删除既有 Dataset/FileRecord/Task/确认事实。

## 14. S5-C2 结论

**BLOCKED**。C2-0 已完成环境级根因定位，原用例仍待允许 IPC 的环境复验；C2-1 至 C2-4 缺少实际运行条件，按任务的环境缺失流程完成只读核验和最小资源清单。本文不是运行通过声明。

## 15. 后续 S6 准入建议

先补 C2 所需资源并重跑 upload、双入口、PG/Redis、权限与 Chromium 全矩阵，再按能力更新证据。即使只读与 Prepare 全部通过，也须另行完成 G3 受信执行、逐协议/版本认证、真实出站约束、传输硬预算、停止与恢复对账及原人工批准条件。`WRITE_RUNTIME_ACCEPTED=False`、`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False` 保持，原 DownloadService、Gateway、FileRegistry、DatasetImportService、TaskService、ToolConfirmationService 均复用且未修改。本轮按要求停止。
