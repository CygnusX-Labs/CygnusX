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
  McpLogEntry,
  McpService,
  McpTool,
  SkillItem,
} from '@/types/agent'
import type {
  SkillImportPreview,
  SkillMarketplaceItem,
  SkillUpdateCheck,
} from '@/types/skill'
import type { ChatMessage, ToolCall, FileAttachment, ChartData } from '@/components/ai-chat/types'
import { agentApi, adminAgentApi } from '@/api/agent'
import apiClient from '@/api/client'
import { reportChatDiagnostic } from '@/utils/chatDiagnostics'
import {
  useAgentChatStream,
  type StudioPlanStep,
  type TokenUsage,
} from '@/composables/useAgentChatStream'
import { studioApi, type StudioPermissionMode } from '@/api/studio'
import { useChatStore } from '@/stores/chat'
import type {
  PipelineSubmitResult,
  PipelineTask,
  PipelineTaskStatus,
  PipelineType,
} from '@/types/pipeline'

const STUDIO_OUTPUT_CAP = 20_000

function appendBoundedStudioOutput(current: string, data: string): string {
  const combined = current + data
  if (combined.length <= STUDIO_OUTPUT_CAP) return combined
  return `…\n${combined.slice(-(STUDIO_OUTPUT_CAP - 2))}`
}

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
  title_locked?: boolean
  agent_id: string
  mode?: 'chat' | 'studio'
  messages: ChatMessage[]
  created_at: string
  updated_at: string
  /** 当前会话使用的模型配置 ID（覆盖 Agent 默认模型） */
  model_id?: string
  mcp_mode?: 'off' | 'auto' | 'manual'
  extra_mcp_servers?: string[]
}

/** 可用模型选项（来自 /api/v1/chat/models） */
export interface AvailableModel {
  id: string
  name: string
  model: string
  provider_type: string
  is_default: boolean
  temperature?: number
  max_tokens?: number
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
  /** 助手回复要求用户提供数据时置位（以 📤 需要您提供数据 开头），聊天界面据此弹窗提醒 */
  const dataRequestNotice = ref<{ sessionId: string; text: string } | null>(null)
  /** 工具调用轮次触顶时置位，聊天界面据此弹窗询问是否以扩展上限（1000 轮）继续 */
  const roundLimitPrompt = ref<{ sessionId: string; maxRounds: number } | null>(null)
  /** 上下文超窗触发历史压缩时置位（值为压缩前估算 token），聊天界面据此提示 */
  const contextCompressedNotice = ref<number | null>(null)
  /** 路由/交接命中 default_mode=studio 的 Agent 时置位，聊天界面据此自动跳转 AI 工作台 */
  const studioRedirect = ref<{ agentId: string; agentName: string } | null>(null)

  /** 目标 Agent 声明默认工作台模式且当前是普通聊天会话时，发起工作台跳转 */
  function maybeRedirectToStudio(agentId: string, agentName: string): void {
    const session = currentSession.value
    if (!session || session.mode === 'studio') return
    if (studioSessionIds.value.has(session.id)) return
    if (studioRedirect.value?.agentId === agentId) return
    const target = getAgent(agentId)
    if ((target?.features as any)?.studio?.default_mode === 'studio') {
      studioRedirect.value = { agentId, agentName }
    }
  }
  const availableModels = ref<AvailableModel[]>([])
  const pipelineTasks = ref<Record<string, PipelineTask>>({})
  const pipelinePollTimers = new Map<string, ReturnType<typeof setTimeout>>()

  /** Studio（工作台）会话 ID 集合：供会话列表打 📊 角标（后端 ChatSessionDTO 无 mode 字段，前端绕道获取） */
  const studioSessionIds = ref<Set<string>>(new Set())
  const currentPlan = ref<StudioPlanStep[]>([])
  /** 当前 Studio 会话的权限模式（supervised=关键操作需批准；auto=放权自动执行） */
  const studioPermissions = ref<{ mode: StudioPermissionMode }>({ mode: 'supervised' })

  const { streamChat, abortStream, isPaused, pauseStream, resetPause } = useAgentChatStream()

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

  async function invokePipelineTool(
    toolName: string,
    arguments_: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const response = await apiClient.post(`/mcp/pipelines/tools/${toolName}/invoke`, {
      tool_name: toolName,
      arguments: arguments_,
    })
    const envelope = response.data as {
      success?: boolean
      error?: string
      result?: Record<string, unknown>
    }
    if (!envelope.success) throw new Error(envelope.error || `${toolName} 调用失败`)
    const result = envelope.result || {}
    return (result.llm_payload as Record<string, unknown>) || result
  }

  function upsertPipelineTask(
    taskId: string,
    pipelineType: PipelineType,
    patch: Partial<PipelineTask> = {},
  ): PipelineTask {
    const current = pipelineTasks.value[taskId]
    const task: PipelineTask = {
      ...current,
      ...patch,
      taskId,
      pipelineType,
      status: patch.status || current?.status || 'queued',
      progress: patch.progress ?? current?.progress ?? 0,
      polling: patch.polling ?? current?.polling ?? false,
    }
    pipelineTasks.value[taskId] = task
    return task
  }

  function stopPipelinePolling(taskId: string): void {
    const timer = pipelinePollTimers.get(taskId)
    if (timer) clearTimeout(timer)
    pipelinePollTimers.delete(taskId)
    const task = pipelineTasks.value[taskId]
    if (task) task.polling = false
  }

