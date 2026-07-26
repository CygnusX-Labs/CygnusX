# OmicHub AI 助手最终框架基线

> **基线日期**：2026-07-26  
> **适用范围**：当前 `data/ai/` Agent 配置、`data/ai/prompts/` 系统提示词、普通聊天、OmicStudio、Handoff 与 MAS 灰度链路。  
> **定位**：本文描述“当前可运行的最终基线”，用于提示词发布、工具授权、Agent 扩展和部署验收。历史演进和更完整的扩展说明见 `agent_architecture_and_extension_guide.md`。

---

## 1. 架构结论

OmicHub 当前采用的是**配置驱动的 Tool Agent 架构**：每个 Agent 有独立身份、提示词、模型、工具白名单、Skill 绑定、Studio 运行时能力和审计上下文；模型可在 ReAct 循环中调用工具，再根据结果继续回答。

它不是仅靠 System Prompt 区分角色的普通聊天系统，已具备：

- Agent 路由、独立运行上下文与模型绑定；
- MCP / 内置工具调用、工具结果回灌和用户隔离；
- 长期记忆、同会话 Handoff、Studio 沙盒；
- 可选的 LangGraph ReAct 执行器；
- 受开关控制的 MAS 计划与 DAG 执行基础设施。

但默认入口仍不是“多个专家自动协同讨论”的 MAS：`agent-router` 每轮只选择一个目标专家；`agent-orchestrator` 仅在 `MAS_ENABLED=true` 时加载，且普通聊天不会自动发起 MAS Run。

---

## 2. 配置、发布与运行时来源

```text
data/OmicHub.yaml                启用哪些内置 Agent
          │
          ▼
data/ai/<agent>.yaml             Agent 声明：模型、prompt_file、工具包、功能开关、Studio
          │
          ├── data/ai/prompts/*.md        可版本控制的提示词源码
          ├── data/ai/tools/*.yaml        声明式最小权限工具包
          ├── data/ai/runtime_images.yaml Studio 运行时能力目录
          └── data/ai/mas/*.yaml          MAS 能力、产物契约、工具策略
          │
          ▼
AgentService.ensure_builtin_agents()
          │
          ▼
AgentTemplate 数据库记录          普通聊天的实际运行时来源
          │
          ▼
AgentService.get_agent_context()
          │
          ▼
ChatService → 手写 ReAct 或 LangGraph ReAct → 模型 / 工具 / SSE
```

### 2.1 关键发布规则

- Markdown 与 YAML 是**版本化源码**；数据库 `AgentTemplate.system_prompt` 是已发布 Agent 的运行时提示词。
- 新建内置 Agent 时，YAML 中的提示词、工具绑定和功能配置会写入数据库。
- 已存在的内置 Agent 启动同步时只同步能力相关 `features`，**不会自动覆盖**管理员可能修改过的模型、提示词和绑定关系。
- 因此，修改 `data/ai/prompts/*.md` 后必须通过管理端保存对应 Agent，或调用 `PUT /api/v1/admin/agents/{agent_id}` 发布 `system_prompt`；仅改文件并重启不能证明线上已生效。

---

## 3. 当前 Agent 清单

`data/OmicHub.yaml` 默认启用以下七个 Agent：

| Agent ID | YAML | 角色 | 默认执行形态 | 主要能力 |
| --- | --- | --- | --- | --- |
| `agent-router` | `data/ai/router.yaml` | 统一入口 | 路由模型调用 | 选择一个合适的目标专家 |
| `agent-general` | `data/ai/general.yaml` | 通用助手与分诊 | LangGraph ReAct | 问答、文件目录/搜索、记忆、转交、科研检索 |
| `agent-rnaseq` | `data/ai/rnaseq.yaml` | RNA-seq 分析师 | 手写 ReAct | Bulk RNA-seq 方案、KEGG、记忆、转交 |
| `agent-scrna` | `data/ai/scrna.yaml` | 单细胞分析师 | LangGraph ReAct | 单细胞方案、KEGG、记忆、转交 |
| `agent-code` | `data/ai/code.yaml` | 代码助手 | 手写 ReAct / Studio | 代码设计、文件目录/搜索、转交 |
| `agent-viz` | `data/ai/viz.yaml` | 可视化专家 | 手写 ReAct / Studio | 绘图工具、文件目录/搜索、转交 |
| `shania` | `data/ai/shania.yaml` | 个性化科研助手 | 手写 ReAct / Studio | 通用科研问答、记忆、转交、科研检索 |

`agent-orchestrator` 定义于 `data/ai/orchestrator.yaml`。它默认不在 `agents.enabled` 列表中；`MAS_ENABLED=true` 时加载器才自动将其加入内置 Agent 同步。

---

## 4. 请求执行链路

