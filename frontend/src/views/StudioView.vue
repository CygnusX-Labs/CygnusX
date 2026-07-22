<script setup lang="ts">
/**
 * StudioView — OmicStudio AI 分析工作台（三栏布局，/studio/:sessionId?）
 *
 * 顶栏：会话名 / 绑定智能体徽章 / 模型 / 沙盒状态灯 / 返回与栏位开关
 * 左栏：工作台会话列表 + 工作区文件树（懒加载目录，点击预览）
 * 中栏：对话执行流（复用 agentHub store + KimiMessageList/KimiChatInput，
 *       Studio 代码工具经 provide 上下文渲染为 StudioCodeCard）
 * 右栏：产物列表 + 待办计划（P1 占位）+ 沙盒状态块
 */
import { ref, reactive, computed, watch, onMounted, onUnmounted, provide, nextTick } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { NButton, NCheckbox, NIcon, NInput, NSwitch, NTag, NTooltip, NModal, NSpin, useMessage } from 'naive-ui'
import {
  ArrowBackOutline, RefreshOutline, FileTrayStackedOutline, ShareSocialOutline,
  PrintOutline, CloseCircleOutline, ConstructOutline, ChevronBackOutline, ChevronForwardOutline,
  ChatbubbleEllipsesOutline, GridOutline, CodeSlashOutline, PowerOutline,
} from '@vicons/ionicons5'
import KimiMessageList from '@/components/ai-chat/KimiMessageList.vue'
import KimiChatInput from '@/components/ai-chat/KimiChatInput.vue'
import FilePickerModal from '@/components/FilePickerModal.vue'
import StudioFileTree from '@/components/studio/StudioFileTree.vue'
import StudioArtifactsPanel from '@/components/studio/StudioArtifactsPanel.vue'
import StudioWorkspaceEditor from '@/components/studio/StudioWorkspaceEditor.vue'
import { StudioContextKey } from '@/components/studio/context'
import { studioApi, type StudioSessionDTO, type SandboxStatus } from '@/api/studio'
import { useAgentHubStore } from '@/stores/agentHub'
import { useAuthStore } from '@/stores/auth'
import type { FileAttachment, ToolCall } from '@/components/ai-chat/types'
import type { FilePickerItem } from '@/types'

const route = useRoute()
const router = useRouter()
const store = useAgentHubStore()
const authStore = useAuthStore()
const message = useMessage()

const sessionId = computed(() => (route.params.sessionId as string) || '')

const loading = ref(true)
const studioSessions = ref<StudioSessionDTO[]>([])
const sandboxStatus = ref<SandboxStatus>('absent')
const sandboxMetrics = ref({ cpu_percent: 0, memory_percent: 0, memory_used: 0, memory_limit: 0 })
const workspaceId = ref<string | null>(null)
const shareActive = ref(false)
const shareExpiresAt = ref<string | null>(null)
const input = ref('')
const longRunSeconds = ref(0)
const longRunPlaceholder = computed(() => {
  if (!store.isStreaming) return `向 ${agent.value?.name || 'AI 助手'} 描述分析任务`
  if (longRunSeconds.value > 90) return '正在跑长任务，去倒杯咖啡？'
  if (longRunSeconds.value > 30) return '沙盒正在计算，代码和产物会实时同步…'
  return 'AI 正在执行，稍等片刻…'
})
let longRunTimer: ReturnType<typeof setInterval> | null = null
const showFilePicker = ref(false)
const importingFile = ref(false)
const showExtractSkill = ref(false)
const extractingSkill = ref(false)
const extractSkillForm = reactive({
  path: '',
  skill_id: '',
  name: '',
  description: '',
  usage_instructions: '',
  category: 'studio',
  icon: '🧪',
  confirm_no_secrets: false,
})

const fileTreeKey = ref(0)
const artifactsKey = ref(0)

const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const rightSections = reactive({ artifacts: true, plan: true, sandbox: true })
const leftWidth = ref(260)
const rightWidth = ref(300)

type StudioViewMode = 'chat' | 'split' | 'code'
const viewMode = ref<StudioViewMode>('chat')
const splitRatio = ref(40)
const chatDrawerOpen = ref(false)
const workspaceEditorRef = ref<InstanceType<typeof StudioWorkspaceEditor> | null>(null)
const followAi = ref(true)
const terminalCollapsed = ref(false)
const hibernateOnLeave = ref(true)

// ---------- 权限模式（supervised/auto，P1 HITL） ----------
const permissionMode = computed(() => store.studioPermissions.mode)
const isAutoMode = computed(() => permissionMode.value === 'auto')
const switchingPermissions = ref(false)

async function handlePermissionToggle(auto: boolean) {
  if (switchingPermissions.value) return
  switchingPermissions.value = true
  try {
    await store.setStudioPermissions(auto ? 'auto' : 'supervised')
    if (auto) {
      message.warning('已切换到放权模式：所有工具将自动执行，不再等待批准')
    } else {
      message.success('已切换到监督模式：关键操作需你批准后执行')
    }
  } catch {
    message.error('权限模式切换失败，请重试')
  } finally {
    switchingPermissions.value = false
  }
}

function toggleRightSection(section: keyof typeof rightSections) {
  rightSections[section] = !rightSections[section]
}

function persistUiState() {
  if (!sessionId.value) return
  void studioApi.updateUi(sessionId.value, {
    view_mode: viewMode.value,
    split_ratio: splitRatio.value,
    follow_ai: followAi.value,
    terminal_collapsed: terminalCollapsed.value,
  }).catch(() => {})
}

function modeStorageKey(id = sessionId.value) { return `omichub:studio:${id}:view-mode` }
function handleTerminalCollapsedChanged(collapsed: boolean) {
  terminalCollapsed.value = collapsed
  persistUiState()
}
function setViewMode(mode: StudioViewMode) {
  viewMode.value = mode
  if (sessionId.value) localStorage.setItem(modeStorageKey(), mode)
  if (mode !== 'code') chatDrawerOpen.value = false
  persistUiState()
}
async function openFileInEditor(path: string, options: { pin?: boolean; externallyChanged?: boolean } = {}) {
  if (viewMode.value === 'chat') setViewMode('split')
  await nextTick()
  await workspaceEditorRef.value?.openFile(path, options.pin, options.externallyChanged)
}
function handleEditorRunStarted(tool: ToolCall) {
  const current = store.currentSession
  if (!current) return
  current.messages.push({
    id: `studio-editor-run-${Date.now()}`,
    role: 'assistant',
    content: '',
    modelName: 'OmicStudio',
    toolCalls: [tool],
    createdAt: new Date().toISOString(),
  })
}

