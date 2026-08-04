<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NTooltip, NPopover, useMessage, NTag } from 'naive-ui'
import {
  ArrowUpOutline,
  AttachOutline,
  GlobeOutline,
  TerminalOutline,
  SparklesOutline,
  TrashOutline,
  PlayOutline,
  RefreshOutline,
  PersonOutline,
  ExtensionPuzzleOutline,
  DocumentTextOutline,
  HammerOutline,
} from '@vicons/ionicons5'
import SlashCommandMenu from './SlashCommandMenu.vue'
import MentionMenu from './MentionMenu.vue'
import { readActiveMentionQuery } from './mentionQuery'
import { pushRecent, recentRank } from './recentItems'
import McpSelectionMenu from './McpSelectionMenu.vue'
import { useChatStore } from '@/stores/chat'
import { useSiteConfigStore } from '@/stores/site-config'
import { useAgentHubStore } from '@/stores/agentHub'
import { useAuthStore } from '@/stores/auth'
import { useModulesStore } from '@/stores/modules'
import { matchWorkbenchIntent } from '@/config/aiIntents'
import apiClient from '@/api/client'
import type { DataFile } from '@/types'
import type { AgentTemplate, SkillItem } from '@/types/agent'
import type { FileAttachment, MentionDirectory, MentionItem } from './types'

interface Props {
  modelValue: string
  placeholder?: string
  disabled?: boolean
  /** 是否正在流式输出 */
  isStreaming?: boolean
  /** 是否已暂停 */
  isPaused?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '输入需求，@ 引用文件、技能或智能体，/ 查看快捷命令',
  disabled: false,
  isStreaming: false,
  isPaused: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [
    content: string,
    options: {
      attachments?: FileAttachment[]
      enableWebSearch?: boolean
      enableCodeExecution?: boolean
      workbenchIntent?: boolean
      /** @ 显式指定的智能体（本条消息转交给该专家回答） */
      explicitAgentId?: string
      /** @ 挂载到本次对话的技能名 */
      skillNames?: string[]
      mcpMode?: 'off' | 'auto' | 'manual'
      extraMcpServers?: string[]
    },
  ]
  triggerSandbox: []
  stop: []
  pause: []
  resume: []
  regenerate: []
}>()

const chatStore = useChatStore()
const siteConfigStore = useSiteConfigStore()
const agentHub = useAgentHubStore()
const authStore = useAuthStore()
const modulesStore = useModulesStore()
const message = useMessage()
const router = useRouter()

const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()
const isFocused = ref(false)
const showSlashMenu = ref(false)
const slashQuery = ref('')
const slashMenuRef = ref<InstanceType<typeof SlashCommandMenu>>()
const showClearConfirm = ref(false)
const attachments = ref<FileAttachment[]>([])
const uploading = ref(false)

// ===== @ 引用状态 =====
const showMentionMenu = ref(false)
const mentionQuery = ref('')
const mentionActiveIndex = ref(0)
const workspaceFiles = ref<DataFile[]>([])
const workspaceDirectories = ref<MentionDirectory[]>([])
const workspaceSynced = ref(false)
const workspaceSyncAttempted = ref(false)
const mentionLoading = ref(false)
const mentionState = ref<'idle' | 'loading' | 'error' | 'empty' | 'forbidden'>('idle')
/** @ 显式指定的智能体（随下一条消息发送） */
const pendingAgent = ref<AgentTemplate | null>(null)
/** @ 挂载的技能（随下一条消息发送） */
const pendingSkills = ref<SkillItem[]>([])
type McpMode = 'off' | 'auto' | 'manual'
const showMcpMenu = ref(false)
const mcpMenuRef = ref<InstanceType<typeof McpSelectionMenu>>()
const mcpMode = ref<McpMode>('auto')
const extraMcpServers = ref<string[]>([])
const defaultMcpIds = computed(() => new Set(agentHub.currentAgent?.mcp_ids || []))
const extraMcpCount = computed(() => extraMcpServers.value.filter((id) => !defaultMcpIds.value.has(id)).length)
const mcpButtonActive = computed(() => mcpMode.value !== 'auto')
const agentTeamsLocked = computed(() => modulesStore.isModuleLocked(
  'agent_teams', authStore.user?.disabled_modules || [],
))

function syncMcpSelection() {
  mcpMode.value = agentHub.currentSession?.mcp_mode || 'auto'
  extraMcpServers.value = [...(agentHub.currentSession?.extra_mcp_servers || [])]
}