```text
用户消息
  │
  ▼
ChatService.stream_agent_chat()
  │
  ├─ 解析当前 Agent 的数据库记录
  ├─ AgentService.get_agent_context()
  │    ├─ 模型 / Provider
  │    ├─ system_prompt
  │    ├─ 工具包白名单过滤后的 MCP 与内置工具
  │    ├─ 已绑定 Skill 的 L1 索引与 use_skill / skill_resource
  │    └─ Agent features（router、handoff、Studio、web_search 等）
  │
  ├─ router Agent：一次模型路由 → 目标 Agent 上下文
  ├─ 时效请求：预搜索并将来源注入上下文
  ├─ 可选：用户记忆召回、Handoff 控制流、Studio 能力装配
  │
  └─ 执行器
       ├─ LangGraph：llm_call → tool_exec → llm_call → ... → END
       └─ 手写 ReAct：模型 → 工具 → 工具结果回灌 → 模型
```

所有工具调用通过 `ToolInvocationContext` 传入当前用户、会话、Agent 与数据库上下文；工具实现必须据此执行权限、文件路径和审计校验。

---

## 5. 提示词与工具契约

提示词只能描述**当前运行时实际注入**给模型的工具。运行时会读取 `features.tool_packs` 并按 `mcp_tools` / `builtin_tools` 白名单过滤；“平台里存在某工具”并不代表每个 Agent 都能调用。

### 5.1 工作区文件能力（当前最终边界）

所有配置了 `tool_packs: [workspace, ...]` 的 Agent 当前只获得：

| 工具 | 用途 |
| --- | --- |
| `list_workspace_files(path?, pattern?)` | 列出当前用户工作区目录项，返回文件 ID、名称、类型、大小、路径和时间。 |
| `search_workspace_files(query, limit?)` | 递归按文件名搜索当前用户工作区。 |

当前 `data/ai/tools/workspace.yaml` 没有授权 `workspace_read_file` 或 `workspace_get_file_info`。因此最终提示词遵循以下边界：

- 用户问“工作区有什么”必须先调用 `list_workspace_files`；
- 用户要求找文件必须先调用 `search_workspace_files`；
- 不得宣称已读取 `@` 引用文件内容、已读表或已查看文件元数据；
- 需要内容预览、读表、绘图或真实执行时，引导至对应专家 Agent 或「AI 工作台」；
- 不得让用户用文件面板代替 Agent 应可完成的目录列举和文件搜索。

平台 MCP 中虽然实现了 `workspace_read_file` 和 `workspace_get_file_info`，但在把它们加入工具包白名单并做权限回归前，不得重新写入 Agent 提示词。

### 5.2 Skill 契约

- `use_skill`、`skill_resource` 仅在 Agent 实际绑定了有效 Skill 时注入。
- 当前内置 Agent YAML 的 `skill_ids` 默认均为空；因此提示词必须使用“当任务与你**已挂载**技能匹配时”的条件表述。
- Skill 使用三层渐进披露：L1 索引常驻；L2 用 `use_skill` 加载 `SKILL.md` 正文；L3 用 `skill_resource` 读取 `references/` 或 `assets/`。

### 5.3 时效检索契约

- 每个 Agent 的 `features.web_search` 定义时效触发词。
- 命中“最新、今天、文献、数据库更新、软件版本”等问题时，框架在模型回答前强制预搜索并注入来源。
- 检索失败时，系统提示词会追加降级约束：必须说明无法实时核验，不得把训练知识表述为最新事实，也不得伪造来源。

### 5.4 记忆与 Handoff 契约

- 配置 `memory` 工具包的 Agent 可使用保存、更新、遗忘和检索用户跨会话记忆；召回内容按用户和 Agent 隔离。
- 配置 `handoff` 工具包的 Agent 可调用 `transfer_to_agent`，但目标必须在其 `allowed_targets` 白名单中，且跳数受 `max_hops_per_session` 限制。
- Handoff 使用受长度、路径和审计约束的交接包；源 Agent 结束后才以交接包启动目标 Agent，不能把控制工具当作普通文本结果继续回答。

---

## 6. 路由、执行器与 Studio

### 6.1 Router

`agent-router` 的提示词只允许输出一个路由 JSON。框架调用 `_route_to_agent()` 解析该 JSON，并对不存在目标、模型失败或格式错误回退至 `agent-general`。路由是**单次分派**，不是多专家并行会诊。

### 6.2 ReAct 与 LangGraph

- `agent-general`、`agent-scrna` 的 `features.engine: langgraph` 在非 Studio 会话使用 LangGraph 图化 ReAct。
- 其他普通 Agent 使用 ChatService 内的手写 ReAct 循环。
- 两种执行器都必须支持工具结果回灌、Handoff 控制信号、错误信封和最大工具轮数限制；业务语义不得因执行器不同而改变。

### 6.3 OmicStudio

Studio 是真实代码执行与产物生成的工作台，而不是普通聊天工具的隐式替代品：

- Agent YAML 的 `studio.runtime_profile` 和 `required_capabilities` 决定可选沙盒镜像；
- Studio 以会话为边界挂载工作区、沙盒和渐进式能力目录；
- 代码、读表、出图、文件产物等需要真实执行的任务应在 Studio 完成，并向用户报告实际产物，而不是在普通聊天中虚构运行结果。

---

## 7. MAS 灰度边界

MAS 具备 Plan、审批、Run、节点、产物 Schema、A2A 事件和 Celery 调度基础设施，但默认关闭：