function handleEditorSaved(path: string) {
  const current = store.currentSession
  if (!current) return
  current.messages.push({
    id: `studio-edit-${Date.now()}`,
    role: 'system',
    content: `✏️ 你修改了 ${path}`,
    createdAt: new Date().toISOString(),
  })
}

// ---------- 工作区刷新（工具结果 / 重跑 / 消息流结束后触发） ----------
function refreshWorkspace() {
  fileTreeKey.value += 1
  artifactsKey.value += 1
  refreshStatus()
  refreshStudioSessions()
}
provide(StudioContextKey, { sessionId, refreshWorkspace, openFileInEditor })

async function refreshStatus() {
  if (!sessionId.value) return
  try {
    const detail = await studioApi.getSession(sessionId.value)
    const wasRunning = sandboxStatus.value === 'running'
    sandboxStatus.value = detail.sandbox_status
    sandboxMetrics.value = detail.sandbox_metrics || { cpu_percent: 0, memory_percent: 0, memory_used: 0, memory_limit: 0 }
    workspaceId.value = detail.workspace_id
    if (!wasRunning && detail.sandbox_status === 'running' && store.isStreaming) message.success('沙盒已点火，工作区准备就绪 🚀')
    store.currentPlan = detail.plan?.steps || []
    if (detail.ui) {
      followAi.value = detail.ui.follow_ai
      terminalCollapsed.value = detail.ui.terminal_collapsed
      hibernateOnLeave.value = detail.ui.hibernate_on_leave
      splitRatio.value = detail.ui.split_ratio
      const serverMode = detail.ui.view_mode
      if (serverMode === 'chat' || serverMode === 'split' || serverMode === 'code') viewMode.value = serverMode
    }
    shareActive.value = detail.share?.active || false
    shareExpiresAt.value = detail.share?.expires_at || null
  } catch {
    // 状态刷新失败不阻塞页面
  }
}

async function refreshStudioSessions() {
  try {
    studioSessions.value = await studioApi.listSessions()
  } catch {
    studioSessions.value = []
  }
}

// ---------- 会话进入 ----------
async function enterSession(id: string) {
  try {
    const detail = await studioApi.getSession(id)
    const wasRunning = sandboxStatus.value === 'running'
    sandboxStatus.value = detail.sandbox_status
    sandboxMetrics.value = detail.sandbox_metrics || { cpu_percent: 0, memory_percent: 0, memory_used: 0, memory_limit: 0 }
    workspaceId.value = detail.workspace_id
    if (!wasRunning && detail.sandbox_status === 'running' && store.isStreaming) message.success('沙盒已点火，工作区准备就绪 🚀')
    store.currentPlan = detail.plan?.steps || []
    if (detail.ui) {
      followAi.value = detail.ui.follow_ai
      terminalCollapsed.value = detail.ui.terminal_collapsed
      hibernateOnLeave.value = detail.ui.hibernate_on_leave
      splitRatio.value = detail.ui.split_ratio
      const serverMode = detail.ui.view_mode
      if (serverMode === 'chat' || serverMode === 'split' || serverMode === 'code') viewMode.value = serverMode
    }
    shareActive.value = detail.share?.active || false
    shareExpiresAt.value = detail.share?.expires_at || null
    store.initStudioPermissions(detail.permissions?.mode)
    // 复用 agentHub 会话编排：注入 studio 会话后走统一的 selectSession/sendMessage 路径
    if (!store.sessions.find((s) => s.id === id)) {
      store.sessions.unshift({
        id,
        title: detail.session.title,
        agent_id: detail.session.agent_id || '',
        messages: [],
        created_at: detail.session.created_at,
        updated_at: detail.session.updated_at,
        model_id: detail.session.model_id || undefined,
      })
    }
    await store.selectSession(id)
  } catch {
    message.error('Studio 会话不存在或无权访问')
    if (studioSessions.value.length) {
      router.replace({ name: 'studio', params: { sessionId: studioSessions.value[0].session_id } })
    } else {
      router.replace({ name: 'studio' })
    }
  }
}

watch(
  sessionId,
  async (id) => {
    const savedMode = id ? localStorage.getItem(modeStorageKey(id)) : null
    viewMode.value = savedMode === 'split' || savedMode === 'code' ? savedMode : 'chat'
    loading.value = true
    await refreshStudioSessions()
    if (!id) {
      // /studio 无参：有历史会话则跳到最近一个，否则展示空态引导
      if (studioSessions.value.length) {
        router.replace({ name: 'studio', params: { sessionId: studioSessions.value[0].session_id } })
        return
      }
      loading.value = false
      return
    }
    await enterSession(id)
    loading.value = false
  },
  { immediate: true },
)

let statusTimer: ReturnType<typeof setInterval> | null = null

function handleStudioFileChanged(event: Event) {
  const detail = (event as CustomEvent<{ sessionId: string; path: string }>).detail
  if (!detail || detail.sessionId !== sessionId.value || !detail.path) return
  refreshWorkspace()
  if (followAi.value) {
    void openFileInEditor(detail.path, { pin: true, externallyChanged: true })
  } else {
    void workspaceEditorRef.value?.markFileChanged(detail.path)
  }
}

onMounted(async () => {
  // 智能体徽章 / 模型名 / 发消息均依赖这两项资产
  if (!store.agents.length) await store.fetchAgents(true)
  if (!store.availableModels.length) await store.fetchAvailableModels()
  statusTimer = setInterval(refreshStatus, 10_000)
  longRunTimer = setInterval(() => { if (store.isStreaming) longRunSeconds.value += 1; else longRunSeconds.value = 0 }, 1000)
  window.addEventListener('omichub:studio-file-changed', handleStudioFileChanged)
})

async function hibernateCurrentSandbox(showFeedback = false) {
  const id = sessionId.value
  if (!id || store.isStreaming || !hibernateOnLeave.value) return
  try {
    const result = await studioApi.hibernateSession(id)
    if (result.status === 'hibernated') {
      sandboxStatus.value = 'absent'
      if (showFeedback) message.success('沙盒已休眠，工作区快照已保留')
    }
  } catch {
    if (showFeedback) message.warning('沙盒暂未释放，将由空闲回收任务处理')
  }
}