function handleMcpSelection(selection: { mode: McpMode; extraServers: string[] }) {
  mcpMode.value = selection.mode
  extraMcpServers.value = [...selection.extraServers]
  const session = agentHub.currentSession
  if (session) {
    session.mcp_mode = mcpMode.value
    session.extra_mcp_servers = [...extraMcpServers.value]
  }
}

const localValue = ref(props.modelValue)

watch(localValue, (val) => {
  emit('update:modelValue', val)
})

watch(
  () => props.modelValue,
  (val) => {
    if (val !== localValue.value) {
      localValue.value = val
    }
  }
)

watch(localValue, () => {
  nextTick(autoResize)
  detectSlashCommand()
  detectMention()
})

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

const canSend = computed(
  () =>
    localValue.value.trim().length > 0 ||
    attachments.value.length > 0 ||
    pendingAgent.value !== null ||
    pendingSkills.value.length > 0,
)

function handleKeydown(e: KeyboardEvent) {
  if (showMcpMenu.value && e.key === 'Escape') {
    e.preventDefault()
    showMcpMenu.value = false
    return
  }
  if (showMcpMenu.value && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
    e.preventDefault()
    mcpMenuRef.value?.moveSelection(e.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (showMcpMenu.value && e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    mcpMenuRef.value?.selectCurrent()
    return
  }
  if (showSlashMenu.value) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      slashMenuRef.value?.moveSelection(e.key === 'ArrowDown' ? 1 : -1)
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      slashMenuRef.value?.selectCurrent()
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      showSlashMenu.value = false
      return
    }
  }

  // @ 补全面板打开时，优先接管方向键 / Enter / Esc
  if (showMentionMenu.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      mentionActiveIndex.value = (mentionActiveIndex.value + 1) % Math.max(mentionItems.value.length, 1)
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      mentionActiveIndex.value =
        (mentionActiveIndex.value - 1 + mentionItems.value.length) % Math.max(mentionItems.value.length, 1)
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const item = mentionItems.value[mentionActiveIndex.value]
      if (item) selectMention(item)
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      showMentionMenu.value = false
      return
    }
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (canSend.value && !props.disabled) {
      handleSend()
    }
  }
  if (e.key === 'Escape') {
    showSlashMenu.value = false
  }
  if (e.key === '/' && localValue.value === '') {
    nextTick(() => {
      showSlashMenu.value = true
      slashQuery.value = ''
    })
  }
}

function detectSlashCommand() {
  const text = localValue.value
  const lastLine = text.split('\n').pop() || ''

  if (lastLine.startsWith('/')) {
    showSlashMenu.value = true
    slashQuery.value = lastLine.slice(1)
  } else {
    showSlashMenu.value = false
  }
}

// ===== @ 引用：检测 / 数据 / 选择 =====

/** 提取光标处活跃的 @ 查询词；不在 @ 上下文中返回 null */
function readMentionQuery(): string | null {
  const el = textareaRef.value
  const text = localValue.value
  const caret = el?.selectionStart ?? text.length
  const before = text.slice(0, caret)
  const committedLabels = [
    ...attachments.value.filter((attachment) => attachment.source === 'workspace').map((attachment) => attachment.name),
    ...(pendingAgent.value ? [pendingAgent.value.name] : []),
    ...pendingSkills.value.map((skill) => skill.name),
  ]
  // 已选择的引用以空格作为提交边界，避免其后的正文再次打开面板；
  // 尚未选择时仍允许目录与文件名包含空格，例如 @docs/report copy.csv。
  return readActiveMentionQuery(before, committedLabels)
}

function detectMention() {
  const q = readMentionQuery()
  if (q === null) {
    showMentionMenu.value = false
    return
  }
  // 与 slash 菜单互斥
  showSlashMenu.value = false
  showMentionMenu.value = true
  mentionQuery.value = q
  mentionActiveIndex.value = 0
  if (workspaceSynced.value || workspaceSyncAttempted.value) searchWorkspaceFiles(q)
  else syncAndSearchWorkspaceFiles(q)
  ensureMentionData()
}

/** 首次打开 @ 面板时加载工作区文件与智能体 / 技能资产 */
async function ensureMentionData() {
  if (!agentHub.agents.length) agentHub.fetchAgents()
  if (!agentHub.skills.length) agentHub.fetchSkills()
}

let mentionSearchRequest = 0
let workspaceSyncPromise: Promise<void> | null = null