```text
MAS_ENABLED=false  → agent-orchestrator 不作为默认入口加载，普通聊天不创建 MAS Run
MAS_ENABLED=true   → 加载 orchestrator；仍需部署 Celery/outbox 与目标执行镜像
```

启用前必须同时验证：

1. `MAS_ENABLED=true`；
2. 数据库已执行至当前 Alembic head；
3. Celery Worker / outbox 消费者可用；
4. `analysis-scrna` 等 MAS 所需运行镜像已部署；
5. 计划确认、失败重试、产物下载和审计事件均可在前端闭环。

---

## 8. 修改与扩展流程

### 8.1 修改现有提示词

1. 编辑 `data/ai/prompts/<agent>.md`；
2. 同步更新 `docs/26.7.26/ai_agent/OmicHub-Agent系统提示词优化版.md` 中对应代码块；
3. 对照该 Agent 的 `tool_packs`、`skill_ids`、Studio 能力和 `handoff.allowed_targets` 检查每个工具声明；
4. 运行提示词和 Agent Loader 测试；
5. 在管理端保存 Agent 或调用更新 API 发布到数据库；
6. 用真实会话覆盖常规、工具、时效、越界和失败降级场景。

### 8.2 新增或授权工具

1. 先实现或注册工具，明确 JSON Schema、用户隔离、授权、审计和失败返回；
2. 在 `data/ai/tools/<pack>.yaml` 通过 `builtin_tools`、`platform_tools` 或 `mcp_tools` 精确授权；
3. 在目标 Agent YAML 的 `tool_packs` 引用该工具包；
4. 仅在运行时确认工具已注入后，才在提示词中增加调用协议；
5. 对已落库 Agent，在管理端复核 MCP / Skill 绑定与提示词发布状态；
6. 测试“模型选择工具 → 服务执行 → 工具结果回灌 → 最终回答”的完整闭环。

### 8.3 新增 Agent

1. 创建 `data/ai/<name>.yaml` 和 `data/ai/prompts/<name>.md`；
2. 在 `data/OmicHub.yaml` 的 `agents.enabled` 加入名称；
3. 选择最小工具包、模型、Studio runtime profile 和 Handoff 白名单；
4. 在 `data/ai/prompts/registry.yaml` 登记提示词；
5. 验证加载、数据库发布、真实工具调用和前端入口。

---

## 9. 发布验收清单

### 提示词与配置

- [ ] 每份 `prompt_file` 存在、非空，且与优化版规范文档对应代码块一致；
- [ ] 提示词不声明未被工具包白名单授权的工具；
- [ ] `skill_ids` 为空时，提示词对 Skill 使用条件表述；
- [ ] Handoff 目标均为已启用或可加载的 Agent；
- [ ] 时效检索触发词和提示词要求一致；
- [ ] 修改后的提示词已通过管理端/API 发布到数据库。

### 运行时

- [ ] 绑定模型处于启用状态且支持所需 function calling；
- [ ] Router 能路由、错误时回退 `agent-general`；
- [ ] 文件列表与搜索均使用当前用户工作区，不泄露其他用户数据；
- [ ] Handoff、记忆和工具错误均产生可解释的 SSE/审计结果；
- [ ] Studio 任务只在可用镜像与能力范围内运行；
- [ ] MAS 灰度部署已完整验证，不把“代码存在”当作“产品已启用”。

---

## 10. 本次基线验证

本基线完成时已执行以下静态与单元验证：

- 优化版文档与八份 Agent 提示词逐字一致：`8/8`；
- `general.md`、`shania.md` 不再声明未授权的工作区读取/元数据工具：`2/2`；
- 提示词配置、Agent Loader、文件工具相关测试：`30 passed`；
- Agent Handoff、Skill、联网搜索、文件工具等兼容测试：`75 passed`；
- `git diff --check` 通过。

LangGraph 运行时测试在当前本地环境中曾出现首项通过后无法在 90 秒内收尾的情况；这属于测试稳定性或外部依赖问题，不能据此声称 LangGraph 全量回归已绿。发布前应在具备完整模型与依赖环境的部署链路中复跑该测试。

---

## 11. 关键实现位置

| 责任 | 文件 |
| --- | --- |
| 启用 Agent 与站点配置 | `data/OmicHub.yaml` |
| Agent YAML / 工具包 / 提示词 | `data/ai/` |
| Agent YAML 加载与工具包展开 | `src/omichub/infrastructure/config/agent_loader.py` |
| 内置 Agent 同步与运行时上下文装配 | `src/omichub/application/services/agent_service.py` |
| 聊天调度、路由、预搜索、Handoff | `src/omichub/application/services/chat_service.py` |
| LangGraph ReAct | `src/omichub/infrastructure/execution/langgraph_runtime.py` |
| LangGraph 节点 | `src/omichub/infrastructure/execution/langgraph_nodes.py` |
| 工作区平台 MCP 工具 | `src/omichub/infrastructure/mcp/presets.py` |
| Skill 渐进式披露 | `src/omichub/domain/skill/services.py` |
| MAS 功能开关 | `src/omichub/core/config.py` |
| MAS 能力与产物契约 | `data/ai/mas/` |

