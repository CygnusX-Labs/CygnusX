/**
 * useAgentChatStream — Agent 调度中枢的 SSE 流式聊天 Composable
 *
 * 基于 fetch + ReadableStream 解析 Server-Sent Events。
 * 与 useChatStream 的区别：
 *  - payload 用 agent_id（走后端 Agent 编排闭环）
 *  - 解析 tool_call / tool_result 事件，供前端渲染工具调用气泡
 */
import { ref } from 'vue'
import { reportChatDiagnostic } from '@/utils/chatDiagnostics'

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
  mcpMode?: 'off' | 'auto' | 'manual'
  extraMcpServers?: string[]
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

/** Studio HITL：审批请求事件（supervised 模式下受控工具挂起等待用户决议） */
export interface ApprovalRequestEvent {
  approval_id: string
  tool_call_id: string
  tool_name: string
  arguments: Record<string, unknown>
  risk_hint?: string
  timeout_seconds?: number
}

export type ApprovalAction = 'approved' | 'edited' | 'rejected' | 'timeout'

/** Studio HITL：审批决议事件（批准后工具照常执行，随后有正常 tool_output/tool_result） */
export interface ApprovalResolvedEvent {
  approval_id: string
  tool_call_id: string
  action: ApprovalAction
}

/** Studio HITL：ask_user 澄清请求（本轮随后结束，用户在下一条消息回答） */
export interface AskRequestEvent {
  tool_call_id: string
  question: string
  options?: string[]
}

/** 智能路由：route 事件（路由器 Agent 分派目标专家后、正文开始前推送） */
export interface RouteEvent {
  agent_id: string
  name: string
  avatar: string
  color: string
  reason: string
}

/** 同一会话内 Agent 交接事件。完整摘要仍由同名工具结果卡片保存和渲染。 */
export interface HandoffEvent {
  source_agent_id: string
  source_agent_name?: string
  target_agent_id: string
  target_agent_name?: string
  reason: string
  handoff_summary?: string
  user_intent?: string
  artifacts?: string[]
  constraints?: string[]
  hop_index: number
}

export interface ConsultationEvent {
  experts: Array<{ agent_id: string; name: string; opinion: string }>
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

export interface WebSearchEvent {
  query: string
  status: 'searching' | 'empty' | 'failed' | 'complete'
  message?: string
}

export interface WebSearchSource {
  title: string
  url: string
  snippet: string
  publishedAt?: string | null
}

export interface AgentStreamCallbacks {
  onText?: (text: string, isReasoning?: boolean) => void
  onSessionCreated?: (sessionId: string, messageId: string) => void
  onToolCall?: (event: ToolCallEvent) => void
  onToolResult?: (event: ToolResultEvent) => void
  onWebSearch?: (event: WebSearchEvent) => void
  onWebSearchResults?: (sources: WebSearchSource[]) => void
  /**
   * Studio 工具执行过程中的 stdout/stderr 增量输出
   * （sandbox_execute 边跑边推；Studio 工具事件带 tool_call_id，旧事件可能仅带工具名）
   */
  onToolOutput?: (tool: string, stream: 'stdout' | 'stderr', data: string, toolCallId?: string) => void
  onPlan?: (steps: StudioPlanStep[]) => void
  onApprovalRequest?: (event: ApprovalRequestEvent) => void
  onApprovalResolved?: (event: ApprovalResolvedEvent) => void
  onAskRequest?: (event: AskRequestEvent) => void
  onRoute?: (event: RouteEvent) => void
  onHandoff?: (event: HandoffEvent) => void
  onConsultation?: (event: ConsultationEvent) => void
  onError?: (error: string) => void
  onDone?: (
    sessionId: string,
    messageId: string,
    usage?: TokenUsage,
    finishReason?: string,
    finalContent?: string,
    finalReasoning?: string,
  ) => void
}

export interface NormalizedAgentStreamEvent {
  type: string
  content: string
  reasoning: string
  isReasoning: boolean
  sessionId?: string
  messageId?: string
  raw: Record<string, unknown>
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.length > 0) return value
  }
  return ''
}