async function syncAndSearchWorkspaceFiles(query: string) {
  if (!workspaceSyncPromise) {
    workspaceSyncAttempted.value = true
    workspaceSyncPromise = apiClient.post('/files/sync')
      .then(() => { workspaceSynced.value = true })
      .catch((error) => {
        console.warn('同步工作区文件索引失败，将使用现有索引:', error)
      })
      .finally(() => { workspaceSyncPromise = null })
  }
  await workspaceSyncPromise
  await searchWorkspaceFiles(query)
}

async function searchWorkspaceFiles(query = mentionQuery.value) {
  const requestId = ++mentionSearchRequest
  mentionLoading.value = true
  mentionState.value = 'loading'
  try {
    const res = await apiClient.get<{ items: DataFile[]; directories: MentionDirectory[]; total: number }>('/files/search', {
      params: { q: query, root: '', limit: 50 },
    })
    if (requestId !== mentionSearchRequest) return
    workspaceFiles.value = res.data.items || []
    workspaceDirectories.value = res.data.directories || []
    mentionState.value = workspaceFiles.value.length || workspaceDirectories.value.length ? 'idle' : 'empty'
  } catch (e) {
    if (requestId !== mentionSearchRequest) return
    mentionState.value = (e as { response?: { status?: number } })?.response?.status === 403 ? 'forbidden' : 'error'
    console.error('搜索工作区文件失败:', e)
  } finally {
    if (requestId === mentionSearchRequest) mentionLoading.value = false
  }
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '')
}

function normalizedMentionQuery(query: string): string {
  return normalizePath(query)
}

/** 按文件名与路径模糊匹配；`@/` 中的斜杠表示路径分隔符。 */
function fuzzyMatch(text: string, q: string): boolean {
  const normalizedQuery = normalizedMentionQuery(q).toLowerCase()
  if (!normalizedQuery) return true
  return normalizePath(text).toLowerCase().includes(normalizedQuery)
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * 友好名称：主行禁止裸显 UUID。
 * 名称本身是 UUID 时，回退到路径末段；末段仍是 UUID 时用类型/占位名。
 * 返回 [展示名, uuid 或 null]。
 */
function friendlyName(raw: string, fallbackPath: string, typeHint: string): [string, string | null] {
  const uuid = UUID_RE.test(raw) ? raw : null
  if (!uuid) return [raw, null]
  const segments = normalizePath(fallbackPath).split('/').filter(Boolean)
  const last = segments[segments.length - 1] || ''
  if (last && !UUID_RE.test(last)) return [last, uuid]
  return [`${typeHint}-${uuid.slice(0, 8)}`, uuid]
}

/**
 * @ 面板条目：仅"上下文引用"类（文件夹 / 文件）。
 * Agent / Skill 属于"能力调用"，改由 / 面板分组承载（Part C 语义拆分）。
 */
const mentionItems = computed<MentionItem[]>(() => {
  const q = mentionQuery.value
  const directories: MentionItem[] = workspaceDirectories.value
    .filter((directory) => fuzzyMatch(directory.path, q))
    .slice(0, 20)
    .map((directory) => {
      const [name, uuid] = friendlyName(directory.name || '', directory.path, '未命名目录')
      return {
        kind: 'directory' as const,
        key: `directory-${directory.path}`,
        name,
        description: `${normalizePath(directory.path)}/`,
        uuid: uuid ?? undefined,
        directory,
      }
    })
  const files: MentionItem[] = workspaceFiles.value
    .filter((f) => fuzzyMatch(f.path || `${f.directory ? `${f.directory}/` : ''}${f.original_name}`, q))
    .slice(0, 30)
    .map((f) => {
      const fullPath = f.path || `${f.directory ? `${f.directory}/` : ''}${f.original_name}`
      const [name] = friendlyName(f.original_name || '', fullPath, f.file_type || 'file')
      return {
        kind: 'file' as const,
        key: `file-${f.id}`,
        name,
        description: `${fullPath} · ${formatBytes(f.size)}`,
        uuid: f.id,
        file: f,
      }
    })

  const items = [...directories, ...files]
  const normalizedQuery = normalizedMentionQuery(q).toLowerCase()
  // 排序：查询相关度 → 最近使用置顶 → 名称
  return items.sort((left, right) => {
    const relevance = (item: MentionItem) => {
      if (!normalizedQuery) return 0
      const text = `${item.name} ${item.description}`.toLowerCase()
      return text.startsWith(normalizedQuery) ? 0 : text.includes(normalizedQuery) ? 1 : 2
    }
    return (
      relevance(left) - relevance(right) ||
      recentRank('mention', left.key) - recentRank('mention', right.key) ||
      left.name.localeCompare(right.name, 'zh')
    )
  })
})

function formatBytes(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)}KB`
  return `${size}B`
}

/** 把光标处活跃的 @查询词 替换为 @名称 + 空格，返回是否替换成功 */
function replaceMentionToken(name: string, appendSpace = true): void {
  const el = textareaRef.value
  const text = localValue.value
  const caret = el?.selectionStart ?? text.length
  const before = text.slice(0, caret).replace(/@([^@\n]*)$/, `@${name}${appendSpace ? ' ' : ''}`)
  localValue.value = before + text.slice(caret)
  nextTick(() => {
    if (el) {
      const pos = before.length
      el.focus()
      el.setSelectionRange(pos, pos)
    }
  })
}

function selectMention(item: MentionItem) {
  if (item.kind === 'directory' && item.directory) {
    pushRecent('mention', item.key)
    replaceMentionToken(`${normalizePath(item.directory.path)}/`, false)
    nextTick(() => detectMention())
    return
  } else if (item.kind === 'file' && item.file) {
    pushRecent('mention', item.key)
    const f = item.file
    const fileId = `file://${f.id}`
    const relativePath = normalizePath(f.path || `${f.directory ? `${f.directory}/` : ''}${f.original_name}`)
    // 去重：已引用则不重复添加
    if (!attachments.value.some((a) => a.file_id === fileId)) {
      attachments.value.push({
        name: relativePath || f.original_name,
        size: f.size,
        type: 'application/octet-stream',
        url: `/api/v1/files/${f.id}/download`,
        file_id: fileId,
        source: 'workspace',
      })
    }
    replaceMentionToken(relativePath || f.original_name)
  } else if (item.kind === 'agent' && item.agent) {
    pendingAgent.value = item.agent
    replaceMentionToken(item.agent.name)
  } else if (item.kind === 'skill' && item.skill) {
    if (!pendingSkills.value.some((s) => s.id === item.skill!.id)) {
      pendingSkills.value.push(item.skill)
    }
    replaceMentionToken(item.skill.name)
  }
  showMentionMenu.value = false
}

