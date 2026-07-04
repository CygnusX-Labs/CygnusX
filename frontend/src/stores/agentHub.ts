/**
 * 多智能体协作平台 Store — 真实后端联动版
 *
 * 资产（Agent / MCP / Skill）从后端 API 加载；会话客户端管理 + welcome_message 首屏；
 * 发消息走 Agent 调度中枢 SSE 流式（agent_id → 后端组装模型/系统词/MCP 工具 → 流式回）。
 *
 * 消息结构复用 @/components/ai-chat/types 的 ChatMessage，便于直接喂给
 * KimiMessageList / KimiChatInput 等已解耦的聊天组件。
 *
 * TODO: 在 Agent-first 架构稳定后，chatSession / chatAssistant 等模型优先 Store 应废弃，
 * chatStore 中与 UI 相关的设置（sidebarCollapsed / deepThinking / conversationSettings）
 * 可进一步收敛到独立的 uiSettingsStore，会话与智能体逻辑保留在 agentHub。
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { isToday, isYesterday, parseISO } from 'date-fns'
import type {
  AgentCategory,
  AgentTemplate,
  McpService,
  McpTool,
  SkillItem,
} from '@/types/agent'
import type { ChatMessage, ToolCall } from '@/components/ai-chat/types'
import { agentApi, adminAgentApi } from '@/api/agent'
import apiClient from '@/api/client'
import { useAgentChatStream } from '@/composables/useAgentChatStream'
import { useChatStore } from '@/stores/chat'

export const CATEGORY_LABELS: Record<AgentCategory, string> = {
  general: '通用',
  analysis: '分析',
  code: '编程',
  visualization: '可视化',
}

/** 前台会话（客户端管理，绑定 Agent） */
export interface AgentSession {
  id: string
  title: string
  agent_id: string
  messages: ChatMessage[]
  created_at: string
  updated_at: string
}