export function normalizeAgentStreamEvent(data: Record<string, unknown>): NormalizedAgentStreamEvent {
  const nestedData = asRecord(data.data)
  const delta = asRecord(data.delta) || asRecord(nestedData?.delta)
  const message = asRecord(data.message) || asRecord(nestedData?.message)
  const firstChoice = Array.isArray(data.choices) ? asRecord(data.choices[0]) : undefined
  const choiceDelta = asRecord(firstChoice?.delta)
  const choiceMessage = asRecord(firstChoice?.message)

  const reasoning = firstString(
    data.reasoning_content,
    data.reasoning,
    nestedData?.reasoning_content,
    nestedData?.reasoning,
    delta?.reasoning_content,
    delta?.reasoning,
    message?.reasoning_content,
    choiceDelta?.reasoning_content,
    choiceDelta?.reasoning,
    choiceMessage?.reasoning_content,
  )
  const content = firstString(
    data.content,
    data.text,
    data.answer,
    typeof data.delta === 'string' ? data.delta : undefined,
    nestedData?.content,
    nestedData?.text,
    nestedData?.answer,
    delta?.content,
    delta?.text,
    delta?.answer,
    message?.content,
    message?.text,
    message?.answer,
    choiceDelta?.content,
    choiceDelta?.text,
    choiceMessage?.content,
    firstChoice?.text,
  )
  const declaredType = firstString(data.type, data.event, nestedData?.type)
  const isReasoning = Boolean(data.is_reasoning)
    || declaredType === 'reasoning'
    || (!!reasoning && !content)
  const type = declaredType || (content || reasoning ? 'text' : '')

  return {
    type,
    content,
    reasoning,
    isReasoning,
    sessionId: firstString(data.session_id, data.sessionId, nestedData?.session_id) || undefined,
    messageId: firstString(data.message_id, data.messageId, nestedData?.message_id) || undefined,
    raw: data,
  }
}

