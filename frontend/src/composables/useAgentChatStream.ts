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
  /** 温度（0-1），后端 Agent 编排层可透传给底层模型 */
  temperature?: number
  /** 单次回复最大 token 数 */
  maxTokens?: number
  /** 是否开启深度思考/推理模式 */
  deepThinking?: boolean
}

export interface ToolCallEvent {
  tool_call_id: string
  tool_name: string
  arguments: Record<string, unknown>
}
export interface ToolResultEvent {
  tool_call_id: string
  tool_name: string
  success: boolean
  result: unknown
}

export interface AgentStreamCallbacks {
  onText?: (text: string, isReasoning?: boolean) => void
  onSessionCreated?: (sessionId: string, messageId: string) => void
  onToolCall?: (event: ToolCallEvent) => void
  onToolResult?: (event: ToolResultEvent) => void
  onError?: (error: string) => void
  onDone?: (sessionId: string, messageId: string) => void
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
          messages: options.messages,
          stream: true,
          temperature: options.temperature,
          max_tokens: options.maxTokens,
          deep_thinking: options.deepThinking,
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

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue
          const data = trimmed.slice(6)
          try {
            handleStreamEvent(JSON.parse(data), callbacks)
          } catch {
            /* 忽略不完整 JSON */
          }
        }
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
        })
        break
      case 'error':
        cb.onError?.(content || '生成失败')
        break
      case 'done':
        if (sessionId && messageId) cb.onDone?.(sessionId, messageId)
        break
    }
  }

  function abortStream(): void {
    abortController.value?.abort()
    isStreaming.value = false
  }

  return { isStreaming, streamChat, abortStream }
}
