<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { NButton, NEmpty, NIcon, NPopover, NSelect, NSpin } from 'naive-ui'
import { ChevronBackOutline, ChevronForwardOutline, AddOutline, RefreshOutline, InformationCircleOutline, PawOutline, PersonOutline, CopyOutline, CheckmarkOutline } from '@vicons/ionicons5'
import TreasureBrandMark from '@/components/research/TreasureBrandMark.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { projectsApi, type ProjectItem } from '@/api/projects'
import { researchAgentApi, researchFailure, researchStreamUrl, type ResearchCapabilities, type DiscoveryProposal, type ResearchMessage, type ResearchSession } from '@/api/researchAgent'
import TreasureOriginalDisplay from '@/components/research/TreasureOriginalDisplay.vue'
import DiscoveryProposalCard from '@/components/research/DiscoveryProposalCard.vue'
import AgentToolPanel from '@/components/research/AgentToolPanel.vue'
import DatasetWorkspace from '@/components/research/DatasetWorkspace.vue'

const sidebarOpen = ref(false)
const petVisible = ref(true)
const messageList = ref<HTMLElement>()
const copiedMessage = ref('')
let stickToBottom = true
function onMessageScroll() {
  const el = messageList.value
  if (el) stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}
async function copyMessage(item: ResearchMessage) {
  try { await navigator.clipboard.writeText(item.content); copiedMessage.value = item.message_id }
  catch { copiedMessage.value = '' }
}
function messageTools(item: ResearchMessage, index: number): Record<string, unknown>[] {
  if (sending.value && index === messages.value.length - 1) return toolTrace.value
  const events = item.metadata_json?.events as { tools?: Record<string, unknown>[] } | undefined
  return Array.isArray(events?.tools) ? events.tools : []
}
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
const toolTrace = ref<Record<string, unknown>[]>([])
const grounding = ref<Record<string, unknown> | null>(null)
const controller = ref<AbortController | null>(null)
const toolPanel = ref<InstanceType<typeof AgentToolPanel> | null>(null)
const datasetPanel = ref<InstanceType<typeof DatasetWorkspace> | null>(null)
let sessionGeneration = 0

function stopCurrentStream() {
  sessionGeneration++
  controller.value?.abort()
  controller.value = null
  sending.value = false
  toolTrace.value = []
  grounding.value = null
}

const projectOptions = computed(() => [
  { label: '全局只读发现（不归档到项目）', value: '' },
  ...projects.value.map((project) => ({ label: project.name, value: project.id })),
])
watch(() => messages.value.map(item => item.content).join(''), async () => {
  await nextTick()
  if (stickToBottom && messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
})

function cardsToProposals(cards: unknown[], sessionId: string, projectId: string | null): DiscoveryProposal[] {
  return cards.flatMap((raw, index) => {
    if (!raw || typeof raw !== 'object') return []
    const card = raw as Record<string, unknown>
    const accession = typeof card.accession === 'string' ? card.accession : null
    return [{
      schema_version: '1.0', proposal_id: `${sessionId}:${accession || index}`,
      source: typeof card.tool === 'string' ? card.tool : 'unknown',
      accession, title: typeof card.title === 'string' ? card.title : '', summary: typeof card.summary === 'string' ? card.summary : '',
      organism: null, assay_type: null, sample_count: null, metadata_status: 'unverified', source_links: [],
      evidence_refs: accession ? [accession] : [], retrieved_at: new Date().toISOString(), project_id: projectId,
      conversation_id: sessionId, provenance: { agent: 'research-treasure-mouse', verification_level: 'source_not_verified' },
      next_actions: ['inspect_metadata', 'refine_search'],
    }]
  })
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
  const projectId = currentSession.value.project_id || null
  draft.value = ''
  streamError.value = ''
  toolTrace.value = []
  grounding.value = null
  stickToBottom = true
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
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (generation !== sessionGeneration) break
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim().startsWith('data:')) continue
        const raw = line.trim().slice(5).trim()
        if (raw === '[DONE]') continue
        const event = JSON.parse(raw) as Record<string, unknown>
        if (typeof event.delta === 'string') assistant.content += event.delta
        if (event.event === 'tool') toolTrace.value.push(event)
        if (event.event === 'platform_tool') { toolPanel.value?.show(event.result); datasetPanel.value?.show(event.result) }
        if (event.event === 'grounding') grounding.value = event
        if (event.event === 'end') {
          const cards = Array.isArray(event.cards) ? event.cards : []
          assistant.metadata_json = { proposals: cardsToProposals(cards, sessionId, projectId), events: { cards, tools: toolTrace.value, grounding: grounding.value } }
        }
        if (event.event === 'cancel') assistant.status = 'cancelled'
        if (event.event === 'error' || event.error) streamError.value = researchFailure({ code: event.code || 'NODE_UNAVAILABLE' })
      }
    }
    assistant.status = streamError.value ? 'error' : assistant.status === 'cancelled' ? 'cancelled' : 'complete'
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
onMounted(() => {
  void refreshAccess()
  window.addEventListener('focus', refreshAccess)
})
onUnmounted(() => { stopCurrentStream(); window.removeEventListener('focus', refreshAccess) })
</script>

