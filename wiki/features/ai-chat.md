# AI 聊天助手

OmicHub AI 助手采用 **Agent-first** 架构，用户先选择智能体再进入对话。

## 架构

- **SSE 流式聊天**：`POST /api/v1/chat/stream`
- **三层数据模型**：`chat_sessions` → `chat_messages` → `chat_assistants`
- **Provider 管理**：`ProviderManager` + `OpenAICompatibleProvider`
- **技能注入**：管理员配置 Skill，自动注入 system prompt
- **MCP 工具调用**：AI 可通过 MCP 查询平台内部状态

## 前端实现

| 组件 | 路径 | 职责 |
|---|---|---|
| `AgentWorkspace.vue` | `components/agent-workspace/` | 智能体工作区外壳 |
| `AgentHub.vue` | `components/agent-workspace/` | 智能体大厅 |
| `AgentSandbox.vue` | `components/agent-workspace/` | 对话区 |
| `KimiMessageList.vue` | `components/ai-chat/` | 消息列表（虚拟滚动） |
| `KimiChatInput.vue` | `components/ai-chat/` | 输入框与斜杠命令 |

## 流式输出

前端使用 `fetch + ReadableStream` 消费 SSE：

```ts
{
  agent_id: string,
  session_id?: string,
  messages: [{ role, content }],
  stream: true,
  temperature?: number,
  max_tokens?: number,
  deep_thinking?: boolean
}
```

事件类型：`text`、`tool_call`、`tool_result`、`error`、`done`。

## 内置助手

- 通用助手
- RNA-seq 助手
- 单细胞助手
- 代码助手
- 文献助手
- 可视化助手
