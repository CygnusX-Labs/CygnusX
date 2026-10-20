# MCP 体系

MCP（Model Context Protocol）是 CygnusX 把平台能力、外部工具和专业数据库暴露给 Agent 的标准通道。平台采用**三层体系**，并对“工具暴露”和“写操作审批”分别治理。

> **当前状态**：MCP 注册、发现、调用、确认凭证和 Builder 均已实现并有隔离测试；外部传输、多用户、真实 Redis/Worker 的部分运行验收仍待完成。**写工具调用受源码门禁保护**，`WRITE_RUNTIME_ACCEPTED=False` 不能被环境变量解除。

## 三层 MCP

| 层 | 示例 | 运行位置 | 特点 |
| --- | --- | --- | --- |
| 内置 Preset | `cygnusx-platform`、`cygnusx-pipelines`、`cygnusx-tools`、`seqout`、`cygnusx-biothings`、`cygnusx-research-data` | 主进程 | 零网络延迟，复用应用服务 |
| 外部 Server | STDIO / SSE / STREAMABLE_HTTP | 独立 `mcp-server/` 或用户配置 | 标准协议，可被外部客户端调用 |
| 管线专属 | 分析流程 SSE（端口从 8900 起） | Flow 运行时 | 与具体 Flow 生命周期绑定 |

内置 Preset 的工具数量会随版本变化，权威清单以 `src/cygnusx/infrastructure/mcp/presets.py` 为准；文档中的数量（platform 22、pipelines 10、seqout 26、biothings 10、research-data 28）只是某个基线的快照。

注册链路：

```text
presets.py
  → ensure_presets()（幂等 upsert）
  → mcp_servers 表
  → Agent YAML 的 mcp_ids 绑定
  → AgentService 装配时按权限与模块开关裁剪
```

外部通道与内置 Preset **共享同一批 provider service**，不复制业务实现；`tests/unit/test_mcp_dual_surface_parity.py` 守护内外双表面一致性。

## 工具固定化：固定动词 + 动态 Flow 目录

自 2026-10-16 起，新增 Flow **不再新增 MCP 工具**。Flow 作为目录数据增长，工具清单保持固定：

| 固定工具 | 作用 |
| --- | --- |
| `cygnusx_list_flows` | 列出当前可提交 Flow（受门控裁剪，分页） |
| `cygnusx_get_flow_detail` | 按需返回单个 Flow 的完整契约 |
| `cygnusx_prepare` | 通用准备信封 `{flow_id, arguments}`，冻结契约并生成确认 |
| `cygnusx_submit` | 消费确认凭证，幂等提交任务 |

设计红线：

- **禁止**把所有 Flow 的 `oneOf` 塞进一个通用 Schema；
- `list_flows` 的输出必须与“实际可提交集合”同源（`FlowService._enabled`）；
- 未开放 Flow 在 `get_flow_detail` 中同样表现为不存在；
- `prepare` 冻结契约版本/哈希，`submit` 不符即拒绝并要求重新 prepare；
- 旧的 per-flow 自动生成工具与 pipelines 四件套已软弃用，纳入 `LEGACY_PIPELINE_TOOLS` 下线路径；默认仍为兼容模式，切换需用户验收。

分页与预算：外部 `cygnusx_list_flows(limit≤50, offset)` 返回 `total/next_offset/has_more`；`llm_payload` 有独立 3000B 预算，超限先裁参数预览再退化摘要，完整数据保留在 `ui_payload`。

## 人类确认凭证

这是 MCP 写路径最重要的一条不变式：**模型永远不能自证确认**。

```text
prepare（服务端校验 + 参数快照 + 契约版本/哈希冻结）
   → 创建 PENDING 确认（owner / project / session / operation / parameters）
   → 前端确认卡（人类 JWT）
   → APPROVED（Redis CAS，一次性）
   → submit（原子消费 + 幂等返回既有 task_id）
```

| 约束 | 值/行为 |
| --- | --- |
| 凭证绑定 | owner、project、session、operation、参数 SHA-256 |
| 有效期 | 默认 30 分钟，可配置 |
| 消费 | 原子、一次性，防并发重放 |
| 幂等 | 同一 `confirmation_id` 重试返回既有 `task_id` |
| 模型自证 | `_confirmed` 已废弃，绝不接受模型布尔值 |

确认卡可显示的参数由 `ui_payload` 提供；模型只能看到压缩后的 `llm_payload`。

## MCP Builder（AI 生成 MCP）

内置 Agent `agent-mcp-builder` 支持从需求生成实验性 MCP Server：

```text
需求 → 规划 → 代码生成 → AST 静态安全检查（12 条规则）
     → 沙箱 /mcp/start · call · stop · list → 审核 → 启用
```

- 数据模型：`mcp_builds`、`mcp_versions`、`mcp_visibility`、`mcp_reviews`。
- 实验 MCP 调用前强制校验：归属 → `review_status=APPROVED` → `is_enabled` → TTL 未过期。
- 单次调用输出超过 16 KiB 时整包替换为截断说明，提示写工作区文件。
- 版本记录含代码/工具/配置快照与契约指纹；回退是 DB 指针切换，**不是制品重建**。
- 尚缺依赖锁定、运行环境摘要、`mcp_deployments` 的 generation 原子激活；共享可见性和 invoke 限流未接线。

## 安全边界

| 检查 | 实现 |
| --- | --- |
| STDIO 命令 | `validate_stdio_command` 白名单/参数校验 |
| SSE URL | `validate_sse_url` 主机与协议校验 |
| STDIO 参数 | `validate_stdio_args` 禁用危险参数 |
| 调用超时 | 默认 30 秒 |
| 日志 | `mcp_logs` 记录调用与状态 |
| 写操作 | 人类确认 + 源码运行门禁 |

已知限制：MCP SSE URL 校验不能覆盖所有网络层风险；`/mcp/call` 无独立频率限制和应用层 token 鉴权（依赖沙箱 UDS 权限与宿主校验）。详见[安全模型](security-model)。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 内置 Preset | `src/cygnusx/infrastructure/mcp/presets.py` |
| MCP Client / 传输 | `src/cygnusx/infrastructure/mcp/` |
| ToolBridge | `src/cygnusx/application/services/tool_bridge_service.py` |
| 固定 Flow 服务 | `src/cygnusx/application/services/analysis_flow_tool_service.py` |
| 确认服务 | `src/cygnusx/application/services/tool_confirmation_service.py` |
| 外部通道 | `mcp-server/tools/`、`mcp-server/ARCHITECTURE.md` |
| Builder | `src/cygnusx/application/services/mcp_builder_service.py` |

## 关联文档

- 权威基线：[`CygnusX_mcp_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md) §1、§11–§12；外部终态见 [`mcp-server/ARCHITECTURE.md`](../../mcp-server/ARCHITECTURE.md)
- [Agent 运行时](agent-runtime) · [Flow 运行时](flow-runtime) · [安全模型](security-model)
- [AI 助手与工作台](../features/ai-chat) · [分析流程](../features/workflows)