onBeforeRouteLeave(async () => {
  await hibernateCurrentSandbox(false)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  statusTimer = null
  if (longRunTimer) clearInterval(longRunTimer)
  longRunTimer = null
  window.removeEventListener('omichub:studio-file-changed', handleStudioFileChanged)
  void hibernateCurrentSandbox(false)
})

// 消息流结束后刷新文件树 / 产物 / 沙盒状态
watch(
  () => store.isStreaming,
  (cur, prev) => {
    if (prev && !cur) refreshWorkspace()
  },
)

// ---------- 顶栏信息 ----------
const session = computed(() => store.currentSession)
const agent = computed(() => (session.value ? store.getAgent(session.value.agent_id) : null))

const modelName = computed(() => {
  const id = session.value?.model_id
  if (id) {
    const found = store.availableModels.find((m) => m.id === id)
    if (found) return found.name
  }
  return agent.value?.model_engine || '默认模型'
})

const userDisplayName = computed(() => authStore.user?.nickname || authStore.user?.username || '我')
const userAvatarUrl = computed(() => authStore.user?.avatar_url || '')

/** 沙盒状态灯：流式执行中按 启动中/运行中 展示，空闲展示真实状态 */
const statusInfo = computed(() => {
  if (store.isStreaming) {
    return sandboxStatus.value === 'running'
      ? { icon: '🟢', label: '运行中' }
      : { icon: '🟡', label: '启动中' }
  }
  switch (sandboxStatus.value) {
    case 'running': return { icon: '🟢', label: '运行中' }
    case 'stopped': return { icon: '⚪', label: '已回收' }
    case 'unavailable': return { icon: '🔴', label: '不可用' }
    default: return { icon: '🌙', label: '已休眠，工作区已保留' }
  }
})

// ---------- 交互 ----------
function handleSend(
  content: string,
  options: { attachments?: FileAttachment[]; enableWebSearch?: boolean; enableCodeExecution?: boolean } = {},
) {
  if (!content.trim() && !options.attachments?.length) return
  if (store.isStreaming) return
  store.sendMessage(content, options)
  input.value = ''
}

function handleInsertArtifact(path: string) {
  input.value = (input.value ? `${input.value}\n` : '') + `请查看产物文件 ${path}`
  message.info(`已插入引用：${path}`)
}

function handleInsertWorkspaceReference(path: string) {
  input.value = (input.value ? `${input.value}\n` : '') + `请查看工作区文件 ${path}`
  message.info(`已插入工作区引用：${path}`)
}

async function handleImportFiles(items: FilePickerItem[]) {
  if (!sessionId.value || !items.length) return
  importingFile.value = true
  const imported: string[] = []
  try {
    for (const item of items) {
      const result = await studioApi.importDataFile(sessionId.value, {
        file_id: item.id,
        name: item.original_name,
      })
      imported.push(result.sandbox_path)
    }
    if (imported.length) {
      const references = imported.map((path) => `已引入文件：${path}`).join('\n')
      input.value = input.value ? `${input.value}\n${references}` : references
      refreshWorkspace()
      message.success(`已引入 ${imported.length} 个文件`)
    }
  } catch {
    message.error('文件引入失败，请确认文件仍可用')
  } finally {
    importingFile.value = false
  }
}

function planStatusIcon(status: 'pending' | 'in_progress' | 'done'): string {
  if (status === 'done') return '☑'
  if (status === 'in_progress') return '◐'
  return '☐'
}

function openExtractSkill() {
  extractSkillForm.path = previewPath.value && /\.(py|r|R|sh|bash)$/.test(previewPath.value)
    ? previewPath.value
    : ''
  extractSkillForm.confirm_no_secrets = false
  showExtractSkill.value = true
}

async function handleExtractSkill() {
  if (!sessionId.value) return
  if (!extractSkillForm.path || !extractSkillForm.skill_id || !extractSkillForm.name) {
    message.warning('请填写脚本路径、Skill ID 和名称')
    return
  }
  if (!extractSkillForm.confirm_no_secrets) {
    message.warning('请先确认脚本不包含密钥、密码或用户隐私数据')
    return
  }
  extractingSkill.value = true
  try {
    const skill = await studioApi.extractSkill(sessionId.value, { ...extractSkillForm })
    showExtractSkill.value = false
    message.success(`已提炼并启用 Skill：${skill.name}`)
  } catch {
    message.error('Skill 提炼失败，请检查脚本路径、ID 唯一性和敏感信息')
  } finally {
    extractingSkill.value = false
  }
}

async function handleShare() {
  if (!sessionId.value) return
  if (shareActive.value && !window.confirm('创建新分享链接会立即使旧链接失效，是否继续？')) return
  try {
    const share = await studioApi.createShare(sessionId.value)
    const url = `${window.location.origin}${share.share_path}`
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(url)
      message.success('只读分享链接已复制，有效期 7 天')
    } else {
      window.prompt('请复制只读分享链接', url)
    }
    shareActive.value = true
    shareExpiresAt.value = share.expires_at
  } catch {
    message.error('分享链接创建失败')
  }
}

async function handleRevokeShare() {
  if (!sessionId.value || !shareActive.value) return
  if (!window.confirm('撤销后当前分享链接将立即失效，是否继续？')) return
  try {
    await studioApi.revokeShare(sessionId.value)
    shareActive.value = false
    shareExpiresAt.value = null
    message.success('分享链接已撤销')
  } catch {
    message.error('分享链接撤销失败')
  }
}

async function handleExportPdf() {
  if (!sessionId.value) return
  const popup = window.open('', '_blank')
  if (!popup) {
    message.error('浏览器阻止了新窗口，请允许弹窗后重试')
    return
  }
  popup.opener = null
  try {
    const html = await studioApi.exportPrintableReport(sessionId.value)
    popup.document.open()
    popup.document.write(html)
    popup.document.close()
    popup.focus()
  } catch {
    popup.close()
    message.error('报告导出失败')
  }
}


async function handleHibernateClick() {
  await hibernateCurrentSandbox(true)
  await refreshStatus()
}

async function handleBack() {
  await hibernateCurrentSandbox(true)
  store.newChat()
  router.push('/ai')
}

async function goSession(id: string) {
  if (id !== sessionId.value) {
    await hibernateCurrentSandbox(false)
    router.push({ name: 'studio', params: { sessionId: id } })
  }
}

// ---------- 文件预览（按类型分流，未知二进制绝不按文本读取） ----------
type PreviewKind = 'image' | 'table' | 'unsupported'
const showFilePreview = ref(false)
const previewPath = ref('')
const previewLoading = ref(false)
const previewKind = ref<PreviewKind>('unsupported')
const previewUrl = ref('')
const previewHeaders = ref<string[]>([])
const previewRows = ref<string[][]>([])

