# CygnusX BioOps Phase 0A 实施记录

日期：2026-10-13

本次实施围绕统一确认契约、外部 MCP 入站边界和分析任务最终校验，复用现有
`ToolConfirmationService`、`FlowSubmissionValidator`、`ManagedFileResolver` 与
`TaskService`，没有新增任务引擎或下载引擎。

## 已落地

- 外部 MCP 下载/普通分析首次调用创建服务端 `PENDING` 确认记录；`user_confirmed=True`
  只返回拒绝，不再作为授权依据。平台网页 JWT 确认后，提交请求携带
  `confirmation_id`，由后端校验用户归属、参数哈希、TTL、状态和一次性消费。
- 新增外部确认请求端点 `POST /api/v1/ai/tool-invocations`。该端点只创建待确认记录，
  `APPROVED` 仍只能由既有 JWT-only approve 端点写入；API Key 不能批准确认。
- 外部任务取消与统一 Run 确认也改为同一 `confirmation_id` 契约，旧布尔值不能放行。
- 外部 RNA/ATAC pipeline 提交不再把 `user_confirmed=True` 转发到平台；提交继续消费
  `prepare` 生成的分析确认记录。
- SSE/HTTP MCP 非回环监听默认启动失败，不再只输出告警；只有明确配置受信任、已鉴权
  网关覆盖时才允许放开。
- `TaskService.submit()` 在创建工作目录、任务记录和队列消息前重新执行统一
  `FlowSubmissionValidator`。受控 `upload://`、`file://`、`directory://` 引用的解析路径
  写回最终 `TaskSubmitRequest`；最终提交拒绝越出用户存储根的路径，并对目录引用做真实
  用户根约束。

## 验证

- `tests/unit/domain/test_flow_submission_validator.py`：8 passed。
- `tests/unit/domain/test_flow_submission_validator.py` +
  `tests/unit/test_mcp_dual_surface_parity.py`：16 passed。
- Phase 0A 聚焦回归集（确认状态机、Flow 校验、MCP 双表面）：19 passed。
- 后端与 MCP 修改范围通过 `python -m compileall -q`，`git diff --check` 通过。
- MCP 传输安全检查验证了回环地址允许、`0.0.0.0` 默认拒绝。
- MCP 本轮触及的 `analysis.py`、`downloads.py`、`pipelines.py`、客户端和入口通过
  `python -m py_compile`；当前环境未安装 `fastmcp`，未进行独立 MCP 进程导入/启动验收。
- Ruff 未能在当前环境执行：`uv` 缓存目录的 `.git` 不可写，且系统未提供独立 `ruff` 命令。

## 剩余风险

- 当前工作树的部分外部 MCP 工具文件在本轮前已存在重复签名/文档字符串污染；未扩展到
  非下载、非分析工具的全面重写。
- Redis 不可用时确认服务回退单进程内存存储，生产多 worker 应保证 Redis 可用。
- API Key 仍代表一个平台服务调用身份，不等于自动获得任意最终用户身份；外部 MCP 对外
  暴露必须使用用户绑定的 API Key 或受信任代理注入的认证上下文。