<template>
  <main class="treasure-page" aria-labelledby="treasure-title">
    <nav class="session-rail" aria-label="会话导航">
      <button class="icon-button" :aria-expanded="sidebarOpen" aria-controls="treasure-sessions" :aria-label="sidebarOpen ? '收起会话' : '展开会话'" @click="sidebarOpen = !sidebarOpen"><NIcon :component="sidebarOpen ? ChevronBackOutline : ChevronForwardOutline" /></button>
      <button class="new-chat-button" aria-label="新会话" title="新会话" :disabled="!canDiscover" @click="createSession"><TreasureBrandMark /></button>
    </nav>
    <aside v-if="canReadSessions" v-show="sidebarOpen" id="treasure-sessions" class="session-panel" aria-label="科研发现会话">
      <div class="panel-title"><strong>历史会话</strong><NButton quaternary size="small" :disabled="!canDiscover" @click="createSession"><NIcon :component="AddOutline" />新会话</NButton></div>
      <NSpin v-if="loading" size="small" />
      <NEmpty v-else-if="historyError" description="会话列表暂不可读取" />
      <p v-else-if="!sessions.length" class="history-empty">暂无平台会话</p>
      <button v-for="session in sessions" v-else :key="session.session_id" class="session-item" :class="{ active: currentSession?.session_id === session.session_id }" @click="selectSession(session)">{{ session.title }}</button>
    </aside>
    <div class="treasure-main">
      <header class="treasure-header">
        <span id="treasure-title" class="page-label">科研寻宝鼠</span>
        <div class="header-actions">
          <NPopover trigger="click" placement="bottom-end">
            <template #trigger><button class="context-button" :disabled="!canReadSessions" title="选择项目上下文">{{ selectedProjectId ? projects.find(p => p.id === selectedProjectId)?.name || '当前项目' : '全局只读' }}</button></template>
            <div class="context-controls"><label for="project-select">项目上下文</label><NSelect id="project-select" :disabled="!canReadSessions" :value="selectedProjectId || ''" :options="projectOptions" @update:value="changeProject" /></div>
          </NPopover>
          <button class="icon-button" :disabled="loading" title="刷新权限" aria-label="刷新权限" @click="refreshAccess"><NIcon :component="RefreshOutline" /></button>
          <NPopover trigger="click" placement="bottom-end"><template #trigger><button class="icon-button" title="关于科研寻宝鼠" aria-label="关于科研寻宝鼠"><NIcon :component="InformationCircleOutline" /></button></template><div class="about-discovery">检索公开组学与文献数据，以原始条目为准。当前使用平台默认模型。下载与分析须经平台授权。</div></NPopover>
          <button class="icon-button" :aria-pressed="petVisible" :title="petVisible ? '收起阿寻' : '找回阿寻'" :aria-label="petVisible ? '收起阿寻' : '找回阿寻'" @click="petVisible = !petVisible"><NIcon :component="PawOutline" /></button>
        </div>
      </header>
      <p v-if="accessError" class="access-notice" role="status">{{ accessError }}</p>
      <p v-if="historyError" class="access-notice" role="alert">{{ historyError }}</p>
      <section class="conversation-panel" :class="{ welcome: !messages.length }">
        <DatasetWorkspace v-if="currentSession && capabilities?.prepare_import" :key="`dataset-${currentSession.session_id}`" ref="datasetPanel" :project-id="currentSession.project_id" />
        <AgentToolPanel v-if="currentSession && capabilities?.prepare_import" :key="currentSession.session_id" ref="toolPanel" :session-id="currentSession.session_id" />
        <div v-if="loading" class="loading-state"><NSpin /> 正在加载科研发现</div>
        <div v-else-if="!messages.length" class="welcome-scroll"><TreasureOriginalDisplay v-model:draft="draft" :disabled="!canDiscover" :streaming="sending" :project-id="selectedProjectId" @submit="send" @example="draft = $event" @cancel="cancel" /></div>
        <div v-else ref="messageList" class="message-list" aria-live="polite" @scroll="onMessageScroll">
          <div class="message-column">
            <article v-for="(item, index) in messages" :key="item.message_id" class="message" :class="item.role">
              <div class="message-avatar"><NIcon v-if="item.role === 'user'" :component="PersonOutline" /><TreasureBrandMark v-else /></div>
              <div class="message-content">
                <div v-if="item.role !== 'user'" class="message-role">科研寻宝鼠</div>
                <div v-if="messageTools(item, index).length" class="trace" aria-label="工具调用轨迹"><span v-for="(tool, toolIndex) in messageTools(item, index)" :key="toolIndex" :class="String(tool.status)"><span aria-hidden="true">{{ tool.status === 'running' ? '◌' : tool.status === 'error' ? '×' : '✓' }}</span>{{ tool.label || tool.name }}<small v-if="typeof tool.ms === 'number'">{{ tool.ms }}ms</small></span></div>
                <div class="message-body"><template v-if="item.role === 'user'">{{ item.content }}</template><MarkdownRenderer v-else :content="item.content || (item.status === 'streaming' ? '正在检索…' : '')" /></div>
                <div v-if="item.metadata_json?.proposals?.length" class="proposal-list"><DiscoveryProposalCard v-for="proposal in item.metadata_json.proposals as DiscoveryProposal[]" :key="proposal.proposal_id" :proposal="proposal" @inspect="toolPanel?.prepare($event)" @prepare-import="datasetPanel?.discover($event)" /></div>
                <button class="copy-message icon-button" :aria-label="copiedMessage === item.message_id ? '已复制' : '复制消息'" @click="copyMessage(item)"><NIcon :component="copiedMessage === item.message_id ? CheckmarkOutline : CopyOutline" /></button>
              </div>
            </article>
            <div v-if="grounding" class="grounding">已保留正文与证据编号的核验状态，请以来源页面为准。</div>
          </div>
        </div>
        <p v-if="streamError" class="error-text" role="alert">{{ streamError }}</p>
        <TreasureOriginalDisplay v-if="messages.length" class="bottom-composer" mode="composer" v-model:draft="draft" :disabled="!canDiscover" :streaming="sending" :project-id="selectedProjectId" @submit="send" @cancel="cancel" />
        <div v-if="messages.length && petVisible" class="pet-corner"><p v-if="sending" class="pet-bubble">正在检索，阿寻继续挖宝中…</p><TreasureOriginalDisplay class="treasure-pet" mode="pet" draft="" :disabled="true" :streaming="sending" :project-id="selectedProjectId" /></div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.treasure-page { --treasure-paper: #faf8f5; --treasure-panel: #f6f3ee; --treasure-card: #fff; --treasure-ink: #292524; --treasure-muted: #78716c; --treasure-border: #e7e5e4; --treasure-green: #15803d; --treasure-green-soft: #dcfce7; --treasure-dot: rgb(120 113 108 / .045); display: flex; flex: 1; height: 100%; min-height: 0; min-width: 0; overflow: hidden; background: var(--treasure-paper); color: var(--treasure-ink); }
:global(html.dark) .treasure-page, :global(html[data-theme="dark"]) .treasure-page { --treasure-paper: #28241f; --treasure-panel: #302b25; --treasure-card: #36302a; --treasure-ink: #f5f0e9; --treasure-muted: #b9afa4; --treasure-border: #494038; --treasure-green: #77d39b; --treasure-green-soft: #253e2d; --treasure-dot: rgb(225 215 192 / .05); }
.session-rail { width: 48px; flex: 0 0 48px; display: flex; flex-direction: column; align-items: center; gap: 16px; padding-top: 12px; border-right: 1px solid var(--treasure-border); background: var(--treasure-panel); }
.icon-button, .new-chat-button, .context-button { display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 8px; background: transparent; color: var(--treasure-muted); cursor: pointer; padding: 6px; font: inherit; }
.icon-button { width: 30px; height: 30px; font-size: 19px; flex-shrink: 0; }
.icon-button:hover, .context-button:hover { background: var(--treasure-panel); color: var(--treasure-green); }
button:focus-visible { outline: 2px solid var(--treasure-green); outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .45; }
.new-chat-button { width: 34px; height: 34px; background: var(--treasure-green-soft); color: var(--treasure-green); border: 1px solid var(--treasure-border); border-radius: 13px; }
.treasure-main { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.treasure-header { min-height: 50px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 24px; border-bottom: 1px solid var(--treasure-border); background: var(--treasure-panel); box-sizing: border-box; }
.page-label { font-size: 14px; font-weight: 600; white-space: nowrap; }
.header-actions { display: flex; align-items: center; gap: 6px; }
.context-button { max-width: 160px; font-size: 12px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.context-controls { width: min(320px, 75vw); display: grid; gap: 8px; } .about-discovery { max-width: 280px; }
.session-panel { width: 240px; flex: 0 0 240px; border-right: 1px solid var(--treasure-border); background: var(--treasure-panel); padding: 14px 10px; overflow: auto; box-sizing: border-box; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; } .history-empty { font-size: 12px; padding: 8px; color: var(--treasure-muted); }
.session-item { display: block; width: 100%; margin: 4px 0; border: 0; border-radius: 8px; padding: 10px; text-align: left; background: transparent; color: inherit; cursor: pointer; overflow-wrap: anywhere; } .session-item.active, .session-item:hover { background: var(--treasure-green-soft); color: var(--treasure-green); }
.conversation-panel { position: relative; display: flex; flex: 1; flex-direction: column; min-height: 0; min-width: 0; overflow: hidden; background-image: radial-gradient(var(--treasure-dot) 1px, transparent 1px); background-size: 24px 24px; }
.welcome-scroll { flex: 1; min-height: 0; overflow: auto; display: flex; } .welcome-scroll > * { min-height: 100%; }
.loading-state { margin: auto; } .access-notice { font-size: 12px; margin: 0; padding: 8px 24px; background: var(--treasure-panel); color: var(--treasure-muted); }
.message-list { flex: 1; min-height: 0; overflow: auto; padding: 24px 24px 40px; }
.message-column { max-width: 768px; margin: 0 auto; }
.message { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 24px; }
.message-avatar { display: flex; align-items: center; justify-content: center; flex: 0 0 30px; height: 30px; border: 1px solid var(--treasure-border); border-radius: 50%; background: var(--treasure-green-soft); color: var(--treasure-green); }
.message-content { flex: 1; min-width: 0; position: relative; }
.message-role { font-size: 12px; color: var(--treasure-muted); margin-bottom: 4px; }
.message-body { padding: 14px 16px; border: 1px solid var(--treasure-border); border-radius: 4px 18px 18px 18px; background: var(--treasure-card); box-shadow: 0 1px 3px rgb(0 0 0 / .04); overflow-wrap: anywhere; line-height: 1.8; }
.message-body :deep(.md-body) { color: inherit; font-size: 14px; } .message-body :deep(p:first-child) { margin-top: 0; } .message-body :deep(p:last-child) { margin-bottom: 0; }
.message.user { flex-direction: row-reverse; margin-bottom: 24px; padding-left: 44px; }
.message.user .message-avatar { background: var(--treasure-card); color: var(--treasure-muted); }
.message.user .message-content { flex: 0 1 auto; max-width: 100%; }
.message.user .message-body { background: var(--treasure-green); color: var(--treasure-card); border-color: var(--treasure-green); border-radius: 18px 18px 4px 18px; white-space: pre-wrap; font-weight: 500; }
.copy-message { opacity: 0; height: 24px; font-size: 14px; } .message:hover .copy-message, .message:focus-within .copy-message { opacity: 1; }
.proposal-list { display: grid; gap: 10px; margin-top: 14px; }
.trace { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; color: var(--treasure-muted); font-size: 11px; } .trace > span { display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px; border: 1px solid var(--treasure-border); border-radius: 20px; background: var(--treasure-card); box-shadow: 0 1px 2px rgb(0 0 0 / .05); } .trace > .running { background: var(--treasure-green-soft); color: var(--treasure-green); } .trace small { color: var(--treasure-muted); }
.grounding { margin: 12px 40px; color: var(--treasure-muted); font-size: 12px; }
.bottom-composer { position: relative; z-index: 1; }
.pet-corner { position: absolute; right: 22px; bottom: 134px; width: 144px; pointer-events: none; }
.treasure-pet { width: 144px; height: 144px; flex: none; }
.pet-bubble { position: relative; margin: 0 0 12px -24px; padding: 10px 12px; font-size: 12px; border: 1px solid var(--treasure-border); border-radius: 14px; background: var(--treasure-card); color: var(--treasure-ink); box-shadow: 0 1px 3px rgb(0 0 0 / .04); }
.pet-bubble::after { content: ""; position: absolute; bottom: -5px; left: 50%; width: 8px; height: 8px; transform: rotate(45deg); background: var(--treasure-card); border-right: 1px solid var(--treasure-border); border-bottom: 1px solid var(--treasure-border); }
.error-text { margin: 0; padding: 8px 24px; color: var(--error-color, #c2410c); }
@media (hover: none) { .copy-message { opacity: 1; } }
@media (max-width: 760px) { .treasure-header { padding: 8px 12px; } .session-panel { position: absolute; top: 50px; bottom: 0; left: 48px; z-index: 3; box-shadow: 4px 0 14px rgb(0 0 0 / .08); } .treasure-page { position: relative; } .context-button { max-width: 85px; } .header-actions { gap: 2px; } .message-list { padding: 18px 12px; } .message { gap: 6px; } .message.user { padding-left: 20px; } .message-avatar { flex-basis: 26px; height: 26px; } .pet-corner { width: 88px; right: 10px; bottom: 140px; } .treasure-pet { width: 88px; height: 88px; } .pet-bubble { display: none; } }
@media (max-width: 480px) { .context-button { display: none; } }
</style>
