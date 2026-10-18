<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { applyResearchEvent, consumeResearchStream, researchMessageView, safeSourceUrl } from '@/components/research/adapters/researchPresentation'
import type { TreasureIslandProps } from '@/types/treasureIsland'
import { projectsApi, type ProjectItem } from '@/api/projects'
import { researchAgentApi, researchFailure, researchStreamUrl, type ResearchCapabilities, type ResearchMessage, type ResearchSession } from '@/api/researchAgent'
import TreasureOriginalDisplay from '@/components/research/TreasureOriginalDisplay.vue'
import AgentToolPanel from '@/components/research/AgentToolPanel.vue'
import DatasetWorkspace from '@/components/research/DatasetWorkspace.vue'

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
const draft = ref('')
const loading = ref(true)
const sending = ref(false)
const streamError = ref('')
const controller = ref<AbortController | null>(null)
const toolPanel = ref<InstanceType<typeof AgentToolPanel> | null>(null)
const datasetPanel = ref<InstanceType<typeof DatasetWorkspace> | null>(null)
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
    if (generation === sessionGeneration) messages.value = restored
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
  draft.value = ''
  streamError.value = ''
  messages.value.push({ message_id: `local-${Date.now()}`, role: 'user', content, status: 'complete', metadata_json: {}, created_at: new Date().toISOString() })
  const assistant = reactive<ResearchMessage>({ message_id: `stream-${Date.now()}`, role: 'assistant', content: '', status: 'streaming', metadata_json: {}, created_at: new Date().toISOString() })
  messages.value.push(assistant)
  sending.value = true
  controller.value = new AbortController()
  try {
    const response = await fetch(researchStreamUrl(sessionId), {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
      body: JSON.stringify({ content }), signal: controller.value.signal,
    })
    if (!response.ok || !response.body) {
      const data = await response.json().catch(() => ({})) as { code?: string }
      throw { response: { status: response.status, data } }
    }
    const ended = await consumeResearchStream(response.body, event => {
      if (generation !== sessionGeneration) return
      applyResearchEvent(assistant, event)
      if (event.event === 'platform_tool') { toolPanel.value?.show(event.result); datasetPanel.value?.show(event.result) }
      if (event.event === 'error' || event.error) {
        streamError.value = researchFailure({ code: event.code || 'NODE_UNAVAILABLE' })
        assistant.metadata_json.events ??= {}
        assistant.metadata_json.events.error = streamError.value
      }
    })
    if (generation === sessionGeneration && !ended && assistant.status === 'streaming') {
      assistant.status = 'interrupted'
      streamError.value = '连接已中断，已保留收到的部分回复；可重新打开会话查看已保存内容。'
    } else if (streamError.value) assistant.status = 'error'
  } catch (error) {
    if (generation === sessionGeneration && (error as Error).name !== 'AbortError') streamError.value = researchFailure(error)
    assistant.status = 'error'
  } finally {
    if (generation === sessionGeneration) {
      sending.value = false
      controller.value = null
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
  try { await loadSessions() } catch (error) { historyError.value = researchFailure(error) }
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
    projects.value = await projectsApi.listProjects()
    if (generation !== sessionGeneration) return
    loading.value = false
    await loadSessions()
  } catch (error) {
    if (generation === sessionGeneration) historyError.value = researchFailure(error)
  } finally { if (generation === sessionGeneration) loading.value = false }
}
async function editSession(id: string, title?: string) {
  try {
    await researchAgentApi.updateSession(id, title ? { title } : { status: 'archived' })
    if (title) {
      const row = sessions.value.find(item => item.session_id === id)
      if (row) row.title = title
    } else {
      sessions.value = sessions.value.filter(item => item.session_id !== id)
      if (currentSession.value?.session_id === id) { stopCurrentStream(); currentSession.value = null; messages.value = [] }
    }
  } catch (error) { historyError.value = researchFailure(error) }
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
    <DatasetWorkspace v-if="currentSession && capabilities?.prepare_import" :key="`dataset-${currentSession.session_id}`" ref="datasetPanel" :project-id="currentSession.project_id" />
    <AgentToolPanel v-if="currentSession && capabilities?.prepare_import" :key="currentSession.session_id" ref="toolPanel" :session-id="currentSession.session_id" />
  </main>
</template>
<style scoped>
.treasure-native-module { display: flex; flex: 1; flex-direction: column; min-height: 0; min-width: 0; height: 100%; overflow: hidden; }
</style>