const editableExtensions = new Set(['py', 'r', 'sh', 'bash', 'js', 'ts', 'vue', 'json', 'yaml', 'yml', 'md', 'txt', 'html', 'css', 'scss', 'toml', 'ini', 'log'])
const imageExtensions = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'])
const tableExtensions = new Set(['csv', 'tsv'])

function parseDelimited(content: string, delimiter: string) {
  const rows = content.split(/\r?\n/).filter(Boolean).slice(0, 51).map((line) => line.split(delimiter))
  previewHeaders.value = rows.shift() || []
  previewRows.value = rows
}

async function handleSelectFile(path: string) {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (editableExtensions.has(ext)) {
    await openFileInEditor(path)
    return
  }
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewPath.value = path
  previewLoading.value = true
  previewHeaders.value = []
  previewRows.value = []
  showFilePreview.value = true
  try {
    if (imageExtensions.has(ext)) {
      previewKind.value = 'image'
      previewUrl.value = await studioApi.fetchWorkspaceBlob(sessionId.value, path)
    } else if (tableExtensions.has(ext)) {
      previewKind.value = 'table'
      const result = await studioApi.readFile(sessionId.value, path, 0, 51)
      parseDelimited(result.content, ext === 'tsv' ? '\t' : ',')
    } else {
      previewKind.value = 'unsupported'
    }
  } catch {
    previewKind.value = 'unsupported'
  } finally {
    previewLoading.value = false
  }
}

