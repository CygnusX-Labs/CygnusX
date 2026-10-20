# Agent 运行时

Agent 是 CygnusX 的**数据驱动执行对象**：它由 `data/ai/*.yaml` 声明，经 `ensure_builtin_agents()` 同步到 `agent_templates` 表，再在一次请求中由上下文构建器装配提示词、模型、工具、MCP、Skill、知识与记忆。Agent 不是通过继承基类定义的，新增 Agent 主要是新增配置并在注册表登记。

> **当前状态**：Agent 装配、LangGraph/Legacy ReAct、Studio Loop 与 AgentTeams 执行路径均已实现；AI → 审批 → 执行 → 产物的**真实受控闭环尚未作为当前源码端到端能力验收**。写操作仍受[共享 Agent 工具层](mcp)与源码门禁保护。

## 一次 Chat 请求如何流转

```text
POST /api/v1/chat/stream (SSE)
  → 中间件：身份 / 模块门禁 / 限流 / 审计
  → ChatService
  → AgentRuntimeGateway
      ├─ 请求准备：AgentContextBuilder
      │    会话历史 · Agent 配置 · Prompt · Provider · Tool/MCP/Skill
      │    知识库 · 记忆 · 计费上下文
      └─ 选择 Runtime
           ├─ LangGraph ReAct（默认）
           └─ Legacy ReAct（逃生舱）
  → 模型调用 / 工具循环
  → ChatEventService：唯一事件出口
  → SSE 增量 + 消息/usage/审计落库
```

对话历史由**前端显式传入**，后端按请求装配，不维护跨请求会话状态机；上下文经三层裁剪后才进入模型请求。数据库原文是权威，压缩视图只用于模型请求。

## 执行路径

| `execution_path` | 场景 | 说明 |
| --- | --- | --- |
| `chat_langgraph` | 普通 Chat 默认路径 | 单 Agent 的 LangGraph ReAct 图；不用 checkpoint |
| `chat_legacy` | 普通 Chat 逃生舱 | 保留旧 ReAct 行为，用于灰度回退和兼容 |
| `studio_chat_loop` | OmicStudio | `STUDIO_TOOL_NAMES` 当前注册 28 个工具名、工作区文件、一会话一沙箱，受 `StudioLoopGuard` |
| `agentteams_manager_consultation`（规划值，未发射） | 早期设计的协作室 Manager 会诊 | 当前代码无该赋值；Manager 会诊事件投影记录为 `agentteams_worker_react` |
| `agentteams_worker_react` | 协作室 Worker | 独立 child_session 的受限 ReAct，带禁止项 |
| `agentteams_tool_execution` | Worker 工具执行 | 受控工具桥接，结果回投房间 |

改 Chat 链路前必须先在这张表里确认目标路径；`agentteams_manager_consultation` 仅为历史规划值，不得用于排障或新增运行路径。改错路径不会生效。编排图才使用 checkpoint，单 Agent ReAct 图不使用。

## Agent 配置与装配

| 资产 | 位置 | 说明 |
| --- | --- | --- |
| Agent 声明 | `data/ai/*.yaml` | 人设、工具包、Skill/MCP 绑定、Studio 运行时画像 |
| 启用清单 | `data/CygnusX.yaml` 的 `agents.enabled` | 决定加载哪些 Agent；新增 Agent 必须与 YAML 同时登记 |
| 提示词 | `data/ai/prompts/` + `registry.yaml` | 共享片段由 loader 统一追加；发布须经管理端 API 写入 DB |
| 数据库模板 | `agent_templates` | 运行时读取的 Agent 配置 |
| 上下文构建 | `AgentContextBuilder` | 会话、记忆、知识、计费与工具装配 |

要点：

- `agents.enabled` 当前启用 19 个 Agent，仓库中约有 20 份 Agent YAML；未登记会**静默不加载**。
- 每个 Agent 必须声明 Studio 运行时镜像，`tests/unit/test_agent_loader_studio.py` 强制校验。
- 提示词中的 `{{runtime_images}}`、`{{bio_packages}}` 是 loader 注入占位符；写双花括号会被当作占位符处理。
- 管理员保存的 DB 配置优先于内置 YAML 的运行时覆盖；`ensure_builtin_agents()` 幂等同步时不会覆盖管理员绑定。

