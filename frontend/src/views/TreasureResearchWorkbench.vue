<script setup lang="ts">
import { useResearchWorkflow } from '@/components/research/adapters/useResearchWorkflow'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { applyResearchEvent, consumeResearchStream, researchMessageView, safeSourceUrl } from '@/components/research/adapters/researchPresentation'
import type { ResearchActionV1, TreasureIslandProps } from '@/types/treasureIsland'
import { projectsApi, type ProjectItem } from '@/api/projects'
import { researchAgentApi, researchFailure, researchStreamUrl, type ResearchCapabilities, type ResearchMessage, type ResearchSession } from '@/api/researchAgent'
import TreasureOriginalDisplay from '@/components/research/TreasureOriginalDisplay.vue'
import { generateId } from '@/utils/id'

const capabilities = ref<ResearchCapabilities | null>(null)
const accessError = ref('')
const historyError = ref('')
const canReadSessions = computed(() => !loading.value && capabilities.value?.read_sessions === true)
const canDiscover = computed(() => !loading.value && capabilities.value?.read_discovery === true)
const projects = ref<ProjectItem[]>([])
const sessions = ref<ResearchSession[]>([])
const selectedProjectId = ref<string | null>(null)
const currentSession = ref<ResearchSession | null>(null)
const messages = ref<ResearchMessage[]>([])
const workflow = useResearchWorkflow(currentSession)
const draft = ref('')
const loading = ref(true)
const sending = ref(false)
const streamError = ref('')
const controller = ref<AbortController | null>(null)
let sessionGeneration = 0

function stopCurrentStream() {
  sessionGeneration++
  controller.value?.abort()
  controller.value = null
  sending.value = false
}

async function loadSessions() {
  const generation = sessionGeneration
  const project = selectedProjectId.value
  const restored = await researchAgentApi.listSessions(project || undefined)
  if (generation !== sessionGeneration || project !== selectedProjectId.value) return
  sessions.value = restored
  if (sessions.value.length && !currentSession.value) await selectSession(sessions.value[0])
}

async function selectSession(session: ResearchSession) {
  if (!canReadSessions.value || (session.project_id || null) !== selectedProjectId.value) return
  stopCurrentStream()
  const generation = sessionGeneration
  currentSession.value = session
  messages.value = []
  try {
    const restored = await researchAgentApi.getMessages(session.session_id)
    if (generation === sessionGeneration) {
      messages.value = restored
      await workflow.action({ type: 'capabilities.refresh' }, true)
      if (generation !== sessionGeneration) return
      if (capabilities.value?.prepare_import) void workflow.action({ type: 'records.refresh' }, true)
    }
  } catch (error) {
    if (generation === sessionGeneration) historyError.value = researchFailure(error)
  }
}

async function createSession() {
  if (!canDiscover.value) return
  stopCurrentStream()
  const generation = sessionGeneration
  let session: ResearchSession
  try { session = await researchAgentApi.createSession(selectedProjectId.value || undefined) }
  catch (error) { if (generation === sessionGeneration) streamError.value = researchFailure(error); return }
  if (generation !== sessionGeneration) return
  currentSession.value = session
  messages.value = []
  void workflow.action({ type: 'capabilities.refresh' }, true)
  sessions.value = [currentSession.value, ...sessions.value]
  streamError.value = ''
}

async function send(submitted?: string) {
  const content = (submitted ?? draft.value).trim()
  if (!content || sending.value || !canDiscover.value) return
  if (!currentSession.value) await createSession()
  if (!currentSession.value) return
  const generation = sessionGeneration
  const sessionId = currentSession.value.session_id
  const requestId = generateId()
  draft.value = ''
  streamError.value = ''
  messages.value.push({ message_id: `local-${Date.now()}`, role: 'user', content, status: 'complete', metadata_json: {}, created_at: new Date().toISOString() })
  const assistant = reactive<ResearchMessage>({ message_id: `stream-${Date.now()}`, role: 'assistant', content: '', status: 'streaming', metadata_json: {}, created_at: new Date().toISOString() })
  messages.value.push(assistant)
  sending.value = true
  let hasPlatformTool = false
  try {
    let cursor = 0
    let ended = false
    let lastError: unknown
    for (let attempt = 0; attempt < 4 && !ended; attempt++) {
      if (attempt > 0) await new Promise(resolve => setTimeout(resolve, 250 * 2 ** (attempt - 1)))
      if (generation !== sessionGeneration) return
      const activeController = new AbortController()
      controller.value = activeController
      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
        }
        if (cursor > 0) headers['Last-Event-ID'] = String(cursor)
        const response = await fetch(researchStreamUrl(sessionId), {
          method: 'POST', headers,
          body: JSON.stringify({ content, request_id: requestId }), signal: activeController.signal,
        })
        if (!response.ok || !response.body) {
          const data = await response.json().catch(() => ({})) as { code?: string }
          throw { response: { status: response.status, data } }
        }
        const result = await consumeResearchStream(response.body, event => {
          if (generation !== sessionGeneration) return
          applyResearchEvent(assistant, event)
          if (event.event === 'platform_tool') hasPlatformTool = true
          if (event.event === 'error' || event.error) {
            streamError.value = researchFailure({ code: event.code || 'NODE_UNAVAILABLE' })
            assistant.metadata_json.events ??= {}
            assistant.metadata_json.events.error = streamError.value
          }
        }, cursor)
        cursor = result.lastEventId
        ended = result.ended
        if (!ended && attempt === 3) break
      } catch (error) {
        lastError = error
        if ((error as Error).name === 'AbortError') throw error
        const status = (error as { response?: { status?: number } }).response?.status
        if (status || attempt === 3) throw error
      }
    }
    if (generation === sessionGeneration && !ended && assistant.status === 'streaming') {
      assistant.status = 'interrupted'
      streamError.value = lastError
        ? researchFailure(lastError)
        : '连接已中断，已保留收到的部分回复；可重新连接查看同一轮结果。'
    } else if (streamError.value) assistant.status = 'error'
  } catch (error) {
    if (generation === sessionGeneration && (error as Error).name !== 'AbortError') streamError.value = researchFailure(error)
    assistant.status = 'error'
  } finally {
    if (generation === sessionGeneration) {
      sending.value = false
      controller.value = null
      if (hasPlatformTool && capabilities.value?.prepare_import) void workflow.action({ type: 'records.refresh' }, !workflow.view.open)
    }
    await nextTick()
  }
}