function closePreviewUrl() {
  if (previewUrl.value) {
    window.URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

function startSplitResize(event: PointerEvent) {
  const host = (event.currentTarget as HTMLElement).parentElement
  if (!host) return
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  const move = (next: PointerEvent) => {
    const rect = host.getBoundingClientRect()
    splitRatio.value = Math.min(70, Math.max(25, ((next.clientX - rect.left) / rect.width) * 100))
  }
  const up = (next: PointerEvent) => {
    target.releasePointerCapture(next.pointerId)
    persistUiState()
    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', up)
  }
  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', up)
}

// ---------- 栏宽拖拽（FilesView startResize 模式） ----------
function startResizeLeft(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startW = leftWidth.value
  const onMove = (ev: MouseEvent) => {
    leftWidth.value = Math.min(400, Math.max(200, startW + ev.clientX - startX))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function startResizeRight(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startW = rightWidth.value
  const onMove = (ev: MouseEvent) => {
    rightWidth.value = Math.min(480, Math.max(240, startW - (ev.clientX - startX)))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function formatSessionTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <main class="studio-view" aria-label="OmicStudio 工作台" :aria-busy="loading">
    <!-- 顶栏 -->
    <header class="studio-topbar">
      <div class="bar-left">
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="back-btn" aria-label="返回 AI 助手" @click="handleBack">
              <n-icon size="18"><ArrowBackOutline /></n-icon>
            </n-button>
          </template>
          返回 AI 助手
        </n-tooltip>
        <span class="bar-title">{{ session?.title || 'AI 分析工作台' }}</span>
        <n-tag v-if="agent" size="small" round :bordered="false" type="info" class="agent-tag">
          {{ agent.avatar }} {{ agent.name }}
        </n-tag>
        <n-tag size="small" round :bordered="false" class="model-tag">{{ modelName }}</n-tag>
      </div>
      <div class="bar-right">
        <n-tooltip v-if="sessionId" trigger="hover">
          <template #trigger>
            <span class="perm-switch" :class="{ auto: isAutoMode }">
              <span class="perm-label">{{ isAutoMode ? '放权模式' : '监督模式' }}</span>
              <n-switch
                :value="isAutoMode"
                size="small"
                :loading="switchingPermissions"
                @update:value="handlePermissionToggle"
              />
            </span>
          </template>
          {{ isAutoMode ? '放权模式：所有工具自动执行，不再等待批准（点击切回监督模式）' : '监督模式：关键操作（执行/写文件/登记产物）需你批准后执行' }}
        </n-tooltip>
        <span class="sandbox-light" :title="`沙盒状态：${statusInfo.label}`">
          {{ statusInfo.icon }} {{ statusInfo.label }}
        </span>
        <n-tooltip v-if="authStore.isAdmin" trigger="hover">
          <template #trigger>
            <n-button text @click="openExtractSkill">
              <n-icon size="16"><ConstructOutline /></n-icon>
            </n-button>
          </template>
          将工作区脚本提炼为 Skill
        </n-tooltip>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text @click="handleShare">
              <n-icon size="16"><ShareSocialOutline /></n-icon>
            </n-button>
          </template>
          创建只读分享链接
        </n-tooltip>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text @click="handleExportPdf">
              <n-icon size="16"><PrintOutline /></n-icon>
            </n-button>
          </template>
          打印 / 保存为 PDF
        </n-tooltip>
        <n-tooltip v-if="shareActive" trigger="hover">
          <template #trigger>
            <n-button text type="error" @click="handleRevokeShare">
              <n-icon size="16"><CloseCircleOutline /></n-icon>
            </n-button>
          </template>
          撤销分享{{ shareExpiresAt ? `（有效至 ${new Date(shareExpiresAt).toLocaleString('zh-CN')}）` : '' }}
        </n-tooltip>
        <n-tooltip v-if="sandboxStatus === 'running'" trigger="hover">
          <template #trigger>
            <n-button text @click="handleHibernateClick">
              <n-icon size="16"><PowerOutline /></n-icon>
            </n-button>
          </template>
          释放沙盒（保留工作区快照）
        </n-tooltip>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text @click="refreshWorkspace">
              <n-icon size="16"><RefreshOutline /></n-icon>
            </n-button>
          </template>
          刷新文件与产物
        </n-tooltip>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text @click="leftCollapsed = !leftCollapsed">
              <n-icon size="16">
                <ChevronBackOutline v-if="!leftCollapsed" />
                <ChevronForwardOutline v-else />
              </n-icon>
            </n-button>
          </template>
          {{ leftCollapsed ? '展开左栏' : '收起左栏' }}
        </n-tooltip>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text @click="rightCollapsed = !rightCollapsed">
              <n-icon size="16">
                <ChevronForwardOutline v-if="!rightCollapsed" />
                <ChevronBackOutline v-else />
              </n-icon>
            </n-button>
          </template>
          {{ rightCollapsed ? '展开右栏' : '收起右栏' }}
        </n-tooltip>
      </div>
    </header>

    <!-- 加载中 -->
    <div v-if="loading" class="studio-center" role="status" aria-live="polite">
      <n-spin size="medium" />
      <p class="center-tip">正在进入工作台…</p>
    </div>

    <!-- 空态：无 sessionId 且无历史工作台会话 -->
    <div v-else-if="!sessionId" class="studio-center">
      <div class="empty-icon">📊</div>
      <div class="empty-title">还没有工作台会话</div>
      <div class="empty-desc">工作台会话需要从 AI 助手的智能体发起</div>
      <n-button type="primary" @click="router.push('/ai')">从 AI 助手发起工作台会话</n-button>
    </div>

    <!-- 三栏主体 -->
    <div v-else class="studio-body">
      <!-- 左栏：会话列表 + 文件树 -->
      <aside v-show="!leftCollapsed" class="col-left" :style="{ width: leftWidth + 'px' }">
        <div class="col-block sessions-block">
          <div class="block-header">
            <n-icon size="14"><FileTrayStackedOutline /></n-icon>
            <span>工作台会话</span>
          </div>
          <div class="session-list">
            <div
              v-for="s in studioSessions"
              :key="s.session_id"
              class="session-item"
              :class="{ active: s.session_id === sessionId }"
              @click="goSession(s.session_id)"
            >
              <div class="s-title">{{ s.title }}</div>
              <div class="s-time">{{ formatSessionTime(s.updated_at) }}</div>
            </div>
            <div v-if="!studioSessions.length" class="block-empty">暂无工作台会话</div>
          </div>
        </div>

        <div class="col-block files-block">
          <div class="files-scroll">
            <StudioFileTree
              :session-id="sessionId"
              :refresh-key="fileTreeKey"
              @select="handleSelectFile"
              @refresh="refreshWorkspace"
              @import="showFilePicker = true"
              @reference="handleInsertWorkspaceReference"
            />
          </div>
        </div>

        <div class="resize-handle" title="拖拽调整宽度" @mousedown="startResizeLeft" />
      </aside>

      <!-- 中栏：对话 / 分屏 / 代码工作室 -->
      <main class="col-center">
        <div class="studio-modebar" role="tablist" aria-label="工作台视图">
          <button :class="{ active: viewMode === 'chat' }" @click="setViewMode('chat')"><n-icon><ChatbubbleEllipsesOutline /></n-icon>对话</button>
          <button :class="{ active: viewMode === 'split' }" @click="setViewMode('split')"><n-icon><GridOutline /></n-icon>分屏</button>
          <button :class="{ active: viewMode === 'code' }" @click="setViewMode('code')"><n-icon><CodeSlashOutline /></n-icon>代码</button>
          <span class="modebar-divider" />
          <button class="follow-ai-toggle" :class="{ active: followAi }" @click="followAi = !followAi; persistUiState()">✦ 跟随 AI</button>
        </div>
        <div v-if="session" class="studio-workbench" :class="`mode-${viewMode}`">
          <section
            v-show="viewMode !== 'code' || chatDrawerOpen"
            class="chat-pane"
            :class="{ drawer: viewMode === 'code' }"
            :style="viewMode === 'split' ? { width: `${splitRatio}%` } : undefined"
          >
            <div v-if="!session.messages.length" class="studio-chat-empty"><div class="empty-stars">✦ · ˚ ✧</div><strong>把工作台交给星光，把问题交给我们</strong><span>描述一个分析目标，AI 会在沙盒中创建代码、运行并整理产物。</span></div>
            <KimiMessageList
              :messages="session.messages"
              :is-typing="store.isStreaming"
              :streaming-content="store.streamingContent"
              :streaming-thought="store.streamingThought"
              :model-name="agent?.name || 'AI 助手'"
              :user-name="userDisplayName"
              :user-avatar="userAvatarUrl"
              :agent-name="agent?.name"
              :agent-avatar="agent?.avatar"
              :agent-color="agent?.color"
            />
            <div class="input-area">
              <KimiChatInput
                v-model="input"
                :disabled="store.isStreaming"
                :placeholder="longRunPlaceholder"
                @send="handleSend"
              />
            </div>
          </section>
          <div v-if="viewMode === 'split'" class="center-splitter" @pointerdown="startSplitResize" />
          <section v-if="viewMode !== 'chat'" class="code-pane" :style="viewMode === 'split' ? { width: `${100 - splitRatio}%` } : undefined">
            <StudioWorkspaceEditor
              ref="workspaceEditorRef"
              :session-id="sessionId"
              :sandbox-status="sandboxStatus"
              :terminal-collapsed="terminalCollapsed"
              -collapsed-changed="handleTerminalCollapsedChanged"
              -changed="refreshWorkspace"
              @user-saved="handleEditorSaved"
              @request-file="message.info('请从左侧工作区选择文件')"
              @run-started="handleEditorRunStarted"
            />
          </section>
          <button v-if="viewMode === 'code'" class="chat-fab" :class="{ open: chatDrawerOpen }" @click="chatDrawerOpen = !chatDrawerOpen">
            <n-icon><ChatbubbleEllipsesOutline /></n-icon><span v-if="store.isStreaming" class="unread-dot" />
          </button>
        </div>
      </main>

      <!-- 右栏：产物 + 待办计划 + 沙盒状态 -->
      <aside v-show="!rightCollapsed" class="col-right" :style="{ width: rightWidth + 'px' }">
        <div class="resize-handle right" title="拖拽调整宽度" @mousedown="startResizeRight" />

        <div class="col-block artifacts-block">
          <button class="block-header accordion-header" @click="toggleRightSection('artifacts')"><span>结果产物</span><span class="accordion-chevron" :class="{ open: rightSections.artifacts }">⌄</span></button>
          <div v-show="rightSections.artifacts" class="block-scroll">
            <StudioArtifactsPanel
              :session-id="sessionId"
              :refresh-key="artifactsKey"
              @insert="handleInsertArtifact"
            />
          </div>
        </div>

        <div class="col-block plan-block">
          <button class="block-header accordion-header" @click="toggleRightSection('plan')"><span>待办计划</span><span class="accordion-chevron" :class="{ open: rightSections.plan }">⌄</span></button>
          <div v-show="rightSections.plan && store.currentPlan.length" class="plan-list">
            <div
              v-for="(step, index) in store.currentPlan"
              :key="`${index}-${step.title}`"
              class="plan-item"
              :class="`is-${step.status}`"
            >
              <span class="plan-status">{{ planStatusIcon(step.status) }}</span>
              <span class="plan-title">{{ step.title }}</span>
            </div>
          </div>
          <div v-if="rightSections.plan && !store.currentPlan.length" class="plan-placeholder">
            <svg viewBox="0 0 120 56" aria-hidden="true"><path d="M18 42c16-13 30-13 42 0 12-13 26-13 42 0" /><circle cx="42" cy="19" r="3" /><circle cx="76" cy="12" r="2" /><path d="M60 38V18l11 12H49l11-12" /></svg>
            <span>任务启航后，计划将在此列队 ⭐</span>
          </div>
        </div>

        <div class="col-block sandbox-block">
          <button class="block-header accordion-header" @click="toggleRightSection('sandbox')"><span>沙盒状态</span><span class="accordion-chevron" :class="{ open: rightSections.sandbox }">⌄</span></button>
          <div v-show="rightSections.sandbox" class="sandbox-info">
            <div class="info-row">
              <span class="info-label">状态</span>
              <span>{{ statusInfo.icon }} {{ statusInfo.label }}</span>
            </div>
            <div v-if="sandboxStatus !== 'running' && sandboxStatus !== 'unavailable'" class="snapshot-note">工作区快照保留中 · 下次运行自动恢复</div>
            <div class="metric-row"><div><span>CPU</span><b>{{ sandboxMetrics.cpu_percent.toFixed(1) }}%</b></div><div class="metric-track"><i :style="{ width: `${Math.min(100, sandboxMetrics.cpu_percent)}%` }" /></div></div>
            <div class="metric-row"><div><span>内存</span><b>{{ sandboxMetrics.memory_percent.toFixed(1) }}%</b></div><div class="metric-track"><i :style="{ width: `${Math.min(100, sandboxMetrics.memory_percent)}%` }" /></div></div>
            <div class="info-row">
              <span class="info-label">工作区</span>
              <span class="info-mono">/workspace</span>
            </div>
            <div class="info-row">
              <span class="info-label">会话 ID</span>
              <span class="info-mono">{{ (workspaceId || sessionId).slice(0, 8) }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <FilePickerModal
      v-model:show="showFilePicker"
      multiple
      @select="handleImportFiles"
    />

    <n-modal
      v-model:show="showExtractSkill"
      preset="card"
      title="提炼为 Skill"
      style="max-width: 620px"
    >
      <div class="extract-skill-form">
        <label>脚本路径<n-input v-model:value="extractSkillForm.path" placeholder="例如 scripts/volcano.py" /></label>
        <div class="extract-grid">
          <label>Skill ID<n-input v-model:value="extractSkillForm.skill_id" placeholder="volcano-plot" /></label>
          <label>名称<n-input v-model:value="extractSkillForm.name" placeholder="火山图绘制" /></label>
        </div>
        <label>描述<n-input v-model:value="extractSkillForm.description" type="textarea" :rows="2" /></label>
        <label>使用说明<n-input v-model:value="extractSkillForm.usage_instructions" type="textarea" :rows="4" /></label>
        <n-checkbox v-model:checked="extractSkillForm.confirm_no_secrets">
          我已检查脚本，不包含 API Key、密码、访问令牌或用户隐私数据
        </n-checkbox>
        <div class="extract-actions">
          <n-button @click="showExtractSkill = false">取消</n-button>
          <n-button type="primary" :loading="extractingSkill" @click="handleExtractSkill">创建并启用 Skill</n-button>
        </div>
      </div>
    </n-modal>

    <!-- 工作区图片 / 表格 / 不支持类型预览 -->
    <n-modal
      v-model:show="showFilePreview"
      preset="card"
      :title="previewPath"
      style="width: min(1040px, 94vw); max-width: 1040px"
      @after-leave="closePreviewUrl"
    >
      <div class="preview-wrap">
        <n-spin v-if="previewLoading" size="medium" />
        <img v-else-if="previewKind === 'image' && previewUrl" :src="previewUrl" :alt="previewPath" class="workspace-image-preview">
        <div v-else-if="previewKind === 'table'" class="workspace-table-wrap">
          <table><thead><tr><th v-for="(header, index) in previewHeaders" :key="index">{{ header }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in previewRows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table>
          <small>仅展示前 50 行</small>
        </div>
        <div v-else class="unsupported-preview">
          <div class="unsupported-icon">◇</div><h3>暂不支持预览此文件</h3><p>为避免二进制乱码，OmicStudio 不会把未知格式强制按文本读取。</p>
          <n-button type="primary" secondary @click="studioApi.downloadWorkspaceFile(sessionId, previewPath)">下载文件</n-button>
        </div>
      </div>
    </n-modal>
  </main>
</template>

<style scoped lang="scss">
.studio-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--chat-bg);
  color: var(--chat-text-primary, inherit);
}

/* ---------- 顶栏 ---------- */
.studio-topbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--chat-border);
  background: var(--chat-nav-bg, var(--chat-bg));
}
.bar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.bar-title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 360px;
}
.agent-tag,
.model-tag {
  flex-shrink: 0;
}
.bar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.sandbox-light {
  font-size: 12px;
  color: var(--chat-text-secondary, #666);
  margin-right: 6px;
  white-space: nowrap;
}

/* 权限模式开关（auto 放权模式警示色） */
.perm-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 8px;
  padding: 3px 10px;
  border: 1px solid var(--chat-border, #e5e7eb);
  border-radius: 999px;
  cursor: pointer;
}
.perm-label {
  font-size: 12px;
  color: var(--chat-text-secondary, #666);
  white-space: nowrap;
}
.perm-switch.auto {
  border-color: rgba(240, 100, 32, 0.6);
  background: rgba(240, 100, 32, 0.08);
}
.perm-switch.auto .perm-label {
  color: #e06420;
  font-weight: 600;
}

/* ---------- 居中态 ---------- */
.studio-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.center-tip {
  font-size: 13px;
  color: var(--chat-text-muted, #999);
}
.empty-icon { font-size: 44px; }
.empty-title { font-size: 16px; font-weight: 600; }
.empty-desc { font-size: 13px; color: var(--chat-text-muted, #999); margin-bottom: 8px; }

/* ---------- 三栏 ---------- */
.studio-body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.col-left {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--chat-border);
  background: var(--chat-sidebar-bg, var(--chat-bg));
  min-height: 0;
}
.col-right {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--chat-border);
  background: var(--chat-sidebar-bg, var(--chat-bg));
  min-height: 0;
  overflow-y: auto;
}

.resize-handle {
  position: absolute;
  top: 0;
  right: -3px;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 5;
}
.resize-handle.right {
  right: auto;
  left: -3px;
}
.resize-handle:hover {
  background: rgba(79, 142, 247, 0.25);
}

.col-block {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-bottom: 1px solid var(--chat-border, #eee);
}
.sessions-block {
  max-height: 40%;
}
.files-block {
  flex: 1;
  border-bottom: none;
}
.block-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--chat-text-muted, #888);
  flex-shrink: 0;
}
.session-list {
  overflow-y: auto;
  padding: 0 8px 8px;
}
.session-item {
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.session-item:hover {
  background: var(--chat-surface-hover, rgba(0, 0, 0, 0.04));
}
.session-item.active {
  background: rgba(79, 142, 247, 0.12);
}
.session-item.active .s-title {
  color: var(--chat-accent, #4f8ef7);
}
.s-title {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.s-time {
  font-size: 11px;
  color: var(--chat-text-muted, #aaa);
}
.block-empty {
  font-size: 12px;
  color: var(--chat-text-muted, #aaa);
  padding: 8px 10px;
}
.files-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.block-footer {
  flex-shrink: 0;
  padding: 8px 10px;
  border-top: 1px solid var(--chat-border, #eee);
}
.import-btn-wrap {
  display: block;
}

/* ---------- 中栏 ---------- */
.col-center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.input-area {
  flex-shrink: 0;
  padding: 12px 20px;
  border-top: 1px solid var(--chat-border);
}

/* ---------- 右栏块 ---------- */
.artifacts-block {
  max-height: 55%;
}
.block-scroll {
  overflow-y: auto;
  padding: 0 10px 10px;
}
.plan-block {
  flex-shrink: 0;
}
.plan-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 10px 10px;
}
.plan-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.45;
  background: var(--chat-surface-hover, rgba(0, 0, 0, 0.035));
}
.plan-item.is-in_progress {
  color: var(--chat-accent, #4f8ef7);
  background: rgba(79, 142, 247, 0.1);
}
.plan-item.is-done {
  color: var(--chat-text-muted, #999);
}
.plan-title {
  min-width: 0;
  word-break: break-word;
}
.plan-status {
  flex-shrink: 0;
  font-family: monospace;
}
.plan-placeholder {
  margin: 0 10px 10px;
  padding: 12px;
  border: 1px dashed var(--chat-border, #ddd);
  border-radius: 8px;
  font-size: 12px;
  color: var(--chat-text-muted, #aaa);
  text-align: center;
  display: grid;
  justify-items: center;
  gap: 5px;
}
.plan-placeholder svg { width: 110px; height: 52px; fill: none; stroke: var(--studio-primary, #6c5ce7); stroke-width: 1.5; opacity: .65; }
.plan-placeholder span { display: block; }
.sandbox-block {
  flex-shrink: 0;
  border-bottom: none;
  margin-top: auto;
}
.sandbox-info {
  padding: 0 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.info-label {
  color: var(--chat-text-muted, #999);
}
.info-mono {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
}

/* ---------- 文件预览 ---------- */
.extract-skill-form {
  display: grid;
  gap: 14px;
}
.extract-skill-form label {
  display: grid;
  gap: 6px;
  color: var(--chat-text-secondary);
  font-size: 13px;
}
.extract-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.extract-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.editor-toolbar {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.editor-meta,
.editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dirty-state { color: #f59e0b; font-size: 12px; }
.saved-state { color: #22c55e; font-size: 12px; }
.shortcut-tip { color: var(--chat-text-muted, #999); font-size: 11px; }
.workspace-editor {
  width: 100%;
  height: min(62vh, 620px);
  min-height: 360px;
}
.editor-output {
  width: 100%;
  margin-top: 10px;
  border: 1px solid var(--chat-border, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
}
.output-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  color: var(--chat-text-secondary);
  font-size: 12px;
  background: var(--chat-surface-hover, #f7f8fa);
}
.editor-output pre {
  margin: 0;
  padding: 10px;
  max-height: 200px;
  overflow: auto;
  background: #1e2127;
  color: #d7dae0;
  font: 12px/1.6 'JetBrains Mono', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.preview-wrap {
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.file-preview {
  width: 100%;
  margin: 0;
  padding: 12px;
  max-height: 60vh;
  overflow: auto;
  background: var(--chat-surface-hover, #f7f8fa);
  border-radius: 8px;
  font-size: 12px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.truncated-tip {
  align-self: flex-end;
  margin-top: 6px;
  font-size: 11px;
  color: var(--chat-text-muted, #999);
}

@media (max-width: 900px) {
  .bar-title { max-width: 160px; }
  .model-tag { display: none; }
}

/* ---------- Studio Apple surface overrides ---------- */
.studio-topbar { border-bottom-color: var(--studio-border, #e8e8f2); background: rgba(255,255,255,.78); backdrop-filter: blur(20px) saturate(1.15); }
.studio-view { background: var(--studio-bg, #f7f7fb); color: var(--studio-text, #2b2b3d); }
.studio-modebar { flex-shrink:0; display:flex; align-items:center; justify-content:center; gap:2px; padding:7px 10px; border-bottom:1px solid var(--studio-border,#e8e8f2); background:rgba(255,255,255,.72); backdrop-filter:blur(18px); }
.studio-modebar button { display:flex; align-items:center; gap:5px; padding:6px 13px; border:0; border-radius:8px; color:var(--studio-text-sub,#8a8aa3); background:transparent; font-size:12px; cursor:pointer; transition:background .16s ease,color .16s ease,transform .1s ease; }
.modebar-divider{width:1px;height:18px;margin:0 5px;background:var(--studio-border,#e8e8f2)}.studio-modebar button:hover,.studio-modebar button.active { color:var(--studio-primary,#6c5ce7); background:var(--studio-primary-soft,#f0edff); }.studio-modebar button.active { font-weight:600; }.studio-modebar button:active { transform:scale(.97); }
.studio-workbench { position:relative; flex:1; min-height:0; display:flex; overflow:hidden; }.chat-pane,.code-pane { min-width:0; min-height:0; display:flex; flex-direction:column; overflow:hidden; }.chat-pane { flex:1; }.code-pane { flex:1; border-left:1px solid var(--studio-border,#e8e8f2); }.mode-chat .chat-pane { width:100%; }.mode-code .code-pane { width:100%; border-left:0; }.center-splitter { flex:0 0 5px; margin-left:-2px; margin-right:-2px; z-index:4; cursor:col-resize; background:transparent; touch-action:none; }.center-splitter:hover { background:var(--studio-primary,#6c5ce7); }
.chat-pane.drawer { position:absolute; right:16px; bottom:16px; z-index:8; width:min(460px,calc(100% - 32px)); height:min(70%,620px); border:1px solid var(--studio-border,#e8e8f2); border-radius:16px; background:rgba(255,255,255,.94); box-shadow:0 18px 50px rgba(43,43,61,.16); }.chat-fab { position:absolute; right:20px; bottom:20px; z-index:9; display:grid; place-items:center; width:44px; height:44px; border:0; border-radius:50%; color:#fff; background:var(--studio-primary,#6c5ce7); box-shadow:0 8px 22px rgba(108,92,231,.28); cursor:pointer; }.chat-fab.open { opacity:0; pointer-events:none; }.unread-dot { position:absolute; top:2px; right:2px; width:9px; height:9px; border:2px solid #fff; border-radius:50%; background:#e45470; }
.col-left,.col-right { background:rgba(255,255,255,.66); border-color:var(--studio-border,#e8e8f2); }.session-item:hover { background:var(--studio-primary-soft,#f0edff); }.session-item.active { background:rgba(108,92,231,.11); }.session-item.active .s-title { color:var(--studio-primary,#6c5ce7); }.resize-handle:hover { background:rgba(108,92,231,.26); }
.plan-item.is-done { color:var(--studio-text-sub,#8a8aa3); background:rgba(108,92,231,.06); opacity:.78; }.plan-item.is-done .plan-title { text-decoration:line-through; text-decoration-thickness:1px; }.plan-item.is-done .plan-status { color:var(--studio-primary,#6c5ce7); font-weight:700; }.plan-item.is-in_progress { color:var(--studio-primary,#6c5ce7); background:var(--studio-primary-soft,#f0edff); }
.workspace-image-preview { max-width:100%; max-height:70vh; object-fit:contain; border-radius:12px; box-shadow:0 12px 36px rgba(43,43,61,.12); }.workspace-table-wrap { width:100%; max-height:65vh; overflow:auto; }.workspace-table-wrap table { width:100%; border-collapse:collapse; font-size:12px; }.workspace-table-wrap th,.workspace-table-wrap td { padding:7px 9px; border-bottom:1px solid var(--studio-border,#e8e8f2); text-align:left; white-space:nowrap; }.workspace-table-wrap th { position:sticky; top:0; background:var(--studio-primary-soft,#f0edff); }.workspace-table-wrap small { display:block; margin-top:8px; color:var(--studio-text-sub,#8a8aa3); }.unsupported-preview { display:grid; justify-items:center; gap:8px; padding:46px 20px; text-align:center; }.unsupported-preview h3 { margin:0; }.unsupported-preview p { max-width:460px; margin:0 0 10px; color:var(--studio-text-sub,#8a8aa3); font-size:12px; }.unsupported-icon { color:var(--studio-primary,#6c5ce7); font-size:42px; }
@media (prefers-reduced-motion: reduce) { .studio-modebar button,.node-caret { transition:none !important; } }

.accordion-header { width:100%; border:0; background:transparent; text-align:left; cursor:pointer; }.accordion-header:hover { background:var(--studio-primary-soft,#f0edff); }.accordion-chevron { margin-left:auto; color:var(--studio-text-sub,#8a8aa3); transition:transform .18s ease; }.accordion-chevron.open { transform:rotate(180deg); }
.studio-view :deep(.kimi-message-item.user .message-content.user-bubble) { max-width:78%; padding:10px 14px; color:var(--studio-text,#2b2b3d); background:#eeeaff; border:1px solid #ddd7ff; border-radius:16px 16px 5px 16px; box-shadow:0 3px 12px rgba(108,92,231,.08); }
.studio-view :deep(.kimi-message-item.assistant .message-content.ai-card) { border-color:var(--studio-border,#e8e8f2); box-shadow:0 4px 16px rgba(43,43,61,.04); }.studio-view :deep(.ai-name),.studio-view :deep(.meta-item.tokens) { color:var(--studio-primary,#6c5ce7); }
.studio-view :deep(.kimi-chat-input) { border-color:var(--studio-border,#e8e8f2); border-radius:16px; background:rgba(255,255,255,.88); box-shadow:0 4px 16px rgba(43,43,61,.04); }.studio-view :deep(.kimi-chat-input.focused) { border-color:var(--studio-primary,#6c5ce7); box-shadow:0 0 0 3px rgba(108,92,231,.12); }.studio-view :deep(.kimi-chat-input.deep-thinking) { border-color:var(--studio-primary,#6c5ce7); }.studio-view :deep(.deep-thinking-btn.active) { color:var(--studio-primary,#6c5ce7)!important; background:var(--studio-primary-soft,#f0edff)!important; border:1px solid #d7d0ff; border-radius:999px; }.studio-view :deep(.send-btn:hover),.studio-view :deep(.send-btn.active) { background:var(--studio-primary,#6c5ce7); }

.studio-chat-empty{position:absolute;inset:0;z-index:0;display:grid;place-content:center;justify-items:center;gap:9px;padding:30px;text-align:center;color:var(--studio-text-sub,#8a8aa3);pointer-events:none;background:radial-gradient(circle at 50% 42%,rgba(240,237,255,.82),transparent 48%)}.studio-chat-empty strong{color:var(--studio-text,#2b2b3d);font-weight:600}.studio-chat-empty span{max-width:350px;font-size:12px;line-height:1.6}.empty-stars{color:var(--studio-primary,#6c5ce7);font-size:28px;letter-spacing:10px;opacity:.7}.chat-pane{position:relative}.snapshot-note{margin:2px 0 6px;padding:6px 8px;border-radius:7px;background:var(--studio-primary-soft,#f0edff);color:var(--studio-primary,#6c5ce7);font-size:11px;line-height:1.45}.metric-row{padding:3px 12px 5px;font-size:11px;color:var(--studio-text-sub,#8a8aa3)}.metric-row>div:first-child{display:flex;justify-content:space-between;margin-bottom:4px}.metric-row b{color:var(--studio-text,#2b2b3d);font-weight:600}.metric-track{height:5px;overflow:hidden;border-radius:99px;background:#ecebf3}.metric-track i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#9f91ed,var(--studio-primary,#6c5ce7));transition:width .3s ease}
</style>
