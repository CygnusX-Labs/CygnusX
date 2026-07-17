/**
 * useAgentChatStream — Agent 调度中枢的 SSE 流式聊天 Composable
 *
 * 基于 fetch + ReadableStream 解析 Server-Sent Events。
 * 与 useChatStream 的区别：
 *  - payload 用 agent_id（走后端 Agent 编排闭环）
 *  - 解析 tool_call / tool_result 事件，供前端渲染工具调用气泡
 */
import { ref } from 'vue'

export interface AgentChatStreamOptions {
  agentId: string
  messages: { role: string; content: string }[]
  sessionId?: string
  /** 当前请求强制使用的模型配置 ID（覆盖 Agent 默认模型） */
  modelId?: string
  /** 温度（0-1），后端 Agent 编排层可透传给底层模型 */
  temperature?: number
  /** 单次回复最大 token 数 */
  maxTokens?: number
  /** 是否开启深度思考/推理模式 */
  deepThinking?: boolean
  /** 当前用户消息的附件 */
  attachments?: ChatAttachment[]
  /** 是否启用联网搜索 */
  enableWebSearch?: boolean
  /** 是否启用代码执行（仅作标记，实际由前端 Pyodide 执行） */
  enableCodeExecution?: boolean
}

export interface ChatAttachment {
  type: 'image' | 'file'
  url: string
  name: string
  mime_type: string
  file_id?: string
}

export interface ToolCallEvent {
  tool_call_id: string
  tool_name: string
  arguments: Record<string, unknown>
  mcp_server?: string
}
export interface ToolResultEvent {
  tool_call_id: string
  tool_name: string
  success: boolean
  result: unknown
  ui_payload?: Record<string, unknown>
  mcp_server?: string
}

export interface StudioPlanStep {
  title: string
  status: 'pending' | 'in_progress' | 'done'
}

export interface TokenUsage {
  input?: number
  output?: number
  total?: number
  input_tokens?: number
  output_tokens?: number
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export interface AgentStreamCallbacks {
  onText?: (text: string, isReasoning?: boolean) => void
  onSessionCreated?: (sessionId: string, messageId: string) => void
  onToolCall?: (event: ToolCallEvent) => void
  onToolResult?: (event: ToolResultEvent) => void
  /**
   * Studio 工具执行过程中的 stdout/stderr 增量输出
   * （sandbox_execute 边跑边推；Studio 工具事件带 tool_call_id，旧事件可能仅带工具名）
   */
  onToolOutput?: (tool: string, stream: 'stdout' | 'stderr', data: string, toolCallId?: string) => void
  onPlan?: (steps: StudioPlanStep[]) => void
  onError?: (error: string) => void
  onDone?: (sessionId: string, messageId: string, usage?: TokenUsage) => void
}

export function useAgentChatStream() {
  const isStreaming = ref(false)
  const abortController = ref<AbortController | null>(null)

  async function streamChat(
    options: AgentChatStreamOptions,
    callbacks: AgentStreamCallbacks,
  ): Promise<void> {
    if (isStreaming.value) return
    isStreaming.value = true
    abortController.value = new AbortController()

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          agent_id: options.agentId,
          session_id: options.sessionId,
          model_id: options.modelId,
          messages: options.messages,
          stream: true,
          temperature: options.temperature,
          max_tokens: options.maxTokens,
          deep_thinking: options.deepThinking,
          attachments: options.attachments || [],
          enable_web_search: options.enableWebSearch || false,
          enable_code_execution: options.enableCodeExecution || false,
        }),
        signal: abortController.value.signal,
      })

      if (!response.ok) {
        const errorText = await response.text()
        callbacks.onError?.(`请求失败 (${response.status}): ${errorText}`)
        return
      }
      if (!response.body) {
        callbacks.onError?.('浏览器不支持流式响应')
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let doneReceived = false
      let errorReceived = false

      const processLine = (line: string) => {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith("data:")) return
        const data = trimmed.slice(5).trimStart()
        if (!data) return
        try {
          const parsed = JSON.parse(data)
          handleStreamEvent(parsed, callbacks)
          if (parsed.type === "done") doneReceived = true
          if (parsed.type === "error") errorReceived = true
        } catch {
          console.warn("[AgentChatStream] 无法解析 SSE 事件:", data)
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""
        for (const line of lines) processLine(line)
      }

      buffer += decoder.decode()
      if (buffer.trim()) processLine(buffer)

      if (!doneReceived && !errorReceived) {
        callbacks.onError?.("流式连接意外中断，请重新发送；如果频繁出现，请检查模型服务或反向代理超时配置")
      }

    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // 用户主动取消
      } else {
        callbacks.onError?.(err instanceof Error ? err.message : '未知错误')
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
    }
  }

  function handleStreamEvent(data: Record<string, unknown>, cb: AgentStreamCallbacks): void {
    const type = data.type as string
    const content = (data.content as string) || ''
    const sessionId = data.session_id as string | undefined
    const messageId = data.message_id as string | undefined
    const isReasoning = data.is_reasoning as boolean | undefined

    switch (type) {
      case 'text':
        cb.onText?.(content, isReasoning)
        if (sessionId && messageId) cb.onSessionCreated?.(sessionId, messageId)
        break
      case 'tool_call':
        cb.onToolCall?.({
          tool_call_id: (data.tool_call_id as string) || '',
          tool_name: (data.tool_name as string) || '',
          arguments: (data.arguments as Record<string, unknown>) || {},
        })
        break
      case 'tool_result':
        cb.onToolResult?.({
          tool_call_id: (data.tool_call_id as string) || '',
          tool_name: (data.tool_name as string) || '',
          success: Boolean(data.success),
          result: data.result,
          ui_payload: (data.ui_payload as Record<string, unknown>) || undefined,
        })
        break
      case 'tool_output':
        cb.onToolOutput?.(
          (data.tool as string) || '',
          data.stream === 'stderr' ? 'stderr' : 'stdout',
          (data.data as string) || '',
          (data.tool_call_id as string) || undefined,
        )
        break
      case 'plan':
        cb.onPlan?.((Array.isArray(data.steps) ? data.steps : []) as StudioPlanStep[])
        break
      case 'error':
        cb.onError?.(content || '生成失败')
        break
      case 'done':
        {
          const usage = data.usage as TokenUsage | undefined
          cb.onDone?.(sessionId || '', messageId || '', usage)
        }
        break
    }
  }

  function abortStream(): void {
    abortController.value?.abort()
    isStreaming.value = false
  }

  return { isStreaming, streamChat, abortStream }
}