async function cancel() {
  if (!currentSession.value) return
  controller.value?.abort()
  await researchAgentApi.cancel(currentSession.value.session_id).catch(() => undefined)
  sending.value = false
  streamError.value = '已停止接收回复。当前服务尚不保证跨进程取消；重新打开会话可查看已保存快照。'
}

async function changeProject(value: string) {
  if (!canReadSessions.value) return
  stopCurrentStream()
  selectedProjectId.value = value || null
  currentSession.value = null
  messages.value = []
  historyError.value = ''
  sessions.value = []
  const generation = sessionGeneration
  try { await loadSessions() } catch (error) { if (generation === sessionGeneration) historyError.value = researchFailure(error) }
}

async function refreshAccess() {
  stopCurrentStream()
  const generation = sessionGeneration
  capabilities.value = null
  accessError.value = ''
  historyError.value = ''
  loading.value = true
  sessions.value = []
  currentSession.value = null
  messages.value = []
  try {
    const access = await researchAgentApi.capabilities()
    if (generation !== sessionGeneration) return
    capabilities.value = access
    if (!access.read_sessions) { accessError.value = researchFailure({ code: access.reason_code || 'FEATURE_DISABLED' }); return }
    if (!access.read_discovery) accessError.value = researchFailure({ code: access.reason_code || 'NODE_NOT_CONFIGURED' })
    const restoredProjects = await projectsApi.listProjects()
    if (generation !== sessionGeneration) return
    projects.value = restoredProjects
    loading.value = false
    await loadSessions()
  } catch (error) {
    if (generation === sessionGeneration) historyError.value = researchFailure(error)
  } finally { if (generation === sessionGeneration) loading.value = false }
}
async function editSession(id: string, title?: string) {
  const generation = sessionGeneration
  try {
    await researchAgentApi.updateSession(id, title ? { title } : { status: 'archived' })
    if (generation !== sessionGeneration) return
    if (title) {
      const row = sessions.value.find(item => item.session_id === id)
      if (row) row.title = title
    } else {
      sessions.value = sessions.value.filter(item => item.session_id !== id)
      if (currentSession.value?.session_id === id) { stopCurrentStream(); currentSession.value = null; messages.value = [] }
    }
  } catch (error) { if (generation === sessionGeneration) historyError.value = researchFailure(error) }
}
async function literature(kind: string, id: string) {
  if (!currentSession.value) throw new Error('No platform session')
  const value = await researchAgentApi.literature(currentSession.value.session_id, kind, id)
  if (value.urls) value.urls = Object.fromEntries(Object.entries(value.urls).map(([key, url]) => [key, safeSourceUrl(url)]))
  return value
}
function regenerate(id: string) {
  const index = messages.value.findIndex(item => item.message_id === id)
  const question = messages.value.slice(0, index).reverse().find(item => item.role === 'user')
  if (question && !sending.value) void send(question.content)
}
async function handleResearchAction(intent: ResearchActionV1) {
  if (!currentSession.value && !['workflow.close', 'task.open', 'report.open'].includes(intent.type)) await createSession()
  await workflow.action(intent)
}
const presentation = computed<Partial<TreasureIslandProps>>(() => ({
  messages: messages.value.map(researchMessageView),
  sessions: sessions.value.map(item => ({ id: item.session_id, title: item.title, updated_at: item.updated_at })),
  activeSessionId: currentSession.value?.session_id ?? null,
  projects: projects.value.map(item => ({ id: item.id, name: item.name })),
  loading: loading.value, accessError: accessError.value, historyError: historyError.value, streamError: streamError.value,
  onSelectSession: id => { const row = sessions.value.find(item => item.session_id === id); if (row) void selectSession(row) },
  onNewSession: () => { void createSession() },
  onRenameSession: (id, title) => { void editSession(id, title) },
  onArchiveSession: id => { void editSession(id) },
  onChangeProject: id => { void changeProject(id) }, onRefresh: () => { void refreshAccess() },
  onRegenerate: regenerate, loadLiterature: literature,
  workflow: { ...workflow.view }, onResearchAction: intent => { void handleResearchAction(intent) },
}))
onMounted(() => {
  void refreshAccess()
  window.addEventListener('focus', refreshAccess)
})
onUnmounted(() => { stopCurrentStream(); window.removeEventListener('focus', refreshAccess) })
</script>

<template>
  <main class="treasure-native-module" aria-label="科研寻宝鼠">
    <TreasureOriginalDisplay mode="app" v-model:draft="draft" :disabled="!canDiscover" :streaming="sending" :project-id="selectedProjectId" :presentation="presentation" @submit="send" @example="draft = $event" @cancel="cancel" />
  </main>
</template>
<style scoped>
.treasure-native-module { display: flex; flex: 1; flex-direction: column; min-height: 0; min-width: 0; height: 100%; overflow: hidden; }
</style>