export function useAgentChatStream() {
  const isStreaming = ref(false)
  const isPaused = ref(false)
  const abortController = ref<AbortController | null>(null)

  async function streamChat(
    options: AgentChatStreamOptions,
    callbacks: AgentStreamCallbacks,
  ): Promise<void> {
    if (isStreaming.value) return
    isStreaming.value = true
    isPaused.value = false
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
          mcp_mode: options.mcpMode || 'auto',
          extra_mcp_servers: options.extraMcpServers || [],
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
          const parsed = JSON.parse(data) as Record<string, unknown>
          const normalized = normalizeAgentStreamEvent(parsed)
          handleStreamEvent(normalized, callbacks)
          if (normalized.type === 'done') doneReceived = true
          if (normalized.type === 'error') errorReceived = true
        } catch (error) {
          reportChatDiagnostic({
            phase: 'stream-parse',
            rawResponseSummary: data.slice(0, 1000),
            error,
          })
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

  function handleStreamEvent(event: NormalizedAgentStreamEvent, cb: AgentStreamCallbacks): void {
    const data = event.raw
    const { type, content, reasoning, sessionId, messageId, isReasoning } = event

    switch (type) {
      case 'text':
      case 'content':
      case 'message':
      case 'delta':
      case 'reasoning':
        cb.onText?.(isReasoning ? reasoning || content : content, isReasoning)
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
      case 'web_search':
        cb.onWebSearch?.({
          query: content,
          status: (data.status as WebSearchEvent['status']) || 'searching',
          message: typeof data.message === 'string' ? data.message : undefined,
        })
        break
      case 'web_search_results':
        cb.onWebSearchResults?.(
          (Array.isArray(data.sources) ? data.sources : [])
            .filter((source): source is Record<string, unknown> => !!source && typeof source === 'object')
            .filter((source) => typeof source.title === 'string' && typeof source.url === 'string')
            .map((source) => ({
              title: source.title as string,
              url: source.url as string,
              snippet: typeof source.snippet === 'string' ? source.snippet : '',
              publishedAt: typeof source.publishedAt === 'string' ? source.publishedAt : null,
            })),
        )
        break
      case 'handoff':
        cb.onHandoff?.({
          source_agent_id: (data.source_agent_id as string) || '',
          source_agent_name: typeof data.source_agent_name === 'string' ? data.source_agent_name : undefined,
          target_agent_id: (data.target_agent_id as string) || '',
          target_agent_name: typeof data.target_agent_name === 'string' ? data.target_agent_name : undefined,
          reason: (data.reason as string) || '',
          handoff_summary: typeof data.handoff_summary === 'string' ? data.handoff_summary : undefined,
          user_intent: typeof data.user_intent === 'string' ? data.user_intent : undefined,
          artifacts: Array.isArray(data.artifacts) ? data.artifacts.filter((item): item is string => typeof item === 'string') : [],
          constraints: Array.isArray(data.constraints) ? data.constraints.filter((item): item is string => typeof item === 'string') : [],
          hop_index: Number(data.hop_index) || 1,
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
      case 'approval_request':
        cb.onApprovalRequest?.({
          approval_id: (data.approval_id as string) || '',
          tool_call_id: (data.tool_call_id as string) || '',
          tool_name: (data.tool_name as string) || '',
          arguments: (data.arguments as Record<string, unknown>) || {},
          risk_hint: (data.risk_hint as string) || undefined,
          timeout_seconds: (data.timeout_seconds as number) || undefined,
        })
        break
      case 'approval_resolved':
        cb.onApprovalResolved?.({
          approval_id: (data.approval_id as string) || '',
          tool_call_id: (data.tool_call_id as string) || '',
          action: ((data.action as string) || 'approved') as ApprovalAction,
        })
        break
      case 'ask_request':
        cb.onAskRequest?.({
          tool_call_id: (data.tool_call_id as string) || '',
          question: (data.question as string) || content,
          options: Array.isArray(data.options) ? (data.options as string[]) : undefined,
        })
        break
      case 'route':
        cb.onRoute?.({
          agent_id: (data.agent_id as string) || '',
          name: (data.name as string) || '',
          avatar: (data.avatar as string) || '',
          color: (data.color as string) || '',
          reason: (data.reason as string) || '',
        })
        break
      case 'consultation':
        cb.onConsultation?.({
          experts: Array.isArray(data.experts)
            ? data.experts
                .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
                .map((item) => ({
                  agent_id: typeof item.agent_id === 'string' ? item.agent_id : '',
                  name: typeof item.name === 'string' ? item.name : '专家',
                  opinion: typeof item.opinion === 'string' ? item.opinion : '',
                }))
            : [],
        })
        break
      case 'error':
        cb.onError?.(content || '生成失败')
        break
      case 'done':
        {
          if (sessionId && messageId) cb.onSessionCreated?.(sessionId, messageId)
          const usage = data.usage as TokenUsage | undefined
          const finishReason = data.finish_reason as string | undefined
          cb.onDone?.(
            sessionId || '',
            messageId || '',
            usage,
            finishReason,
            content,
            reasoning,
          )
        }
        break
    }
  }

  function abortStream(): void {
    abortController.value?.abort()
    isStreaming.value = false
    isPaused.value = false
  }

  /** 暂停流式输出：中断连接但保留已输出文本，标记为暂停态 */
  function pauseStream(): void {
    abortController.value?.abort()
    isStreaming.value = false
    isPaused.value = true
  }

  /** 重置暂停状态（重新生成前调用） */
  function resetPause(): void {
    isPaused.value = false
  }

  return { isStreaming, isPaused, streamChat, abortStream, pauseStream, resetPause }
}