  async function loadPipelineResults(task: PipelineTask): Promise<void> {
    const data = await invokePipelineTool(`${task.pipelineType}_results`, {
      task_id: task.taskId,
      result_types: ['summary', 'artifacts'],
    })
    upsertPipelineTask(task.taskId, task.pipelineType, {
      reportUrl: data.report_url as string | undefined,
      metrics: (data.metrics as PipelineTask['metrics']) || {},
      artifacts: (data.artifacts as PipelineTask['artifacts']) || [],
    })
  }

  async function pollPipelineTask(taskId: string): Promise<void> {
    const task = pipelineTasks.value[taskId]
    if (!task || task.polling) return
    task.polling = true
    try {
      const data = await invokePipelineTool(`${task.pipelineType}_status`, { task_id: taskId })
      const status = String(data.status || 'running').toLowerCase() as PipelineTaskStatus
      const progressValue = Number(data.progress || 0)
      upsertPipelineTask(taskId, task.pipelineType, {
        status,
        progress: progressValue <= 1 ? progressValue * 100 : progressValue,
        resultUrl: data.result_url as string | undefined,
        error: (data.error_summary as string | undefined) || undefined,
        polling: false,
      })
      if (status === 'success') {
        await loadPipelineResults(pipelineTasks.value[taskId])
        stopPipelinePolling(taskId)
        return
      }
      if (['failed', 'cancelled'].includes(status)) {
        stopPipelinePolling(taskId)
        return
      }
    } catch (error) {
      upsertPipelineTask(taskId, task.pipelineType, {
        error: error instanceof Error ? error.message : '任务状态获取失败',
        polling: false,
      })
    }
    pipelinePollTimers.set(taskId, setTimeout(() => pollPipelineTask(taskId), 2500))
  }

  async function submitPipelineTask(
    pipelineType: PipelineType,
    preparedParams: Record<string, unknown>,
  ): Promise<PipelineTask> {
    const data = (await invokePipelineTool(`${pipelineType}_submit`, {
      prepared_params: preparedParams,
    })) as unknown as PipelineSubmitResult
    const task = upsertPipelineTask(data.task_id, pipelineType, {
      status: String(data.status || 'queued').toLowerCase() as PipelineTaskStatus,
      progress: Number(data.progress || 0),
      resultUrl: data.result_url,
      preparedParams,
    })
    void pollPipelineTask(task.taskId)
    return task
  }

  function trackPipelineTask(
    taskId: string,
    pipelineType: PipelineType,
    initial?: Partial<PipelineTask>,
  ): PipelineTask {
    const existing = pipelineTasks.value[taskId]
    const task = upsertPipelineTask(
      taskId,
      pipelineType,
      existing
        ? { preparedParams: existing.preparedParams || initial?.preparedParams }
        : initial,
    )
    if (!['success', 'failed', 'cancelled'].includes(task.status)) void pollPipelineTask(taskId)
    return task
  }

