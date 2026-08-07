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
  messages: { role: string; content: string; metadata?: Record<string, unknown> }[]
  sessionId?: string
  /** 当前会话运行模式；Studio 模式会由后端装配工作区工具与上下文。 */
  mode?: 'chat' | 'studio'
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
  /** 当前会话是否启用 multi-agent 协作运行时 */
  multiAgent?: boolean
  overdrive?: boolean
  /** 工具调用轮次上限扩展：true 时后端按 1000 轮执行（用户在触顶弹窗确认继续后置位） */
  extendMaxRounds?: boolean
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
  /** 多问题列表（优先）；兼容后端平铺的 question/options 单问题字段 */
  questions?: Array<{ question: string; options?: string[] }>
  question?: string
  options?: string[]
}

/** 智能路由：route 事件（路由器 Agent 分派目标专家后、正文开始前推送） */
export interface RouteEvent {
  agent_id: string
  name: string
  avatar: string
  color: string
  reason: string
  intent?: string
  confidence?: number
  transition?: {
    visible: boolean
    stage: 'specialist_intake' | 'execution_ready'
    title: string
    message: string
    next_step: string
    requires_execution_confirmation: boolean
    auto_start: boolean
  }
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
  consultation_id?: string
  consultation_summary?: string
  case_available?: boolean
}

export interface CollaborationRouteEvent {
  intent: 'transfer' | 'fanout' | 'consult' | 'case' | 'dag' | 'chat'
  label: string
  reason: string
  confidence: number
  available: boolean
  degraded: boolean
  message: string
}