## 模型、工具与双通道

- **Provider**：自研 OpenAI-compatible 适配层，统一处理流式响应、usage 与错误；模型路由默认关闭，见[模型路由与 Token 计费](model-routing-billing)。
- **工具裁剪**：请求级 `tool_packs` 决定注入哪些工具；未授权工具不会出现在模型可见清单里。
- **双通道**：`llm_payload` 是给模型的压缩结果，`ui_payload` 是给前端的完整展示数据（如确认卡）。大结果写工作区文件，不塞进模型上下文。
- **MCP**：内置 Preset、外部 Server 与管线 MCP 三层的接入见 [MCP 体系](mcp)。
- **Skill**：L1 索引/L2 正文/L3 资源的渐进披露见 [Skill 体系](skills)。

## 事件、审批与保护

统一事件包含生命周期事件与工具事件链：`agent_tool_call` → `agent_tool_started` → `agent_tool_result`，由 `tool_call_id` 贯穿。前端按事件类型显示进度、工具调用、审批卡和终态；默认展开底层事件以便审计。

保护机制：

| 机制 | 作用 |
| --- | --- |
| 轮次治理 | 普通对话与工具循环的轮次上限（约 100/1000 两级） |
| `StudioLoopGuard` | Studio 循环熔断，必要时降级到 supervised |
| `duplicate_tool_call` | 拒绝重复工具调用 |
| 无进展 Guard | 连续无新信息时停止循环 |
| 审批闸 | 高风险工具需人类确认；模型不能自证确认 |
| `ask_user` | 数据缺失时统一中断并向用户澄清 |

## 协作形态

| 形态 | 机制 | 适用 |
| --- | --- | --- |
| Supervisor | Manager 规划、派单与复核 | AgentTeams 协作室 |
| Handoff | 按 `allowed_targets` 串行交接 | 专家转交 |
| Map-Reduce | 请求内 `parallel_subagents` 并行子循环 | 多个独立小任务 |
| Group Chat | 多专家会诊（≤3 个 LLM，无工具） | 方案讨论 |

协作能力默认关闭，需要部署开关、Agent 配置与权限同时满足。

## 修改门禁

1. 改 Chat 执行/事件流 → 跑 `tests/e2e/chat_golden` 与 LangGraph 沙箱用例。
2. 改 Agent YAML、提示词或 Studio 画像 → `make validate-image-mapping` + `scripts/test_studio_agent_runtime.py` + 加载验证。
3. 改工具包或 MCP 绑定 → 检查请求级裁剪与双表面一致性；写工具必须保留确认门。
4. 不要把内部提示词、完整系统消息或密钥写入日志/Wiki。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| Chat SSE 入口 | `src/cygnusx/api/v1/chat.py` |
| Chat 用例与事件 | `src/cygnusx/application/services/chat_service.py`、`application/services/chat/chat_event_service.py` |
| 请求准备/上下文 | `src/cygnusx/application/services/chat/request_preparation.py`、`agent_context_builder.py` |
| Agent 配置加载 | `src/cygnusx/infrastructure/config/agent_loader.py` |
| 工具 Schema | `tool_configs/tools_schema.yaml` |
| Provider | `src/cygnusx/infrastructure/ai_provider/` |

## 关联文档

- 权威基线：[`CygnusX_agent_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_agent_architecture.md)、[`CygnusX_agent_execution_framework.md`](../../ARCHITECTURE_DESIGN/CygnusX_agent_execution_framework.md)、[`CygnusX_agent_framework_baseline.md`](../../ARCHITECTURE_DESIGN/CygnusX_agent_framework_baseline.md)
- [MCP 体系](mcp) · [Skill 体系](skills) · [沙箱与执行隔离](sandbox) · [记忆与知识库](memory-knowledge)
- [AI 助手与工作台](../features/ai-chat) · [AI 多 Agent 协作](../features/ai-collaboration)
