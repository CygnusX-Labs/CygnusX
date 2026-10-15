# CygnusX BioOps Phase 0B Closure 实施与准入验收

审计日期：2026-10-15（Asia/Shanghai）。本轮按用户列出的 WP0-WP5 执行；未找到本轮所称
《Phase 0B Closure 详细优化与实施方案》附件原文，因此以下矩阵以本轮目标、仓库代码和
上一版 Phase 0A/0B 报告为事实来源。没有把缺失的方案内容推定为已执行。

## WP0 基线与环境封存

已重新执行 `git status --short`、branch、HEAD、递归 submodule 盘点。主仓仍为
`feat/reproducible-report-phase0` / `c68ea9e0d6ecb63cb5678444ad3dd1e2a8a00407`，工作树
包含原有报告系统、前端、Phase 0A/0B 和子模块未提交修改；本轮未 reset、clean、checkout、
commit 或 push。所有工作树状态及递归子模块 HEAD/dirty paths 写入 Runtime Manifest。

本机探针结果：Docker CLI 存在但 daemon socket 返回 `operation not permitted`；未发现
`redis-server`/`redis-cli`；loopback/Unix socket 创建权限受限。故本轮不能把宿主机模拟、
进程内 FastMCP Client 或 ASGITransport 升级为真实部署证据。

## WP1 版本与来源闭合

寻宝鼠 Compose 默认 tag 为 `cygnusx-treasure-mouse-{chat,web}:1ea2f79`，build context
为主仓 `pipelines/Treasure-Seeking_Mouse`，其 HEAD 为 `88dae95e...`，存在来源漂移。
Docker inspect、image ID、digest、运行容器 label 无法获取；本轮不通过改 tag 伪造闭合，
状态仍为 **BLOCKED/FAIL**。后续必须从干净源码构建并记录 git SHA、image ID、digest，
再从实际容器回读相同元数据。

下载运行时从 `tool_configs/download/download_config.yaml` 解析到
`/data/omichub/bin/EBIDownload`，宿主机实测 `ebidownload-cli 1.4.0`，SHA-256 为
`6628ad8fd489eee68b9ebd58299f32c021812b386435a82193911c4494e219c4`。这不是 Worker
容器证据。相邻 Polariseq/EBIDownload 源码 VERSION 为 1.4.3，未替换或执行。
Worker 实际配置路径 `/home/zj/pipeline/{RNAFlow,ATACFlow}`，分别为
`b83c27d0...`（dirty）和 `8a173fbb...`（clean）；主仓 submodule SHA 不可代替它们。

## WP2 Redis 与确认状态

源码修复已落地：生产默认 Redis，Redis 故障返回 503；内存 store 仅测试显式注入；Lua
CAS 检查 expected status、过期时间和 changed 结果；task 审批先占用 `SUBMITTING` 再调用
业务提交；失败方不得重复执行。Unit/ASGI 集成测试覆盖 TTL 语义、过期、重放、参数篡改、
跨 owner、并发双消费和 Redis 故障关闭。

真实 Redis 双消费者、故障恢复、TTL/restart 不能在本机执行，因为没有 Redis binary 且
本地 socket 权限被拒绝。新增测试 `tests/integration/test_phase0b_redis.py` 只会启动
临时 Unix-socket Redis，不会连接配置 Redis；当前明确 `BLOCKED`，迁移执行步骤见 Runbook。

## WP3 MCP Transport 与双用户边界

FastMCP 主入口进程内真实 Client 已发现 71 工具并完成 schema、结构化错误、confirmation_id、
伪造 token 拒绝和 lifespan 资源关闭测试；pipeline 入口发现 10 工具。新增下载确认回归，
确保直链列表和云存储 object URI 与平台 DTO 规范化后的重试参数一致；同时修复已有事件循环
中导入 MCP 主模块时的未 await 自校验协程。当前 MCP runtime 测试为 4 PASS、4 环境 SKIPPED。
HTTP/SSE/STDIO 外部 transport 仍未完成：socket 权限阻断 loopback server，STDIO initialize
在受限环境跳过。未开放公共监听。

当前外部 MCP token 只认证隔离 MCP 客户端，不把 Header 映射成任意平台用户；REST API Key
owner 仍由平台绑定。完整双用户真实栈（两个 JWT/API key、MCP transport、人工 JWT approve、
任务/文件/审计落库）需在 Docker/Redis/Postgres 隔离环境执行，当前不宣称通过。

## WP4 任务、下载与审计链

真实应用服务组合加隔离 repo/queue doubles 已覆盖 RNA/ATAC 合法提交、最终 Flow 校验、
owner 查询、幂等键、路径逃逸、下载文件登记与跨用户拒绝。负向用例确认验证失败前不落库、
不入队、不创建目录。真实 Celery/Worker/数据库提交和全链路审计落库仍未运行。

## WP5 门禁与交付

已更新：

- [Runtime Manifest](../audits/cygnusx-runtime-provenance-manifest.json)
- [G-01～G-13 矩阵](../audits/cygnusx-phase0b-closure-gates.md)
- [任务对账 Runbook](../audits/cygnusx-phase0b-task-reconciliation-runbook.md)

本轮聚焦回归：确认服务、HTTP 边界和 MCP 双表面 21 PASS；MCP runtime 4 PASS、4 环境
SKIPPED；此前 Phase0B 服务/安全/validator 用例 22 PASS。compileall、`git diff --check`、
聚焦 Ruff、确认/validator mypy 通过。真实 Redis、Docker、外部 MCP transport 和 Worker
验收仍未执行。
Docker Compose synthetic config 通过，但不代表容器可启动。

## 准入结论

**BLOCKED。** 未解除的关键项是：寻宝鼠镜像来源/运行 digest 漂移、Worker 二进制和流程
挂载未实测、真实 Redis 多进程 CAS 未验收、真实外部 MCP transport 未验收、双用户全栈
任务/文件/审计链未验收。不得开放寻宝鼠下载、分析提交等有副作用 Agent 工具。

在隔离环境完成 Runbook 中 G-01、G-02、G-04、G-06、G-07、G-08、G-09、G-10、G-12
后，重新生成 Manifest；全部必需门通过且无来源漂移后，才可改为 READY。只读前端或身份
准备可在 CONDITIONAL 许可下继续，但不等于写工具开放。