function removePendingAgent() {
  pendingAgent.value = null
}

function removePendingSkill(idx: number) {
  pendingSkills.value.splice(idx, 1)
}

function handleSlashSelect(command: string) {
  pushRecent('slash', command)
  const text = localValue.value
  const lines = text.split('\n')
  lines[lines.length - 1] = command + ' '
  localValue.value = lines.join('\n')
  showSlashMenu.value = false
  nextTick(() => textareaRef.value?.focus())
}

/**
 * / 面板选中智能体：插入与手动 @ 完全一致的 mention 标签。
 * 与 selectMention 的 agent 分支同款状态（pendingAgent）+ 同款 `@名称 ` 文本，
 * 保证标签渲染与提交数据结构不变；替换的是行首 `/查询词`（而非 @ 查询词）。
 */
function handleSlashSelectAgent(agent: AgentTemplate) {
  pushRecent('slash', `agent-${agent.id}`)
  pendingAgent.value = agent
  const el = textareaRef.value
  const text = localValue.value
  const caret = el?.selectionStart ?? text.length
  const beforeCaret = text.slice(0, caret)
  const replaced = beforeCaret.replace(
    /(^|\n)\/[^\n]*$/,
    (match, prefix: string) => `${prefix}@${agent.name} `,
  )
  localValue.value = replaced + text.slice(caret)
  showSlashMenu.value = false
  nextTick(() => {
    if (el) {
      el.focus()
      el.setSelectionRange(replaced.length, replaced.length)
    }
  })
}