  async function retryPipelineTask(taskId: string): Promise<PipelineTask> {
    const task = pipelineTasks.value[taskId]
    if (!task?.preparedParams) throw new Error('缺少原始预检参数，无法直接重试')
    return submitPipelineTask(task.pipelineType, task.preparedParams)
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
        command: m.command ?? '',
        args: m.args ?? [],
        url: m.url ?? '',
        env: m.env ?? {},
        registry: m.registry ?? 'default',
        working_dir: m.working_dir ?? '',
        version: m.version ?? '',
        is_enabled: m.is_enabled ?? true,
        tools: m.tools ?? [],
        timeout: m.timeout ?? 30,
        auto_restart: m.auto_restart ?? true,
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
        source: s.is_builtin ? 'builtin' : (s.source_type ?? 'json'),
        source_url: s.source_ref ?? undefined,
        version: s.version ?? undefined,
        author: s.author ?? undefined,
        has_scripts: !!s.has_scripts,
        is_active: s.is_active ?? true,
      }))
    } catch (e) {
      console.error('加载技能列表失败:', e)
    }
  }

  /** 加载可用模型列表（供会话内模型切换） */
  async function fetchAvailableModels(): Promise<void> {
    try {
      const res = await apiClient.get<AvailableModel[]>('/chat/models')
      availableModels.value = (res.data || []).map((m) => ({
        id: String(m.id),
        name: m.name,
        model: m.model,
        provider_type: m.provider_type,
        is_default: m.is_default,
        temperature: m.temperature,
        max_tokens: m.max_tokens,
      }))
    } catch (e) {
      console.error('加载模型列表失败:', e)
    }
  }

  /** 加载当前用户的历史会话列表（Agent-first 模式只保留绑定 agent_id 的会话） */
  async function fetchSessions(): Promise<void> {
    try {
      const res = await apiClient.get<Array<{
        session_id: string
        title: string
        title_locked?: boolean
        agent_id: string | null
        model_id: string
        mode?: 'chat' | 'studio'
        mcp_mode?: 'off' | 'auto' | 'manual'
        extra_mcp_servers?: string[]
        created_at: string
        updated_at: string
      }>>('/chat/sessions')
      const loaded = (res.data || [])
        .filter((s) => s.agent_id)
        .map((s) => ({
          id: s.session_id,
          title: s.title,
          title_locked: s.title_locked ?? false,
          agent_id: s.agent_id as string,
          mode: s.mode || 'chat',
          messages: [] as ChatMessage[],
          created_at: s.created_at,
          updated_at: s.updated_at,
          model_id: s.model_id || undefined,
          mcp_mode: s.mcp_mode || 'auto',
          extra_mcp_servers: s.extra_mcp_servers || [],
        }))
      // 合并正在流式中的临时会话，避免刷新时丢失
      const tempSessions = sessions.value.filter((s) => s.id.startsWith('sess-'))
      sessions.value = [...tempSessions, ...loaded]
    } catch (e) {
      console.error('加载会话列表失败:', e)
    }
  }

  /** 拉取当前用户的 Studio 会话 ID 集合（供 /ai 会话列表打角标；失败静默，不阻塞主流程） */
  async function fetchStudioSessionIds(): Promise<void> {
    try {
      const res = await apiClient.get<Array<{ session_id: string }>>('/studio/sessions')
      studioSessionIds.value = new Set((res.data || []).map((s) => s.session_id))
    } catch (e) {
      console.error('加载 Studio 会话列表失败:', e)
    }
  }

  /** 新建 Studio 会话后登记 ID，无需整表刷新 */
  function markStudioSession(id: string): void {
    studioSessionIds.value = new Set([...studioSessionIds.value, id])
  }

  /** 一次性初始化全部资产（前台页面挂载时调用） */
  async function initAssets(): Promise<void> {
    await Promise.all([
      fetchAgents(true), fetchMcps(), fetchSkills(false), fetchAvailableModels(), fetchSessions(),
      fetchStudioSessionIds(),
    ])
  }

  // ========== 资产 Actions（后台 CRUD，调真实 API） ==========

  /** 切换 MCP 启用状态 */
  async function toggleMcpStatus(id: string) {
    const m = mcps.value.find((x) => x.id === id)
    if (!m) return
    const newEnabled = !m.is_enabled
    try {
      await apiClient.put(`/mcp/servers/${id}`, { is_enabled: newEnabled })
      m.is_enabled = newEnabled
    } catch {
      // keep original
    }
  }

  async function addMcpServer(data: {
    name: string
    description?: string
    transport: string
    command?: string
    args?: string[]
    url?: string
    env?: Record<string, string>
    registry?: string
    working_dir?: string
    timeout?: number
  }): Promise<McpService> {
    const res = await apiClient.post<McpService>('/mcp/servers', data)
    await fetchMcps()
    const id = String(res.data?.id || '')
    const created = mcps.value.find((server) => server.id === id)
      || mcps.value.find((server) => server.name === data.name)
    if (!created) throw new Error('MCP 创建成功但未能读取服务信息')
    return created
  }

  async function updateMcpServer(id: string, data: Record<string, unknown>): Promise<void> {
    await apiClient.put(`/mcp/servers/${id}`, data)
    await fetchMcps()
  }

  async function fetchMcpLogs(id: string, tail = 100): Promise<McpLogEntry[]> {
    const res = await apiClient.get(`/mcp/servers/${id}/logs`, { params: { tail } })
    return (res.data || []).map((log: any) => ({
      timestamp: log.timestamp,
      level: log.level,
      message: log.message,
      source: log.source,
    }))
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
    let saved: AgentTemplate
    if (dto.id && agents.value.some((a) => a.id === dto.id)) {
      saved = await adminAgentApi.update(dto.id, dto)
    } else {
      saved = await adminAgentApi.create(dto)
    }
    await fetchAgents(false)
    return saved
  }

  async function toggleAgent(id: string): Promise<void> {
    await adminAgentApi.toggle(id)
    await fetchAgents(false)
  }

  async function deleteAgent(id: string): Promise<void> {
    await adminAgentApi.remove(id)
    await fetchAgents(false)
  }

  async function setDefaultAgent(id: string): Promise<void> {
    await adminAgentApi.setDefault(id)
    await fetchAgents(false)
  }

  // ========== 技能管理（后台 CRUD + SKILL.md 四入口导入，调 /admin/skills） ==========

  /** 入口一：GitHub 仓库/子目录 URL → 解析预览（不入库） */
  async function previewSkillFromGithub(url: string): Promise<SkillImportPreview> {
    const res = await apiClient.post<SkillImportPreview>('/admin/skills/import/github', { url })
    return res.data
  }

  /** 入口二：本地 zip 上传 → 解析预览（不入库） */
  async function previewSkillFromZip(file: File): Promise<SkillImportPreview> {
    const form = new FormData()
    form.append('file', file)
    const res = await apiClient.post<SkillImportPreview>('/admin/skills/import/zip', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  }

  /** 入口三：JSON 粘贴（兼容旧格式）→ 解析预览（不入库） */
  async function previewSkillFromJson(text: string): Promise<SkillImportPreview> {
    const res = await apiClient.post<SkillImportPreview>('/admin/skills/import/json', { text })
    return res.data
  }

  /** 预览确认后入库 */
  async function confirmSkillImport(preview: SkillImportPreview, overwrite = false): Promise<void> {
    await apiClient.post('/admin/skills/import/confirm', { preview, overwrite })
    await fetchSkills(true)
  }

  /** 入口四：技能市场列表（随仓库发布的内置技能） */
  async function fetchSkillMarketplace(): Promise<SkillMarketplaceItem[]> {
    const res = await apiClient.get<SkillMarketplaceItem[]>('/admin/skills/marketplace')
    return res.data || []
  }

  /** 一键安装市场技能 */
  async function installMarketplaceSkill(skillId: string, overwrite = false): Promise<void> {
    await apiClient.post(`/admin/skills/marketplace/${skillId}/install`, null, {
      params: { overwrite },
    })
    await fetchSkills(true)
  }

  /** 检查上游更新（GitHub 来源） */
  async function checkSkillUpdate(skillId: string): Promise<SkillUpdateCheck> {
    const res = await apiClient.post<SkillUpdateCheck>(`/admin/skills/${skillId}/check-update`)
    return res.data
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
      title_locked: false,
      agent_id: agentId,
      mode: 'chat',
      messages: [],
      created_at: now,
      updated_at: now,
      model_id: agent.model_id || undefined,
      mcp_mode: 'auto',
      extra_mcp_servers: [],
    }
    sessions.value.unshift(session)
    currentSessionId.value = session.id
    return session
  }

  async function selectSession(id: string) {
    if (currentSessionId.value !== id) {
      stopStreaming()
      currentPlan.value = []
    }
    currentSessionId.value = id
    const session = sessions.value.find((s) => s.id === id)
    if (session && session.messages.length === 0 && !session.id.startsWith('sess-')) {
      await loadSessionMessages(id)
    }
    // Studio 会话：同步权限模式（非 studio 会话保持默认 supervised，不在此展示开关）
    if (studioSessionIds.value.has(id)) {
      studioApi.getSession(id)
        .then((detail) => initStudioPermissions(detail.permissions?.mode))
        .catch(() => {})
    }
  }

  function newChat() {
    stopStreaming()
    currentSessionId.value = ''
  }

  async function deleteSession(id: string) {
    if (currentSessionId.value === id) stopStreaming()
    if (!id.startsWith('sess-')) {
      try {
        await apiClient.delete(`/chat/sessions/${id}`)
      } catch (e) {
        console.error('删除会话失败:', e)
        return
      }
    }
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentSessionId.value === id) currentSessionId.value = ''
  }

  async function renameSession(id: string, title: string) {
    const s = sessions.value.find((x) => x.id === id)
    const cleaned = title.trim()
    if (!s || !cleaned) return
    if (id.startsWith('sess-')) {
      s.title = cleaned
      s.title_locked = true
      return
    }
    const previous = s.title
    s.title = cleaned
    s.title_locked = true
    try {
      const res = await apiClient.patch<{
        session_id: string
        title: string
        title_locked?: boolean
      }>(`/chat/sessions/${id}`, { title: cleaned })
      s.title = res.data.title
      s.title_locked = res.data.title_locked ?? true
    } catch (e) {
      s.title = previous
      console.error('重命名会话失败:', e)
      throw e
    }
  }

  async function generateSessionTitle(id: string): Promise<void> {
    if (!id || id.startsWith('sess-')) return
    const session = sessions.value.find((s) => s.id === id)
    if (!session || session.title_locked) return
    try {
      const res = await apiClient.post<{ title: string }>(`/chat/sessions/${id}/generate-title`)
      if (res.data?.title) session.title = res.data.title
    } catch (e) {
      console.error('生成会话标题失败:', e)
      // 首轮 LLM 失败时把“生成中...”占位回退，避免历史列表标题卡在占位文案
      if (session.title === '生成中...') session.title = '新对话'
    }
  }

  async function searchSessions(keyword: string): Promise<{
    title_matches: AgentSession[]
      content_matches: Array<{ session_id: string; title: string; title_locked: boolean; agent_id: string | null; model_id: string; mode: 'chat' | 'studio'; message_id: string; snippet: string; created_at: string; updated_at: string }>
  }> {
    const res = await apiClient.get('/chat/sessions/search', { params: { keyword } })
    const title_matches = (res.data?.title_matches || [])
      .filter((s: any) => s.agent_id)
      .map((s: any) => ({
        id: s.session_id,
        title: s.title,
        title_locked: s.title_locked ?? false,
        agent_id: s.agent_id,
        mode: s.mode || 'chat',
        messages: [] as ChatMessage[],
        created_at: s.created_at,
        updated_at: s.updated_at,
        model_id: s.model_id || undefined,
      }))
    return {
      title_matches,
      content_matches: (res.data?.content_matches || []).map((m: any) => ({
        session_id: m.session_id,
        title: m.title,
        title_locked: m.title_locked ?? false,
        agent_id: m.agent_id,
        model_id: m.model_id,
        mode: m.mode || 'chat',
        message_id: m.message_id,
        snippet: m.snippet,
        created_at: m.created_at,
        updated_at: m.updated_at,
      })),
    }
  }

  /** 切换指定会话当前使用的模型 */
  function switchSessionModel(id: string, modelId: string) {
    const s = sessions.value.find((x) => x.id === id)
    if (s) s.model_id = modelId
  }

  /** 从后端加载指定会话的历史消息（含 token）并替换当前客户端消息 */
  async function loadSessionMessages(sessionId: string): Promise<void> {
    try {
      const res = await apiClient.get<Array<{
        message_id: string
        role: string
        content: string
        metadata_json?: Record<string, unknown>
        created_at: string
        tokens?: { input: number; output: number; total: number }
      }>>(`/chat/sessions/${sessionId}/messages`)
      const session = sessions.value.find((s) => s.id === sessionId)
      if (!session) return
      const existingIds = new Set(session.messages.map((m) => m.id))
      let restoredPlan: StudioPlanStep[] = []
      const loaded = (res.data || []).map((m) => {
        const msg: ChatMessage = {
          id: m.message_id,
          role: m.role as 'user' | 'assistant' | 'system',
          content: m.content,
          createdAt: m.created_at,
          modelName: (m.metadata_json?.model as string) || undefined,
          // usage is response metadata; keep it off user/system messages even if an old
          // backend row contains a stale tokens payload.
          tokens: m.role === 'assistant' ? (m.tokens || { input: 0, output: 0, total: 0 }) : undefined,
        }
        // 智能路由：恢复本条消息的专家徽标
        const routedAgent = m.metadata_json?.routed_agent as
          | { agent_id?: string; name?: string; avatar?: string; color?: string; reason?: string }
          | undefined
        if (routedAgent?.name) {
          msg.routedAgent = {
            agentId: routedAgent.agent_id || '',
            name: routedAgent.name,
            avatar: routedAgent.avatar || '',
            color: routedAgent.color || '',
            reason: routedAgent.reason || '',
          }
        }
        const webSources = m.metadata_json?.web_sources
        if (Array.isArray(webSources)) {
          msg.webSources = webSources
            .filter((source): source is Record<string, unknown> => !!source && typeof source === 'object')
            .filter((source) => typeof source.title === 'string' && typeof source.url === 'string')
            .map((source) => ({
              title: source.title as string,
              url: source.url as string,
              snippet: typeof source.snippet === 'string' ? source.snippet : '',
              publishedAt: typeof source.publishedAt === 'string' ? source.publishedAt : null,
            }))
        }
        // Studio 会话：历史消息随 metadata_json.tool_invocations 落库，
        // 重载时重建工具调用卡片（代码卡片凭 arguments + ui_payload 渲染）
        const invocations = m.metadata_json?.tool_invocations
        if (Array.isArray(invocations) && invocations.length) {
          msg.toolCalls = invocations.map((t) => {
            const inv = t as Record<string, unknown>
            const uiPayload = (inv.ui_payload as Record<string, unknown> | undefined) || undefined
            if (inv.tool_name === 'update_plan' && Array.isArray(uiPayload?.steps)) {
              restoredPlan = uiPayload.steps as StudioPlanStep[]
            }
            const so = typeof uiPayload?.stdout === 'string' ? uiPayload.stdout : ''
            const se = typeof uiPayload?.stderr === 'string' ? uiPayload.stderr : ''
            const tc: ToolCall = {
              id: (inv.tool_call_id as string) || `tc-${m.message_id}`,
              name: (inv.tool_name as string) || '',
              arguments: (inv.arguments as Record<string, unknown>) || {},
              result: inv.result,
              uiPayload,
              mcpServer: 'studio',
              status: inv.success ? 'success' : 'error',
            }
            if (so || se) tc.output = so + se
            return tc
          })
        }
        return msg
      })
      // 保留当前正在流式中的占位消息，避免闪烁
      const streamingPlaceholders = session.messages.filter(
        (m) => m.role === 'assistant' && m.content === '' && !existingIds.has(m.id),
      )
      session.messages = [...loaded, ...streamingPlaceholders]
    } catch (e) {
      console.error('加载会话历史消息失败:', e)
    }
  }

  /** 发送消息（真实 SSE 流式，走 Agent 调度中枢） */
  async function sendMessage(
    content: string,
    options: {
      attachments?: FileAttachment[]
      enableWebSearch?: boolean
      enableCodeExecution?: boolean
      /** @ 显式指定的智能体：本条消息转交该专家回答 */
      explicitAgentId?: string
      /** @ 挂载到本次对话的技能名 */
      skillNames?: string[]
      mcpMode?: 'off' | 'auto' | 'manual'
      extraMcpServers?: string[]
      /** 工具轮次触顶后用户确认继续：本次请求上限扩展到 1000 轮 */
      extendMaxRounds?: boolean
    } = {},
  ): Promise<void> {
    const session = currentSession.value
    if (!session || isStreaming.value || !content.trim()) return
    // @ 显式指定的智能体优先，否则回落到会话绑定的智能体
    const agent = getAgent(options.explicitAgentId || session.agent_id) || getAgent(session.agent_id)
    if (!agent) return
    // 临时会话尚未在后端落库时，@Agent 会决定该会话的实际绑定对象。
    // 必须同步本地绑定，否则首轮后端创建的是显式 Agent 会话，第二轮却会按旧 Agent 发请求，
    // 触发“会话绑定的 Agent 与当前请求不一致”。
    if (options.explicitAgentId && session.id.startsWith('sess-')) {
      session.agent_id = agent.id
      session.model_id = agent.model_id || undefined
    }
    if (options.mcpMode) session.mcp_mode = options.mcpMode
    if (options.extraMcpServers) session.extra_mcp_servers = [...options.extraMcpServers]

    // 若当前临时会话 ID 正在解析为真实 ID，排队等待，防止创建重复会话
    if (session.id.startsWith('sess-') && pendingSessionIdPromise) {
      await pendingSessionIdPromise
    }

    const chatStore = useChatStore()
    const now = new Date().toISOString()

    // 用户消息
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      createdAt: now,
    }
    if (options.attachments?.length) {
      userMsg.attachments = options.attachments.map((a) => ({
        name: a.name,
        size: a.size,
        type: a.type,
        url: a.url,
        file_id: a.file_id,
        source: a.source,
      }))
    }
    session.messages.push(userMsg)

    // 助手占位消息（流式填充）
    const aiId = `msg-ai-${Date.now()}`
    const aiMsgSeed: ChatMessage = {
      id: aiId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      modelName: agent.model_engine || agent.name,
      toolCalls: [],
      createdAt: new Date().toISOString(),
      tokens: { input: 0, output: 0, total: 0 },
    }
    session.messages.push(aiMsgSeed)
    // 必须使用响应式数组返回的代理对象继续写入。
    // 若继续修改 push 前的普通对象，message_id/content/thought 的流式更新不会触发 Vue，
    // 会出现 Token 已更新但正文气泡保持空白，刷新后才显示的现象。
    const aiMsg = session.messages[session.messages.length - 1]!

    // 标题随对话演进刷新：首轮必算，之后每满 3 条用户消息重算一次，以捕捉后续多轮里
    // 用户真正关心的基因/流程/文件等细节；锁定或超过 12 轮后停止，避免无谓的 LLM 调用。
    // 仅首轮显示“生成中...”占位，刷新轮静默替换，避免已成型标题闪烁成占位文案。
    const userCount = session.messages.filter((m) => m.role === 'user').length
    const isFirstTurn = userCount === 1
    const shouldGenerateTitle =
      !session.title_locked && userCount <= 12 && (isFirstTurn || userCount % 3 === 0)
    if (isFirstTurn) session.title = '生成中...'

    // 构建送后端的上下文（含历史，排除当前 AI 占位）
    const ctxLen = chatStore.conversationSettings.contextLength ?? 20
    const apiMessages = session.messages
      .filter((m) => m.id !== aiId && m.role !== 'assistant' || (m.role === 'assistant' && m.content.length > 0))
      .slice(-ctxLen)
      .map((m) => ({ role: m.role, content: m.content }))

    // @ 挂载技能：在最后一条用户消息注入显式技能上下文，使模型优先运用对应能力
    if (options.skillNames?.length) {
      const lastUser = [...apiMessages].reverse().find((m) => m.role === 'user')
      if (lastUser) {
        lastUser.content += `\n\n[用户为本次对话挂载技能：${options.skillNames.join('、')}，请优先运用相关能力作答。]`
      }
    }

    // 当前消息的附件（仅最后一条用户消息需要）
    const apiAttachments = options.attachments?.map((a) => ({
      type: (a.type.startsWith('image/') ? 'image' : 'file') as 'image' | 'file',
      url: a.url || '',
      name: a.name,
      mime_type: a.type,
      file_id: a.file_id,
    })) || []

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
        modelId: session.model_id,
        temperature: chatStore.conversationSettings.temperature,
        maxTokens: chatStore.conversationSettings.maxTokens,
        deepThinking: chatStore.deepThinking,
        attachments: apiAttachments,
        enableWebSearch: options.enableWebSearch ?? chatStore.enableWebSearch,
        enableCodeExecution: options.enableCodeExecution ?? false,
        mcpMode: options.mcpMode ?? session.mcp_mode ?? 'auto',
        extraMcpServers: options.extraMcpServers ?? session.extra_mcp_servers ?? [],
        extendMaxRounds: options.extendMaxRounds ?? false,
      },
      {
        onText: (text, isReasoning) => {
          if (isReasoning) {
            streamingThought.value += text
            aiMsg.thought = streamingThought.value
          } else {
            streamingContent.value += text
            aiMsg.content = streamingContent.value
          }
          session.updated_at = new Date().toISOString()
        },
        onSessionCreated: (sessionId, messageId) => {
          // 首个文本块只回填后端 ID。不要在流式过程中加载历史消息：
          // 此时后端助手行仍是 streaming/0 token，会替换正在更新的 aiMsg。
          if (session.id.startsWith('sess-')) {
            session.id = sessionId
            session.agent_id = agent.id
            currentSessionId.value = sessionId
            if (messageId) aiMsg.backendMessageId = messageId
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
            mcpServer: event.mcp_server,
          })
        },
        onToolResult: (event) => {
          const tc = (aiMsg.toolCalls || []).find((t) => t.id === event.tool_call_id)
          if (tc) {
            tc.result = event.result
            // 兼容：event.ui_payload 缺失但 event.result 里包着 ui_payload 的情况
            let uiPayload = event.ui_payload
            if (!uiPayload && event.result && typeof event.result === 'object') {
              const r = event.result as Record<string, unknown>
              uiPayload = (r.ui_payload as Record<string, unknown> | undefined)
                || (r.uiPayload as Record<string, unknown> | undefined)
            }
            tc.uiPayload = uiPayload
            tc.status = event.success ? 'success' : 'error'
            tc.mcpServer = event.mcp_server
            // Studio 工具：未走 tool_output 流时，用 ui_payload 的 stdout/stderr 回填输出区
            if (!tc.output && uiPayload) {
              const so = typeof uiPayload.stdout === 'string' ? uiPayload.stdout : ''
              const se = typeof uiPayload.stderr === 'string' ? uiPayload.stderr : ''
              if (so || se) tc.output = appendBoundedStudioOutput('', so + se)
            }
            if (event.success && (tc.name === 'workspace_write' || tc.name === 'workspace_edit')) {
              const changedPath = String(tc.arguments.path || uiPayload?.path || '')
              if (changedPath) {
                window.dispatchEvent(new CustomEvent('omichub:studio-file-changed', {
                  detail: { sessionId: session.id, path: changedPath, tool: tc.name },
                }))
              }
            }
          }
        },
        onWebSearch: (event) => {
          aiMsg.webSearchStatus = {
            query: event.query,
            status: event.status,
            message: event.message,
          }
        },
        onWebSearchResults: (sources) => {
          aiMsg.webSources = sources
          aiMsg.webSearchStatus = { status: 'complete' }
        },
        onPlan: (steps) => {
          currentPlan.value = steps
        },
        onRoundLimit: (event) => {
          if (event.canExtend) {
            roundLimitPrompt.value = { sessionId: event.sessionId, maxRounds: event.maxRounds }
          }
        },
        onContextCompressed: (estimatedTokens) => {
          contextCompressedNotice.value = estimatedTokens
        },
        onApprovalRequest: (event) => {
          // 找到对应工具卡片：置 awaiting_approval 并保存审批信息（卡片由 ApprovalCard 接管交互）
          const tc = (aiMsg.toolCalls || []).find((t) => t.id === event.tool_call_id)
          if (!tc) return
          tc.status = 'awaiting_approval'
          tc.approval = {
            approval_id: event.approval_id,
            status: 'pending',
            risk_hint: event.risk_hint,
            timeout_seconds: event.timeout_seconds,
          }
          // 审批事件的 arguments 可能比 tool_call 事件更全，以其为准补齐
          tc.arguments = { ...tc.arguments, ...event.arguments }
        },
        onApprovalResolved: (event) => {
          const tc = (aiMsg.toolCalls || []).find((t) => t.id === event.tool_call_id)
          if (!tc?.approval) return
          tc.approval.status = event.action
          if (event.action === 'approved' || event.action === 'edited') {
            // 批准后工具照常执行，回到 running 等待 tool_output/tool_result
            tc.status = 'running'
          } else {
            // rejected/timeout：后端会以 rejected tool_result 收尾；先落定终态
            tc.status = 'error'
          }
        },
        onAskRequest: (event) => {
          aiMsg.askRequest = {
            question: event.question,
            options: event.options,
            answered: false,
          }
        },
        onRoute: (event) => {
          // 智能路由：记录本条消息实际由哪位专家回答（气泡头部徽标）
          aiMsg.routedAgent = {
            agentId: event.agent_id,
            name: event.name,
            avatar: event.avatar,
            color: event.color,
            reason: event.reason,
          }
          maybeRedirectToStudio(event.agent_id, event.name)
        },
        onHandoff: (event) => {
          // 交接后会话绑定目标 Agent，下一轮消息直接由目标继续；当前消息的工具卡保留完整交接摘要。
          session.agent_id = event.target_agent_id
          const target = getAgent(event.target_agent_id)
          if (target) {
            aiMsg.routedAgent = {
              agentId: target.id,
              name: target.name,
              avatar: target.avatar,
              color: target.color,
              reason: event.reason,
            }
            maybeRedirectToStudio(target.id, target.name)
          }
        },
        onConsultation: (event) => {
          aiMsg.consultation = { experts: event.experts }
        },
        onToolOutput: (tool, _stream, data, toolCallId) => {
          // 优先按 tool_call_id 精确匹配；无 id（旧事件）时回退为最后一个同名 running 工具
          const tcs = aiMsg.toolCalls || []
          const tc = toolCallId
            ? tcs.find((t) => t.id === toolCallId)
            : [...tcs].reverse().find((t) => t.status === 'running' && (!tool || t.name === tool))
          if (tc) tc.output = appendBoundedStudioOutput(tc.output || '', data)
        },
        onError: (error) => {
          aiMsg.content = streamingContent.value || `生成失败: ${error}`
          aiMsg.thought = streamingThought.value || undefined
          aiMsg.status = 'error'
          aiMsg.toolCalls = (aiMsg.toolCalls || []).map((t) =>
            t.status === 'running' ? { ...t, status: 'error' as const } : t,
          )
          isStreaming.value = false
          streamingContent.value = ''
          streamingThought.value = ''
          releaseSessionIdLock()
        },
        onDone: (_, messageId, usage, finishReason, finalContent, finalReasoning) => {
          if (!streamingContent.value && finalContent) {
            streamingContent.value = finalContent
          }
          if (!streamingThought.value && finalReasoning) {
            streamingThought.value = finalReasoning
          }
          aiMsg.content = streamingContent.value || aiMsg.content
          aiMsg.thought = streamingThought.value || undefined
          if (finishReason) aiMsg.finishReason = finishReason
          if (usage) {
            const input = usage.prompt_tokens ?? usage.input_tokens ?? usage.input ?? 0
            const output = usage.completion_tokens ?? usage.output_tokens ?? usage.output ?? 0
            const total = usage.total_tokens ?? usage.total ?? input + output
            // 以服务端返回的 assistant message_id 定位，避免流期间对象被替换后写入旧引用。
            const targetId = messageId || aiMsg.backendMessageId || aiMsg.id
            const target = session.messages.find(
              (item) => (item.id === targetId || item.backendMessageId === targetId) && item.role === 'assistant',
            )
            ;(target || aiMsg).tokens = { input, output, total }
          }
          if (finishReason === 'length' && aiMsg.content.trim()) {
            aiMsg.content += '\n\n---\n⚠️ *回答因达到最大长度限制而截断，可尝试缩短提问或分步追问。*'
          }
          if (!aiMsg.content.trim() && !aiMsg.toolCalls?.length) {
            aiMsg.status = aiMsg.thought ? 'empty' : 'error'
            reportChatDiagnostic({
              phase: 'stream-empty',
              messageId: aiMsg.backendMessageId || aiMsg.id,
              sessionId: session.id,
              rawResponseSummary: {
                usage,
                finishReason,
                hasThought: Boolean(aiMsg.thought?.trim()),
              },
            })
            if (!aiMsg.thought) {
              aiMsg.content = '当前模型响应为空，请重新发送'
            }
          }
          if (aiMsg.status !== 'error' && aiMsg.status !== 'empty') aiMsg.status = 'complete'
          if (aiMsg.content.trimStart().startsWith('📤 需要您提供数据')) {
            dataRequestNotice.value = { sessionId: session.id, text: aiMsg.content.trim() }
          }
          isStreaming.value = false
          streamingContent.value = ''
          streamingThought.value = ''
          releaseSessionIdLock()
        },
      },
    )

    if (shouldGenerateTitle && !isStreaming.value) {
      void generateSessionTitle(session.id)
    }

    // 兜底：若流异常中断未触发 onDone/onError（极罕见，onDone 已有内部兜底）
    if (isStreaming.value) {
      aiMsg.content = streamingContent.value || aiMsg.content
      aiMsg.thought = streamingThought.value || undefined
      if (!aiMsg.content.trim() && !aiMsg.toolCalls?.length) {
        aiMsg.status = aiMsg.thought ? 'empty' : 'error'
        if (!aiMsg.thought) {
          aiMsg.content = '当前模型响应为空，请重新发送'
        }
      }
      isStreaming.value = false
      streamingContent.value = ''
      streamingThought.value = ''
      releaseSessionIdLock()
    }
  }

  function stopStreaming() {
    abortStream()
    const session = currentSession.value
    if (session) {
      const last = session.messages[session.messages.length - 1]
      if (last && last.role === 'assistant') {
        last.content = streamingContent.value || last.content || '（已停止）'
        last.thought = streamingThought.value || undefined
      }
    }
    isStreaming.value = false
    streamingContent.value = ''
    streamingThought.value = ''
    releaseSessionIdLock()
  }

  /** 暂停流式输出：保留已输出文本，标记暂停态供 UI 显示继续/重新生成按钮 */
  function pauseStreaming() {
    pauseStream()
    const session = currentSession.value
    if (session) {
      const last = session.messages[session.messages.length - 1]
      if (last && last.role === 'assistant') {
        last.content = streamingContent.value || last.content
        last.thought = streamingThought.value || undefined
        last.status = 'streaming'
      }
    }
    releaseSessionIdLock()
  }

  // ========== Studio HITL：审批 / 澄清 / 权限模式 ==========

  /** 在所有会话消息中定位待审批的工具卡片（审批仅内存态，限定当前会话即可） */
  function findApprovalTool(approvalId: string): ToolCall | null {
    const session = currentSession.value
    if (!session) return null
    for (const msg of session.messages) {
      const tc = (msg.toolCalls || []).find((t) => t.approval?.approval_id === approvalId)
      if (tc) return tc
    }
    return null
  }

  /** 批准待审批工具；带 modifiedArgs 即"编辑后批准"（乐观更新，后端决议经 approval_resolved 回写） */
  async function approveToolCall(
    approvalId: string,
    modifiedArgs?: Record<string, unknown>,
  ): Promise<void> {
    const tc = findApprovalTool(approvalId)
    if (tc?.approval && tc.approval.status === 'pending') {
      tc.approval.status = modifiedArgs ? 'edited' : 'approved'
      tc.status = 'running'
    }
    try {
      await studioApi.approveApproval(approvalId, modifiedArgs)
    } catch (e) {
      if (tc?.approval) {
        tc.approval.status = 'pending'
        tc.status = 'awaiting_approval'
      }
      throw e
    }
  }

  /** 退回待审批工具（理由回灌 LLM 让其修改后重试） */
  async function rejectToolCall(approvalId: string, reason?: string): Promise<void> {
    const tc = findApprovalTool(approvalId)
    if (tc?.approval && tc.approval.status === 'pending') {
      tc.approval.status = 'rejected'
      tc.status = 'error'
    }
    try {
      await studioApi.rejectApproval(approvalId, reason)
    } catch (e) {
      if (tc?.approval) {
        tc.approval.status = 'pending'
        tc.status = 'awaiting_approval'
      }
      throw e
    }
  }

  /** 回答 ask_user 澄清：等价于把该文本作为下一条用户消息发送 */
  async function answerAskRequest(text: string): Promise<void> {
    const session = currentSession.value
    if (session) {
      for (let i = session.messages.length - 1; i >= 0; i--) {
        const msg = session.messages[i]
        if (msg.askRequest && !msg.askRequest.answered) {
          msg.askRequest.answered = true
          break
        }
      }
    }
    await sendMessage(text)
  }

  /** 进入会话时按后端 detail.permissions 初始化（默认 supervised） */
  function initStudioPermissions(mode?: StudioPermissionMode): void {
    studioPermissions.value = { mode: mode || 'supervised' }
  }

  /** 切换当前 Studio 会话权限模式（调 API 后更新本地态） */
  async function setStudioPermissions(mode: StudioPermissionMode): Promise<void> {
    const sessionId = currentSessionId.value
    if (!sessionId || sessionId.startsWith('sess-')) return
    const prev = studioPermissions.value.mode
    studioPermissions.value = { mode }
    try {
      const saved = await studioApi.updatePermissions(sessionId, mode)
      studioPermissions.value = { mode: saved.mode || mode }
    } catch (e) {
      studioPermissions.value = { mode: prev }
      throw e
    }
  }

  return {
    // state
    mcps, skills, agents, sessions, currentSessionId,
    isStreaming, isPaused, streamingContent, streamingThought, availableModels, pipelineTasks,
    dataRequestNotice,
    roundLimitPrompt,
    contextCompressedNotice,
    studioRedirect,
    studioSessionIds, currentPlan, studioPermissions,
    // getters
    activeAgents, currentSession, currentAgent, groupedSessions,
    // lookups
    getAgent, mcpsByIds, skillsByIds,
    // asset actions
    fetchAgents, fetchMcps, fetchSkills, initAssets, fetchAvailableModels, fetchSessions,
    fetchStudioSessionIds, markStudioSession,
    toggleMcpStatus, addMcpServer, updateMcpServer, removeMcpServer, testMcpServer, fetchMcpTools, fetchMcpLogs,
    upsertAgent, toggleAgent, deleteAgent, setDefaultAgent,
    previewSkillFromGithub, previewSkillFromZip, previewSkillFromJson, confirmSkillImport,
    fetchSkillMarketplace, installMarketplaceSkill, checkSkillUpdate,
    toggleSkill, deleteSkill,
    // session actions
    startSessionFromAgent, selectSession, newChat, deleteSession, renameSession, generateSessionTitle,
    searchSessions, switchSessionModel, loadSessionMessages, sendMessage, stopStreaming, pauseStreaming,
    approveToolCall, rejectToolCall, answerAskRequest,
    initStudioPermissions, setStudioPermissions,
    invokePipelineTool, submitPipelineTask, trackPipelineTask, pollPipelineTask,
    retryPipelineTask, stopPipelinePolling,
  }
})