export const useAgentHubStore = defineStore('agentHub', () => {
  // ========== State ==========
  const mcps = ref<McpService[]>([])
  const skills = ref<SkillItem[]>([])
  const agents = ref<AgentTemplate[]>([])
  const sessions = ref<AgentSession[]>([])
  const currentSessionId = ref<string>('')

  const isStreaming = ref(false)
  const streamingContent = ref('')
  const streamingThought = ref('')

  const { streamChat, abortStream } = useAgentChatStream()

  /**
   * 临时会话 ID 解析锁。
   * Agent 工作流先创建客户端临时 `sess-` ID，等待 SSE 返回真实 session_id 后回填。
   * 该锁保证在回填完成前，后续消息不会携带临时 ID 重复触发后端创建多个会话。
   */
  let pendingSessionIdResolver: (() => void) | null = null
  let pendingSessionIdPromise: Promise<void> | null = null

  function createSessionIdLock(): Promise<void> {
    if (!pendingSessionIdPromise) {
      pendingSessionIdPromise = new Promise((resolve) => {
        pendingSessionIdResolver = resolve
      })
    }
    return pendingSessionIdPromise
  }

  function releaseSessionIdLock() {
    pendingSessionIdResolver?.()
    pendingSessionIdResolver = null
    pendingSessionIdPromise = null
  }

  // ========== Getters ==========
  const activeAgents = computed(() => agents.value.filter((a) => a.is_active))

  function getAgent(id: string): AgentTemplate | undefined {
    return agents.value.find((a) => a.id === id)
  }

  function mcpsByIds(ids: string[]): McpService[] {
    return ids.map((id) => mcps.value.find((m) => m.id === id)).filter(Boolean) as McpService[]
  }

  function skillsByIds(ids: string[]): SkillItem[] {
    return ids.map((id) => skills.value.find((s) => s.id === id)).filter(Boolean) as SkillItem[]
  }

  const currentSession = computed(
    () => sessions.value.find((s) => s.id === currentSessionId.value) || null,
  )

  const currentAgent = computed(() =>
    currentSession.value ? getAgent(currentSession.value.agent_id) : null,
  )

  /** 按 今天 / 昨天 / 更早 分组的历史会话 */
  const groupedSessions = computed(() => {
    const fit = (fn: (d: Date) => boolean) =>
      sessions.value.filter((s) => {
        try { return fn(parseISO(s.updated_at)) } catch { return false }
      })
    const groups: { label: string; sessions: AgentSession[] }[] = []
    const today = fit(isToday)
    const yesterday = fit(isYesterday)
    const older = fit((d) => !isToday(d) && !isYesterday(d))
    if (today.length) groups.push({ label: '今天', sessions: today })
    if (yesterday.length) groups.push({ label: '昨天', sessions: yesterday })
    if (older.length) groups.push({ label: '更早', sessions: older })
    return groups
  })

  // ========== 资产加载 ==========

  /** 加载启用中的 Agent 列表（前台集市） */
  async function fetchAgents(activeOnly = true): Promise<void> {
    try {
      agents.value = activeOnly ? await agentApi.list() : await adminAgentApi.list()
    } catch (e) {
      console.error('加载 Agent 列表失败:', e)
    }
  }

  /** 加载 MCP 服务列表（供表单 transfer / 能力预览） */
  async function fetchMcps(): Promise<void> {
    try {
      const res = await apiClient.get<any[]>('/mcp/servers')
      mcps.value = (res.data || []).map((m) => ({
        id: String(m.id),
        name: m.name,
        description: m.description ?? '',
        status: m.status === 'online' ? 'online' : 'offline',
        transport: m.transport ?? 'builtin',
        tools: m.tools ?? [],
        tool_count: m.tool_count ?? 0,
        is_preset: !!m.is_preset,
      }))
    } catch (e) {
      console.error('加载 MCP 列表失败:', e)
    }
  }

  /** 加载技能列表（供表单 transfer / 能力预览）
   *  all=false 走公开 /chat/skills（仅启用）；all=true 走 /admin/skills（含停用）
   */
  async function fetchSkills(all = false): Promise<void> {
    try {
      const url = all ? '/admin/skills' : '/chat/skills'
      const res = await apiClient.get<any[]>(url)
      skills.value = (res.data || []).map((s) => ({
        id: s.skill_id ?? String(s.id),
        name: s.name,
        description: s.description ?? '',
        icon: s.icon ?? '🔧',
        category: s.category ?? '通用',
        source: s.is_builtin ? 'builtin' : 'json',
        is_active: s.is_active ?? true,
      }))
    } catch (e) {
      console.error('加载技能列表失败:', e)
    }
  }

  /** 一次性初始化全部资产（前台页面挂载时调用） */
  async function initAssets(): Promise<void> {
    await Promise.all([fetchAgents(true), fetchMcps(), fetchSkills(false)])
  }

  // ========== 资产 Actions（后台 CRUD，调真实 API） ==========

  /** 切换 MCP 在线状态 */
  async function toggleMcpStatus(id: string) {
    const m = mcps.value.find((x) => x.id === id)
    if (!m) return
    const newStatus = m.status === 'online' ? 'offline' : 'online'
    try {
      await apiClient.put(`/mcp/servers/${id}`, { status: newStatus })
      m.status = newStatus
    } catch {
      m.status = newStatus
    }
  }

  async function addMcpServer(data: {
    name: string
    description?: string
    transport: string
    command?: string
    url?: string
    env?: Record<string, string>
    timeout?: number
  }): Promise<void> {
    await apiClient.post('/mcp/servers', data)
    await fetchMcps()
  }

  async function removeMcpServer(id: string): Promise<void> {
    await apiClient.delete(`/mcp/servers/${id}`)
    mcps.value = mcps.value.filter((m) => m.id !== id)
    agents.value.forEach((a) => {
      a.mcp_ids = a.mcp_ids.filter((mid) => mid !== id)
    })
  }

  async function testMcpServer(id: string): Promise<{ success: boolean; tool_count: number; error?: string }> {
    const res = await apiClient.post(`/mcp/servers/${id}/test`)
    return res.data
  }

  async function fetchMcpTools(id: string): Promise<McpTool[]> {
    const res = await apiClient.get<any[]>(`/mcp/servers/${id}/tools`)
    return (res.data || []).map((t: any) => ({
      name: t.name,
      description: t.description ?? '',
      input_schema: t.input_schema ?? {},
    }))
  }

  async function upsertAgent(dto: Partial<AgentTemplate> & { id?: string }): Promise<AgentTemplate | null> {
    try {
      let saved: AgentTemplate
      if (dto.id && agents.value.some((a) => a.id === dto.id)) {
        saved = await adminAgentApi.update(dto.id, dto)
      } else {
        saved = await adminAgentApi.create(dto)
      }
      await fetchAgents(false)
      return saved
    } catch (e) {
      console.error('保存 Agent 失败:', e)
      return null
    }
  }

  async function toggleAgent(id: string): Promise<void> {
    try {
      await adminAgentApi.toggle(id)
      await fetchAgents(false)
    } catch (e) {
      console.error('切换 Agent 状态失败:', e)
    }
  }

  async function deleteAgent(id: string): Promise<void> {
    try {
      await adminAgentApi.remove(id)
      await fetchAgents(false)
    } catch (e) {
      console.error('删除 Agent 失败:', e)
    }
  }

  // ========== 技能管理（后台 CRUD，调 /admin/skills） ==========

  /** URL 拉取导入（当前后端无 URL 抓取，落库为一条自定义技能记录） */
  async function importSkillFromUrl(url: string): Promise<void> {
    const skillId = `skill-url-${Date.now()}`
    await apiClient.post('/admin/skills', {
      skill_id: skillId,
      name: '自定义技能',
      description: `从 ${url} 拉取的技能配置`,
      icon: '🧩',
      category: '自定义',
      prompt: '',
      is_active: true,
    })
    await fetchSkills(true)
  }

  /** JSON 粘贴导入：解析 {name, description?, icon?, category?, prompt?} */
  async function importSkillFromJson(text: string): Promise<void> {
    let obj: Record<string, unknown>
    try {
      obj = JSON.parse(text)
    } catch {
      throw new Error('JSON 格式错误，请检查配置内容')
    }
    if (!obj.name) throw new Error('配置缺少必填字段 name')
    await apiClient.post('/admin/skills', {
      skill_id: `skill-json-${Date.now()}`,
      name: String(obj.name),
      description: String(obj.description ?? ''),
      icon: String(obj.icon ?? '🧩'),
      category: String(obj.category ?? '自定义'),
      prompt: String(obj.prompt ?? ''),
      is_active: true,
    })
    await fetchSkills(true)
  }

  async function toggleSkill(id: string): Promise<void> {
    try {
      await apiClient.post(`/admin/skills/${id}/toggle`)
      await fetchSkills(true)
    } catch (e) {
      console.error('切换技能状态失败:', e)
    }
  }

  async function deleteSkill(id: string): Promise<void> {
    try {
      await apiClient.delete(`/admin/skills/${id}`)
      await fetchSkills(true)
      // 同步解绑 Agent 上的引用（前端缓存）
      agents.value.forEach((a) => (a.skill_ids = a.skill_ids.filter((x) => x !== id)))
    } catch (e) {
      console.error('删除技能失败:', e)
    }
  }

  // ========== 会话编排 ==========

  function startSessionFromAgent(agentId: string): AgentSession | null {
    // 切换/新建会话时先中断当前流，避免资源浪费
    stopStreaming()
    const agent = getAgent(agentId)
    if (!agent) return null
    const now = new Date().toISOString()
    const session: AgentSession = {
      id: `sess-${Date.now()}`,
      title: agent.name,
      agent_id: agentId,
      messages: [
        {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: agent.welcome_message,
          createdAt: now,
        },
      ],
      created_at: now,
      updated_at: now,
    }
    sessions.value.unshift(session)
    currentSessionId.value = session.id
    return session
  }

  function selectSession(id: string) {
    if (currentSessionId.value !== id) stopStreaming()
    currentSessionId.value = id
  }

  function newChat() {
    stopStreaming()
    currentSessionId.value = ''
  }

  function deleteSession(id: string) {
    if (currentSessionId.value === id) stopStreaming()
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentSessionId.value === id) currentSessionId.value = ''
  }

  function renameSession(id: string, title: string) {
    const s = sessions.value.find((x) => x.id === id)
    if (s) s.title = title
  }

  /** 发送消息（真实 SSE 流式，走 Agent 调度中枢） */
  async function sendMessage(content: string): Promise<void> {
    const session = currentSession.value
    if (!session || isStreaming.value || !content.trim()) return
    const agent = getAgent(session.agent_id)
    if (!agent) return

    // 若当前临时会话 ID 正在解析为真实 ID，排队等待，防止创建重复会话
    if (session.id.startsWith('sess-') && pendingSessionIdPromise) {
      await pendingSessionIdPromise
    }

    const chatStore = useChatStore()
    const now = new Date().toISOString()

    // 用户消息
    session.messages.push({
      id: `msg-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      createdAt: now,
    })

    // 助手占位消息（流式填充）
    const aiId = `msg-ai-${Date.now()}`
    const aiMsg: ChatMessage = {
      id: aiId,
      role: 'assistant',
      content: '',
      toolCalls: [],
      createdAt: new Date().toISOString(),
    }
    session.messages.push(aiMsg)

    // 首条用户消息后自动生成标题
    if (session.title === agent.name) {
      const t = content.trim().slice(0, 24)
      session.title = t + (content.trim().length > 24 ? '...' : '')
    }

    // 构建送后端的上下文（含历史，排除当前 AI 占位）
    const ctxLen = chatStore.conversationSettings.contextLength ?? 20
    const apiMessages = session.messages
      .filter((m) => m.id !== aiId && m.role !== 'assistant' || (m.role === 'assistant' && m.content.length > 0))
      .slice(-ctxLen)
      .map((m) => ({ role: m.role, content: m.content }))

    isStreaming.value = true
    streamingContent.value = ''
    streamingThought.value = ''

    // 是否已有真实后端 session_id（首次为空，后端创建后回填）
    let backendSessionId: string | undefined
    if (session.id.startsWith('sess-') === false) backendSessionId = session.id

    // 新会话首次发消息时加锁，直到 onSessionCreated 回填真实 ID
    if (session.id.startsWith('sess-')) createSessionIdLock()

    await streamChat(
      {
        agentId: agent.id,
        messages: apiMessages,
        sessionId: backendSessionId,
        temperature: chatStore.conversationSettings.temperature,
        maxTokens: chatStore.conversationSettings.maxTokens,
        deepThinking: chatStore.deepThinking,
      },
      {
        onText: (text, isReasoning) => {
          if (isReasoning) {
            streamingThought.value += text
          } else {
            streamingContent.value += text
          }
          session.updated_at = new Date().toISOString()
        },
        onSessionCreated: (sessionId) => {
          // 后端首次创建会话 → 回填真实 session_id
          if (session.id.startsWith('sess-')) {
            session.id = sessionId
            currentSessionId.value = sessionId
            releaseSessionIdLock()
          }
        },
        onToolCall: (event) => {
          if (!aiMsg.toolCalls) aiMsg.toolCalls = []
          aiMsg.toolCalls.push({
            id: event.tool_call_id || `tc-${Date.now()}`,
            name: event.tool_name,
            arguments: event.arguments,
            status: 'running',
          })
        },
        onToolResult: (event) => {
          const tc = (aiMsg.toolCalls || []).find((t) => t.id === event.tool_call_id)
          if (tc) {
            tc.result = event.result
            tc.status = event.success ? 'success' : 'error'
          }
        },
        onError: (error) => {
          aiMsg.content = streamingContent.value || `生成失败: ${error}`
          aiMsg.toolCalls = (aiMsg.toolCalls || []).map((t) =>
            t.status === 'running' ? { ...t, status: 'error' as const } : t,
          )
          isStreaming.value = false
          streamingContent.value = ''
          streamingThought.value = ''
          releaseSessionIdLock()
        },
        onDone: () => {
          aiMsg.content = streamingContent.value || aiMsg.content
          isStreaming.value = false
          streamingContent.value = ''
          streamingThought.value = ''
          releaseSessionIdLock()
        },
      },
    )

    // 兜底：若流异常中断未触发 onDone/onError
    isStreaming.value = false
    streamingContent.value = ''
    streamingThought.value = ''
    releaseSessionIdLock()
  }

  function stopStreaming() {
    abortStream()
    const session = currentSession.value
    if (session) {
      const last = session.messages[session.messages.length - 1]
      if (last && last.role === 'assistant') {
        last.content = streamingContent.value || last.content || '（已停止）'
      }
    }
    isStreaming.value = false
    streamingContent.value = ''
    streamingThought.value = ''
    releaseSessionIdLock()
  }

  return {
    // state
    mcps, skills, agents, sessions, currentSessionId,
    isStreaming, streamingContent, streamingThought,
    // getters
    activeAgents, currentSession, currentAgent, groupedSessions,
    // lookups
    getAgent, mcpsByIds, skillsByIds,
    // asset actions
    fetchAgents, fetchMcps, fetchSkills, initAssets,
    toggleMcpStatus, addMcpServer, removeMcpServer, testMcpServer, fetchMcpTools,
    upsertAgent, toggleAgent, deleteAgent,
    importSkillFromUrl, importSkillFromJson, toggleSkill, deleteSkill,
    // session actions
    startSessionFromAgent, selectSession, newChat, deleteSession, renameSession,
    sendMessage, stopStreaming,
  }
})