function handleSend() {
  const content = localValue.value.trim()
  const hasPayload =
    content.length > 0 ||
    attachments.value.length > 0 ||
    pendingAgent.value !== null ||
    pendingSkills.value.length > 0
  if (!hasPayload || props.disabled) return

  // Feature 5: 意图匹配 → 自动切换工作台模式
  const workbenchIntent = matchWorkbenchIntent(content)
  if (workbenchIntent) {
    message.info('已为您切换至工作台模式，便于跟踪任务进度')
  }

  emit('send', content, {
    attachments: attachments.value.length ? [...attachments.value] : undefined,
    enableWebSearch: chatStore.enableWebSearch,
    workbenchIntent,
    explicitAgentId: pendingAgent.value?.id,
    skillNames: pendingSkills.value.length ? pendingSkills.value.map((s) => s.name) : undefined,
    mcpMode: mcpMode.value,
    extraMcpServers: mcpMode.value === 'manual' ? [...extraMcpServers.value] : [],
  })
  localValue.value = ''
  attachments.value = []
  pendingAgent.value = null
  pendingSkills.value = []
  showMentionMenu.value = false
  showMcpMenu.value = false
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

function handleStop() {
  emit('stop')
}

function handleResume() {
  emit('resume')
}

function handleRegenerate() {
  emit('regenerate')
}

let blurTimer: ReturnType<typeof setTimeout> | null = null

function handleBlur(e: FocusEvent) {
  const nextTarget = e.relatedTarget as Node | null
  if (nextTarget && (e.currentTarget as HTMLElement).closest('.kimi-chat-input')?.contains(nextTarget)) {
    return
  }
  if (blurTimer) clearTimeout(blurTimer)
  blurTimer = setTimeout(() => {
    isFocused.value = false
    showSlashMenu.value = false
    showMentionMenu.value = false
  }, 200)
}

function handleAttach() {
  fileInputRef.value?.click()
}

async function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length) return
  uploading.value = true
  for (const file of Array.from(files)) {
    const formData = new FormData()
    formData.append('file', file)
    // 带上当前会话 ID，后端会把会话短标记写入上传文件名，便于按会话检索；
    // 仅真实后端会话 ID 才传（sess- 开头的是尚未落库的临时 ID，无检索意义）
    const sid = agentHub.currentSessionId
    if (sid && !sid.startsWith('sess-')) formData.append('session_id', sid)
    try {
      const res = await apiClient.post('/files/chat-upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      attachments.value.push({
        name: file.name,
        size: file.size,
        type: file.type || 'application/octet-stream',
        url: res.data.url,
        file_id: res.data.id,
      })
    } catch (err: any) {
      message.error(`上传 ${file.name} 失败: ${err?.response?.data?.detail || err.message}`)
    }
  }
  uploading.value = false
  input.value = ''
}

function removeAttachment(idx: number) {
  attachments.value.splice(idx, 1)
}

async function handleWebSearchToggle() {
  if (chatStore.enableWebSearch) {
    chatStore.toggleWebSearch()
    return
  }
  try {
    const { data } = await apiClient.get<{ available: boolean }>('/chat/web-search/availability')
    if (data.available) {
      chatStore.toggleWebSearch()
      return
    }
  } catch {
    // 配置检查失败时保守地阻止开关，避免用户以为已经联网。
  }
  message.warning('请先到 AI 配置中心 · 资源中心 · 联网搜索 配置服务商')
  void router.push('/admin/ai-config/resources')
}

function handleSandboxStub() {
  message.info('代码执行请在生成代码后点击代码块“运行”按钮')
}

function insertAgentTeamsCaseTemplate() {
  const template = '请将以下工作转为协作 Case：\n- 交付目标：\n- 项目 ID：\n- 流程 ID：\n- 需要的审批/验收：\n'
  localValue.value = localValue.value.trim() ? `${localValue.value}\n\n${template}` : template
  nextTick(() => {
    textareaRef.value?.focus()
    autoResize()
  })
}

function handleClearConfirm() {
  localValue.value = ''
  showClearConfirm.value = false
  nextTick(() => {
    if (textareaRef.value) textareaRef.value.style.height = 'auto'
  })
}

