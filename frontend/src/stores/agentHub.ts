/**
 * 多智能体协作平台 Store — 真实后端联动版
 *
 * 资产（Agent / MCP / Skill）从后端 API 加载；会话客户端管理 + welcome_message 首屏；
 * 发消息走 Agent 调度中枢 SSE 流式（agent_id → 后端组装模型/系统词/MCP 工具 → 流式回）。
 *
 * 消息结构复用 @/components/ai-chat/types 的 ChatMessage，便于直接喂给
 * KimiMessageList / KimiChatInput 等已解耦的聊天组件。
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { isToday, isYesterday, parseISO } from 'date-fns'
import type {
  AgentCategory,
  AgentTemplate,
  McpService,
  SkillItem,
} from '@/types/agent'
import type { ChatMessage, ToolCall } from '@/components/ai-chat/types'
import { agentApi, adminAgentApi } from '@/api/agent'
import apiClient from '@/api/client'
import { useAgentChatStream } from '@/composables/useAgentChatStream'

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

  // 流式状态
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const streamingThought = ref('')

  const { streamChat, abortStream } = useAgentChatStream()

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
      const res = await apiClient.get<any[]>('/mcp')
      mcps.value = (res.data || []).map((m) => ({
        id: String(m.id),
        name: m.name,
        description: m.description ?? '',
        status: m.status === 'online' ? 'online' : 'offline',
        transport: m.transport ?? 'builtin',
        tools: m.tools ?? [],
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

  /** 切换 MCP 在线状态（前端仅展示，真实状态由后端探测） */
  function toggleMcpStatus(id: string) {
    const m = mcps.value.find((x) => x.id === id)
    if (m) m.status = m.status === 'online' ? 'offline' : 'online'
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
    currentSessionId.value = id
  }

  function newChat() {
    currentSessionId.value = ''
  }

  function deleteSession(id: string) {
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
    const ctxLen = 20
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

    await streamChat(
      {
        agentId: agent.id,
        messages: apiMessages,
        sessionId: backendSessionId,
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
        },
        onDone: () => {
          aiMsg.content = streamingContent.value || aiMsg.content
          isStreaming.value = false
          streamingContent.value = ''
          streamingThought.value = ''
        },
      },
    )

    // 兜底：若流异常中断未触发 onDone/onError
    isStreaming.value = false
    streamingContent.value = ''
    streamingThought.value = ''
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
    toggleMcpStatus, upsertAgent, toggleAgent, deleteAgent,
    importSkillFromUrl, importSkillFromJson, toggleSkill, deleteSkill,
    // session actions
    startSessionFromAgent, selectSession, newChat, deleteSession, renameSession,
    sendMessage, stopStreaming,
  }
})