export interface AgentTeamsCaseEvent {
  phase: 'created' | 'status_changed'
  case_id: string
  title: string
  status: string
  next_actor: string
  case_url: string
  session_id?: string
  message_id?: string
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

export interface RoomSpeechEvent {
  sender: { agent_id: string; name: string; avatar?: string; color?: string; role: 'manager' | 'worker' }
  content: string
  round: number
  messageId?: string
  sessionId?: string
  workerKey?: string
  isReasoning?: boolean
  thought?: string
  summary?: string
  artifacts?: Record<string, string>
  taskStatus?: string
  errorSummary?: string
}

export interface OverdriveProgressEvent {
  phase: 'manager_ready' | 'workers_starting' | 'worker_running' | 'tool_running' | 'worker_finished' | 'peer_reviewing' | 'summarizing' | 'awaiting_input' | 'paused' | 'completed'
  label: string
  completed: number
  total: number
  wave?: number
  waveTotal?: number
  waveMode?: 'parallel' | 'serial'
  fallback?: boolean
  warning?: string
  stalledTaskId?: string
  tasks?: Array<{ taskId: string; agentId: string; status: string; errorSummary?: string }>
}

export interface OverdriveApprovalEvent {
  approval: {
    approval_id: string
    tool_name: string
    arguments: Record<string, unknown>
    status: 'pending' | 'executing' | 'completed' | 'rejected' | 'failed'
    result?: Record<string, unknown>
    error?: string
    reason?: string
  }
  workerKey?: string
  agentId?: string
}

/** Skill 调用生命周期事件（skill.invoked / skill.completed / skill.failed 三时机） */
export interface SkillStreamEvent {
  /** invoked=技能被匹配加载；completed=加载成功；failed=加载失败/技能不可用 */
  phase: 'invoked' | 'completed' | 'failed'
  tool_call_id: string
  message_id?: string
  skill_id: string
  name: string
  version: string
  source: string
  icon: string
  agent?: string
  duration_ms?: number
  summary?: string
  error?: string
}

export interface WebSearchSource {
  title: string
  url: string
  snippet: string
  publishedAt?: string | null
}

export interface RoundLimitEvent {
  sessionId: string
  messageId: string
  maxRounds: number
  canExtend: boolean
}

export interface AgentStreamCallbacks {
  onText?: (text: string, isReasoning?: boolean) => void
  onSessionCreated?: (sessionId: string, messageId: string) => void
  onToolCall?: (event: ToolCallEvent) => void
  onToolResult?: (event: ToolResultEvent) => void
  /** Skill 调用生命周期（invoked/completed/failed），驱动会话流内技能调用卡片 */
  onSkill?: (event: SkillStreamEvent) => void
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
  onCollaborationRoute?: (event: CollaborationRouteEvent) => void
  onAgentTeamsCase?: (event: AgentTeamsCaseEvent) => void
  /** 工具调用轮次触顶：can_extend 为 true 时可由用户确认后以扩展上限继续 */
  onRoundLimit?: (event: RoundLimitEvent) => void
  /** 上下文超窗触发历史压缩时回调（estimatedTokens 为压缩前估算值） */
  onContextCompressed?: (estimatedTokens: number) => void
  onRoomSpeech?: (event: RoomSpeechEvent) => void
  onRoomSpeechDelta?: (event: RoomSpeechEvent) => void
  onOverdriveProgress?: (event: OverdriveProgressEvent) => void
  onOverdriveApproval?: (event: OverdriveApprovalEvent) => void
  onModeChanged?: (enabled: boolean, degraded?: boolean) => void
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
  metadata?: Record<string, unknown>
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
    metadata: asRecord(data.metadata) || nestedData,
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
          mode: options.mode,
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
          multi_agent: options.multiAgent ?? false,
          overdrive: options.overdrive,
          extend_max_rounds: options.extendMaxRounds || false,
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
      case 'mode_changed':
        if (data.mode === 'overdrive') cb.onModeChanged?.(Boolean(data.enabled), Boolean(data.degraded))
        break
      case 'room_speech': {
        const sender = asRecord(data.sender)
        if (!sender) break
        cb.onRoomSpeech?.({
          sender: {
            agent_id: String(sender.agent_id || ''),
            name: String(sender.name || '专家'),
            avatar: typeof sender.avatar === 'string' ? sender.avatar : undefined,
            color: typeof sender.color === 'string' ? sender.color : undefined,
            role: sender.role === 'worker' ? 'worker' : 'manager',
          },
          content,
          round: Number(data.round) || 1,
          messageId,
          sessionId,
          workerKey: typeof data.worker_key === 'string' ? data.worker_key : undefined,
          thought: typeof data.thought === 'string' ? data.thought : undefined,
          summary: typeof data.summary === 'string' ? data.summary : undefined,
          artifacts: (asRecord(data.artifacts) || undefined) as Record<string, string> | undefined,
          taskStatus: typeof data.task_status === 'string' ? data.task_status : undefined,
          errorSummary: typeof data.error_summary === 'string' ? data.error_summary : undefined,
        })
        if (sessionId && messageId) cb.onSessionCreated?.(sessionId, messageId)
        break
      }
      case 'room_speech_delta': {
        const sender = asRecord(data.sender)
        if (!sender) break
        cb.onRoomSpeechDelta?.({
          sender: {
            agent_id: String(sender.agent_id || ''),
            name: String(sender.name || '专家'),
            avatar: typeof sender.avatar === 'string' ? sender.avatar : undefined,
            color: typeof sender.color === 'string' ? sender.color : undefined,
            role: sender.role === 'worker' ? 'worker' : 'manager',
          },
          content,
          round: Number(data.round) || 1,
          sessionId,
          workerKey: typeof data.worker_key === 'string' ? data.worker_key : undefined,
          isReasoning: Boolean(data.is_reasoning),
        })
        break
      }
      case 'overdrive_progress': {
        const rawTasks = Array.isArray(data.tasks) ? data.tasks : []
        cb.onOverdriveProgress?.({
          phase: String(data.phase || 'worker_running') as OverdriveProgressEvent['phase'],
          label: String(data.label || '超频协作进行中'),
          completed: Number(data.completed || 0),
          total: Number(data.total || 0),
          wave: Number(data.wave) || undefined,
          waveTotal: Number(data.wave_total) || undefined,
          waveMode: data.wave_mode === 'parallel' ? 'parallel' : data.wave_mode === 'serial' ? 'serial' : undefined,
          tasks: rawTasks.map((raw) => {
            const task = asRecord(raw) || {}
            return {
              taskId: String(task.task_id || ''),
              agentId: String(task.agent_id || ''),
              status: String(task.status || 'pending'),
              errorSummary: typeof task.error_summary === 'string' ? task.error_summary : undefined,
            }
          }),
        })
        break
      }
      case 'schedule_fallback':
        cb.onOverdriveProgress?.({ phase: 'workers_starting', label: String(data.label || '已使用默认分工'), completed: 0, total: 0, fallback: true })
        break
      case 'schedule_warning':
        cb.onOverdriveProgress?.({ phase: 'workers_starting', label: String(data.label || '调度已降级'), completed: 0, total: 0, warning: String(data.label || '') })
        break
      case 'worker_stalled':
        cb.onOverdriveProgress?.({ phase: 'worker_running', label: String(data.label || '任务长时间无新进度'), completed: 0, total: 0, stalledTaskId: String(data.task_id || '') })
        break
      case 'overdrive_approval_request': {
        const approval = asRecord(data.approval)
        if (!approval || typeof approval.approval_id !== 'string' || typeof approval.tool_name !== 'string') break
        cb.onOverdriveApproval?.({
          approval: {
            approval_id: approval.approval_id,
            tool_name: approval.tool_name,
            arguments: (asRecord(approval.arguments) || {}) as Record<string, unknown>,
            status: String(approval.status || 'pending') as OverdriveApprovalEvent['approval']['status'],
            result: asRecord(approval.result),
            error: typeof approval.error === 'string' ? approval.error : undefined,
            reason: typeof approval.reason === 'string' ? approval.reason : undefined,
          },
          workerKey: typeof data.worker_key === 'string' ? data.worker_key : undefined,
          agentId: typeof data.agent_id === 'string' ? data.agent_id : undefined,
        })
        break
      }
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
      case 'agentteams_case':
        cb.onAgentTeamsCase?.({
          phase: data.phase === 'status_changed' ? 'status_changed' : 'created',
          case_id: (data.case_id as string) || '',
          title: (data.title as string) || '协作 Case',
          status: (data.status as string) || 'received',
          next_actor: (data.next_actor as string) || '协作团队',
          case_url: (data.case_url as string) || '',
          session_id: typeof data.session_id === 'string' ? data.session_id : undefined,
          message_id: typeof data.message_id === 'string' ? data.message_id : undefined,
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
      case 'skill':
        {
          const phase = data.phase === 'completed' || data.phase === 'failed' ? data.phase : 'invoked'
          cb.onSkill?.({
            phase,
            tool_call_id: (data.tool_call_id as string) || '',
            message_id: typeof data.message_id === 'string' ? data.message_id : undefined,
            skill_id: (data.skill_id as string) || '',
            name: (data.name as string) || '',
            version: (data.version as string) || '',
            source: (data.source as string) || '',
            icon: (data.icon as string) || '🧩',
            agent: typeof data.agent === 'string' ? data.agent : undefined,
            duration_ms: typeof data.duration_ms === 'number' ? data.duration_ms : undefined,
            summary: typeof data.summary === 'string' ? data.summary : undefined,
            error: typeof data.error === 'string' ? data.error : undefined,
          })
        }
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
        {
          const rawQuestions = Array.isArray(data.questions) ? data.questions : []
          const questions = rawQuestions
            .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
            .map((item) => ({
              question: typeof item.question === 'string' ? item.question : '',
              options: Array.isArray(item.options) ? (item.options as string[]) : undefined,
            }))
          // 兼容旧后端：无 questions 数组时退回平铺的 question/options
          if (!questions.length) {
            const single = (data.question as string) || content
            if (single) {
              questions.push({
                question: single,
                options: Array.isArray(data.options) ? (data.options as string[]) : undefined,
              })
            }
          }
          // 兜底一个空问题：卡片渲染自由输入，保证用户总能回复、已回答摘要不会空白
          if (!questions.length) {
            questions.push({ question: '', options: undefined })
          }
          cb.onAskRequest?.({
            tool_call_id: (data.tool_call_id as string) || '',
            questions,
          })
        }
        break
      case 'route': {
        const transition = asRecord(data.transition)
        cb.onRoute?.({
          agent_id: (data.agent_id as string) || '',
          name: (data.name as string) || '',
          avatar: (data.avatar as string) || '',
          color: (data.color as string) || '',
          reason: (data.reason as string) || '',
          intent: typeof data.intent === 'string' ? data.intent : undefined,
          confidence: typeof data.confidence === 'number' ? data.confidence : undefined,
          transition: transition
            ? {
                visible: Boolean(transition.visible),
                stage:
                  transition.stage === 'execution_ready'
                    ? 'execution_ready'
                    : 'specialist_intake',
                title: String(transition.title || '已匹配专项专家'),
                message: String(transition.message || ''),
                next_step: String(transition.next_step || '专项 Agent 进行任务 intake'),
                requires_execution_confirmation: Boolean(transition.requires_execution_confirmation),
                auto_start: Boolean(transition.auto_start),
              }
            : undefined,
        })
        break
      }
      case 'round_limit':
        cb.onRoundLimit?.({
          sessionId: sessionId || '',
          messageId: messageId || '',
          maxRounds: Number(data.max_rounds) || 0,
          canExtend: Boolean(data.can_extend),
        })
        break
      case 'context_compressed':
        cb.onContextCompressed?.(Number(data.estimated_tokens_before) || 0)
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
          consultation_id: typeof data.consultation_id === 'string' ? data.consultation_id : undefined,
          consultation_summary: typeof data.consultation_summary === 'string' ? data.consultation_summary : undefined,
          case_available: typeof data.case_available === 'boolean' ? data.case_available : undefined,
        })
        break
      case 'collaboration_route':
        cb.onCollaborationRoute?.({
          intent: ((data.intent as CollaborationRouteEvent['intent']) || 'chat'),
          label: (data.label as string) || '协作路径',
          reason: (data.reason as string) || '',
          confidence: Number(data.confidence) || 0,
          available: Boolean(data.available),
          degraded: Boolean(data.degraded),
          message: (data.message as string) || '',
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