onMounted(() => {
  siteConfigStore.fetchSiteConfig()
  void modulesStore.ensureLoaded()
  syncMcpSelection()
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onUnmounted(() => {
  if (blurTimer) clearTimeout(blurTimer)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target as Element | null
  if (showMcpMenu.value && target && !target.closest('.mcp-selection-menu') && !target.closest('.mcp-toolbar-trigger')) {
    showMcpMenu.value = false
  }
}

watch(() => agentHub.currentSessionId, syncMcpSelection)
</script>

<template>
  <div
    class="kimi-chat-input"
    :class="{
      focused: isFocused,
      disabled,
      'deep-thinking': chatStore.deepThinking,
      'popup-open': showSlashMenu || showMentionMenu || showMcpMenu,
    }"
  >
    <Transition name="composer-menu" appear>
      <SlashCommandMenu
        v-if="showSlashMenu"
        ref="slashMenuRef"
        :query="slashQuery"
        :agents="agentHub.activeAgents"
        @select="handleSlashSelect"
        @select-agent="handleSlashSelectAgent"
        @close="showSlashMenu = false"
      />
    </Transition>

    <Transition name="composer-menu" appear>
      <McpSelectionMenu
        v-if="showMcpMenu"
        ref="mcpMenuRef"
        :mode="mcpMode"
        :extra-servers="extraMcpServers"
        @update="handleMcpSelection"
        @close="showMcpMenu = false"
      />
    </Transition>

    <Transition name="composer-menu" appear>
      <MentionMenu
        v-if="showMentionMenu"
        :items="mentionItems"
        :active-index="mentionActiveIndex"
        :loading="mentionLoading"
        :state="mentionState"
        :query="mentionQuery"
        @select="selectMention"
        @hover="mentionActiveIndex = $event"
          @retry="searchWorkspaceFiles"
        @close="showMentionMenu = false"
      />
    </Transition>

    <div class="input-wrapper">
      <textarea
        ref="textareaRef"
        v-model="localValue"
        class="chat-textarea"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @focus="isFocused = true"
        @blur="handleBlur"
        @keydown="handleKeydown"
      />
    </div>

    <!-- accept 镜像后端 _CHAT_UPLOAD_ALLOWED_SUFFIXES（含建树格式），仅作系统选择框引导，真正拦截仍以后端校验为准 -->
    <input
      ref="fileInputRef"
      type="file"
      multiple
      accept=".png,.jpg,.jpeg,.gif,.svg,.webp,.bmp,.ico,.pdf,.txt,.md,.doc,.docx,.csv,.tsv,.json,.yaml,.yml,.fastq,.fq,.fasta,.fa,.fna,.faa,.ffn,.bam,.cram,.sam,.vcf,.gff,.gff3,.gtf,.bed,.h5ad,.rds,.gz,.zip,.tar,.bz2,.xz,.nwk,.newick,.nhx,.nh,.tree,.tre,.trees,.dnd,.nex,.nexus,.iqtree,.treefile,.contree,.bionj,.mldist,.ufboot,.log,.aln,.phy,.phylip,.sto"
      style="display: none"
      @change="handleFileChange"
    />

    <div
      v-if="attachments.length || pendingAgent || pendingSkills.length"
      class="ref-bar"
    >
      <!-- @ 指定的智能体 -->
      <NTag
        v-if="pendingAgent"
        size="small"
        round
        closable
        class="ref-chip ref-agent"
        @close="removePendingAgent"
      >
        <template #icon>
          <n-icon><PersonOutline /></n-icon>
        </template>
        {{ pendingAgent.name }}
      </NTag>

      <!-- @ 挂载的技能 -->
      <NTag
        v-for="(sk, idx) in pendingSkills"
        :key="`skill-${sk.id}`"
        size="small"
        round
        closable
        class="ref-chip ref-skill"
        @close="removePendingSkill(idx)"
      >
        <template #icon>
          <n-icon><ExtensionPuzzleOutline /></n-icon>
        </template>
        {{ sk.name }}
      </NTag>

      <!-- 附件 / @ 引用的工作区文件 -->
      <NTag
        v-for="(att, idx) in attachments"
        :key="`att-${idx}`"
        size="small"
        round
        closable
        class="ref-chip"
        :class="{ 'ref-file': att.source === 'workspace' }"
        :disabled="uploading"
        @close="removeAttachment(idx)"
      >
        <template v-if="att.source === 'workspace'" #icon>
          <n-icon><DocumentTextOutline /></n-icon>
        </template>
        {{ att.name }}
      </NTag>
    </div>

    <div class="input-toolbar">
      <div class="toolbar-left">
        <!-- 附件上传 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn upload-btn" :loading="uploading" @click="handleAttach">
              <n-icon size="18"><AttachOutline /></n-icon>
            </n-button>
          </template>
          上传文件
        </n-tooltip>

        <!-- 联网搜索 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              text
              class="toolbar-btn web-search-btn"
              :class="{ active: chatStore.enableWebSearch }"
              @click="handleWebSearchToggle"
            >
              <n-icon size="18"><GlobeOutline /></n-icon>
            </n-button>
          </template>
          {{ chatStore.enableWebSearch ? '关闭联网搜索' : '开启联网搜索' }}
        </n-tooltip>

        <!-- 代码执行提示 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn sandbox-btn" @click="handleSandboxStub">
              <n-icon size="18"><TerminalOutline /></n-icon>
            </n-button>
          </template>
          代码执行
        </n-tooltip>

        <n-tooltip v-if="!agentTeamsLocked" trigger="hover">
          <template #trigger>
            <n-button
              text
              class="toolbar-btn case-btn"
              aria-label="转为协作 Case"
              @click="insertAgentTeamsCaseTemplate"
            >
              <span class="btn-label">转为协作 Case</span>
            </n-button>
          </template>
          插入协作 Case 信息模板；发送后仍需确认创建
        </n-tooltip>

        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              text
              class="toolbar-btn mcp-toolbar-trigger"
              :class="{ active: mcpButtonActive }"
              @click="showMcpMenu = !showMcpMenu"
            >
              <span class="mcp-button-icon">
                <n-icon size="18"><HammerOutline /></n-icon>
                <span v-if="mcpMode === 'manual' && extraMcpCount" class="mcp-count-badge">+{{ extraMcpCount }}</span>
              </span>
            </n-button>
          </template>
          MCP 工具：{{ mcpMode === 'off' ? '关闭' : mcpMode === 'manual' ? '手动选择' : '自动' }}
        </n-tooltip>

        <!-- 深度思考 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              text
              class="toolbar-btn deep-thinking-btn"
              :class="{ active: chatStore.deepThinking }"
              @click="chatStore.toggleDeepThinking()"
            >
              <n-icon size="18"><SparklesOutline /></n-icon>
              <span class="btn-label">深度思考</span>
            </n-button>
          </template>
          {{ chatStore.deepThinking ? '关闭深度思考' : '开启深度思考' }}
        </n-tooltip>
      </div>

      <div class="toolbar-right">
        <!-- 清空 -->
        <n-popover v-model:show="showClearConfirm" trigger="click" placement="top-end" :width="200">
          <template #trigger>
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-button text class="toolbar-btn clear-btn" :disabled="!localValue">
                  <n-icon size="18"><TrashOutline /></n-icon>
                </n-button>
              </template>
              清空输入
            </n-tooltip>
          </template>
          <div style="text-align: center">
            <p style="margin: 0 0 10px; font-size: 13px">确认清空输入框内容？</p>
            <div style="display: flex; gap: 8px; justify-content: center">
              <n-button size="small" @click="showClearConfirm = false">取消</n-button>
              <n-button size="small" type="error" @click="handleClearConfirm">确认清空</n-button>
            </div>
          </div>
        </n-popover>

        <!-- 流式输出中：发送按钮切换为停止方块，立即中止当前请求 -->
        <n-tooltip v-if="isStreaming" trigger="hover">
          <template #trigger>
            <n-button
              circle
              class="send-btn stop-btn"
              aria-label="停止生成"
              @click="handleStop"
            >
              <span class="stop-square" aria-hidden="true" />
            </n-button>
          </template>
          停止生成
        </n-tooltip>

        <!-- 已暂停：继续 + 重新生成 -->
        <template v-else-if="isPaused">
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-button circle class="send-btn resume-btn" @click="handleResume">
                <template #icon>
                  <n-icon size="18"><PlayOutline /></n-icon>
                </template>
              </n-button>
            </template>
            继续生成
          </n-tooltip>
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-button circle class="send-btn regenerate-btn" @click="handleRegenerate">
                <template #icon>
                  <n-icon size="18"><RefreshOutline /></n-icon>
                </template>
              </n-button>
            </template>
            重新生成
          </n-tooltip>
        </template>

        <!-- 默认：发送按钮 -->
        <n-button
          v-else
          circle
          class="send-btn"
          :class="{ active: canSend }"
          :disabled="!canSend || disabled"
          @click="handleSend"
        >
          <template #icon>
            <n-icon size="18"><ArrowUpOutline /></n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <div class="input-hint">
      <template v-if="isPaused">
        <span class="paused-hint">生成已暂停</span>
      </template>
      <template v-else>
        {{ siteConfigStore.aiInputHint }}
      </template>
    </div>

  </div>
</template>

<style scoped lang="scss">
.kimi-chat-input {
  position: relative;
  z-index: 20;
  isolation: isolate;
  background: var(--chat-input-bg);
  border: 1px solid var(--chat-input-border);
  border-radius: var(--chat-radius-xl, 20px);
  padding: 12px 16px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;

  &.focused {
    border-color: var(--stardust-blue);
    box-shadow: 0 0 0 3px rgba(46, 91, 255, 0.12);
  }

  &.deep-thinking {
    border-color: var(--stardust-blue);
    box-shadow: 0 0 0 3px rgba(46, 91, 255, 0.12);
  }

  &.disabled {
    opacity: 0.6;
    pointer-events: none;
  }

  .input-wrapper {
    position: relative;
    z-index: 1;
    margin-bottom: 8px;
  }

  .ref-bar,
  .input-toolbar,
  .input-hint {
    position: relative;
    z-index: 1;
  }

  &.popup-open {
    border-radius: var(--chat-radius-xl, 20px);
  }

  &.popup-open :deep(.slash-command-menu),
  &.popup-open :deep(.mention-menu),
  &.popup-open :deep(.mcp-selection-menu) {
    position: relative;
    left: auto;
    right: auto;
    bottom: auto;
    width: calc(100% + 32px);
    margin: -12px -16px 12px;
    border: none;
    border-bottom: 1px solid var(--chat-input-border);
    border-radius: var(--chat-radius-xl, 20px) var(--chat-radius-xl, 20px) 0 0;
    box-shadow: none;
  }

  :deep(.composer-menu-enter-active),
  :deep(.composer-menu-leave-active) {
    transition: opacity 180ms ease-out, transform 180ms ease-out;
    transform-origin: bottom;
  }

  :deep(.composer-menu-enter-from),
  :deep(.composer-menu-leave-to) {
    opacity: 0;
    transform: translateY(8px);
  }

  .ref-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;

    .ref-chip {
      max-width: 240px;
    }

    .ref-file {
      color: var(--arco-primary, #4c6fff);
      background: var(--arco-primary-light, rgba(76, 111, 255, 0.12));
    }

    .ref-agent {
      color: var(--icon-visualization, #8b5cf6);
      background: var(--icon-purple-bg, rgba(139, 92, 246, 0.12));
    }

    .ref-skill {
      color: #059669;
      background: var(--icon-green-bg, rgba(5, 150, 105, 0.12));
    }
  }

  .chat-textarea {
    width: 100%;
    min-height: 24px;
    max-height: 200px;
    background: transparent;
    border: none;
    outline: none;
    color: var(--chat-text-primary);
    font-size: 15px;
    line-height: 1.6;
    resize: none;
    font-family: inherit;

    &::placeholder {
      color: var(--chat-text-muted);
    }

    &::-webkit-scrollbar {
      width: 4px;
    }

    &::-webkit-scrollbar-thumb {
      background: var(--chat-border);
      border-radius: 2px;
    }
  }

  .input-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1px solid var(--chat-border);
    padding-top: 8px;

    .toolbar-left,
    .toolbar-right {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .toolbar-btn {
      color: var(--chat-text-secondary);
      padding: 4px 8px;
      border-radius: 8px;
      transition: all 0.15s ease;

      &:hover {
        color: var(--chat-text-primary);
        background: var(--chat-surface-hover);
      }

      &.active {
        color: var(--stardust-blue);
        background: rgba(46, 91, 255, 0.1);
        border: 1px solid rgba(46, 91, 255, 0.35);
      }

      .btn-label {
        margin-left: 4px;
        font-size: 13px;
      }

      &.deep-thinking-btn.active {
        color: var(--stardust-blue);
        background: rgba(46, 91, 255, 0.1);
        border: 1px solid rgba(46, 91, 255, 0.35);
      }

      &.clear-btn:hover {
        color: var(--chat-error);
      }
    }

    .mcp-toolbar-trigger {
      position: relative;
    }

    .mcp-button-icon {
      position: relative;
      display: inline-flex;
    }

    .mcp-count-badge {
      position: absolute;
      top: -8px;
      right: -10px;
      min-width: 15px;
      padding: 0 3px;
      color: #fff;
      background: var(--chat-accent);
      border-radius: 8px;
      font-size: 9px;
      line-height: 15px;
      text-align: center;
    }

    .upload-btn { color: var(--stardust-purple); }
    .web-search-btn { color: #0891B2; }
    .sandbox-btn { color: #64748B; }
    .case-btn { color: var(--stardust-purple); }

    .send-btn {
      width: 32px;
      height: 32px;
      color: var(--chat-text-muted);
      background: var(--chat-surface);
      transition: all 0.2s ease;

      &:hover,
      &.active {
        color: #fff;
        background: var(--stardust-gradient);
        box-shadow: 0 4px 12px rgba(46, 91, 255, 0.35);
      }

      &:disabled {
        color: #fff;
        background: #d4dbf5;
        opacity: 1;
        cursor: not-allowed;
      }

      &.stop-btn {
        color: #fff;
        background: var(--stardust-gradient);
      }

      .stop-square {
        display: block;
        width: 11px;
        height: 11px;
        background: var(--text-on-primary, #fff);
        border-radius: 2px;
      }

      &.resume-btn {
        color: #fff;
        background: var(--arco-success, #00B42A);
      }

      &.regenerate-btn {
        color: var(--chat-text-secondary);
        background: var(--chat-surface);

        &:hover {
          color: #fff;
          background: var(--brand-gradient);
        }
      }
    }
  }

  .input-hint {
    text-align: center;
    font-size: 12px;
    color: var(--chat-text-muted);
    margin-top: 8px;
    line-height: 1.4;
  }

  .paused-hint {
    color: var(--stardust-blue);
    font-weight: 500;
  }
}

</style>
