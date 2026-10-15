<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NEmpty, NInput, NSelect, NSpin, useMessage } from 'naive-ui'
import { projectsApi, type ProjectItem } from '@/api/projects'
import { researchAgentApi, researchStreamUrl, type DiscoveryProposal, type ResearchMessage, type ResearchSession } from '@/api/researchAgent'
import DiscoveryProposalCard from '@/components/research/DiscoveryProposalCard.vue'
import AgentToolPanel from '@/components/research/AgentToolPanel.vue'
import DatasetWorkspace from '@/components/research/DatasetWorkspace.vue'

const message = useMessage()
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
const proposals = computed(() => messages.value.flatMap((item) => item.metadata_json?.proposals || []))

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
  sessions.value = await researchAgentApi.listSessions(selectedProjectId.value || undefined)
  if (sessions.value.length && !currentSession.value) await selectSession(sessions.value[0])
}

async function selectSession(session: ResearchSession) {
  stopCurrentStream()
  const generation = sessionGeneration
  currentSession.value = session
  messages.value = []
  const restored = await researchAgentApi.getMessages(session.session_id)
  if (generation === sessionGeneration) messages.value = restored
}

async function createSession() {
  stopCurrentStream()
  const generation = sessionGeneration
  const session = await researchAgentApi.createSession(selectedProjectId.value || undefined)
  if (generation !== sessionGeneration) return
  currentSession.value = session
  messages.value = []
  sessions.value = [currentSession.value, ...sessions.value]
  streamError.value = ''
}

async function send() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  if (!currentSession.value) await createSession()
  if (!currentSession.value) return
  const generation = sessionGeneration
  const sessionId = currentSession.value.session_id
  const projectId = currentSession.value.project_id || null
  draft.value = ''
  streamError.value = ''
  toolTrace.value = []
  grounding.value = null
  messages.value.push({ message_id: `local-${Date.now()}`, role: 'user', content, status: 'complete', metadata_json: {}, created_at: new Date().toISOString() })
  const assistant: ResearchMessage = { message_id: `stream-${Date.now()}`, role: 'assistant', content: '', status: 'streaming', metadata_json: {}, created_at: new Date().toISOString() }
  messages.value.push(assistant)
  sending.value = true
  controller.value = new AbortController()
  try {
    const response = await fetch(researchStreamUrl(sessionId), {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
      body: JSON.stringify({ content }), signal: controller.value.signal,
    })
    if (!response.ok || !response.body) throw new Error(`科研发现请求失败（${response.status}）`)
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
        if (event.event === 'error') streamError.value = String(event.error || '科研发现服务异常')
      }
    }
    assistant.status = streamError.value ? 'error' : assistant.status === 'cancelled' ? 'cancelled' : 'complete'
  } catch (error) {
    if (generation === sessionGeneration && (error as Error).name !== 'AbortError') streamError.value = (error as Error).message
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
}

async function changeProject(value: string) {
  stopCurrentStream()
  selectedProjectId.value = value || null
  currentSession.value = null
  messages.value = []
  await loadSessions()
}

onMounted(async () => {
  try {
    projects.value = await projectsApi.listProjects()
    await loadSessions()
  } catch (error) {
    streamError.value = (error as Error).message || '科研发现入口暂时不可用'
  } finally { loading.value = false }
})
onUnmounted(() => controller.value?.abort())
</script>

<template>
  <main class="treasure-page" aria-labelledby="treasure-title">
    <header class="treasure-header">
      <div><p class="eyebrow">CygnusX BioOps</p><h1 id="treasure-title">科研寻宝鼠</h1><p>面向 GEO、SRA、ENA 与文献的只读科研发现。</p></div>
      <div class="context-controls"><label for="project-select">项目上下文</label><NSelect id="project-select" :value="selectedProjectId || ''" :options="projectOptions" @update:value="changeProject" /><NButton secondary @click="createSession">新会话</NButton></div>
    </header>
    <section class="treasure-layout">
      <aside class="session-panel" aria-label="科研发现会话">
        <div class="panel-title"><strong>历史会话</strong><span>{{ sessions.length }}</span></div>
        <NSpin v-if="loading" size="small" />
        <NEmpty v-else-if="!sessions.length" description="暂无平台会话" />
        <button v-for="session in sessions" v-else :key="session.session_id" class="session-item" :class="{ active: currentSession?.session_id === session.session_id }" @click="selectSession(session)">{{ session.title }}</button>
      </aside>
      <section class="conversation-panel">
        <DatasetWorkspace v-if="currentSession" :key="`dataset-${currentSession.session_id}`" ref="datasetPanel" :project-id="currentSession.project_id" />
        <AgentToolPanel v-if="currentSession" :key="currentSession.session_id" ref="toolPanel" :session-id="currentSession.session_id" />
        <div v-if="loading" class="loading-state"><NSpin /> 正在加载科研发现</div>
        <NEmpty v-else-if="!messages.length" description="从一个科研问题开始，例如：寻找小鼠肝脏单细胞 RNA-seq 数据集" class="empty-state" />
        <div v-else class="message-list" aria-live="polite">
          <article v-for="item in messages" :key="item.message_id" class="message" :class="item.role"><div class="message-role">{{ item.role === 'user' ? '你' : '寻宝鼠' }}</div><div class="message-body">{{ item.content || (item.status === 'streaming' ? '正在检索…' : '') }}</div><div v-if="item.metadata_json?.proposals?.length" class="proposal-list"><DiscoveryProposalCard v-for="proposal in item.metadata_json.proposals as DiscoveryProposal[]" :key="proposal.proposal_id" :proposal="proposal" @inspect="toolPanel?.prepare($event)" @prepare-import="datasetPanel?.discover($event)" /></div></article>
          <div v-if="toolTrace.length" class="trace" aria-label="工具调用轨迹"><strong>检索过程</strong><span v-for="(tool, index) in toolTrace" :key="index">{{ tool.label || tool.name }} · {{ tool.status }}</span></div>
          <div v-if="grounding" class="grounding">已保留正文与证据编号的核验状态，请以来源页面为准。</div>
        </div>
        <p v-if="streamError" class="error-text" role="alert">{{ streamError }}</p>
        <form class="composer" @submit.prevent="send"><NInput v-model:value="draft" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" maxlength="12000" placeholder="描述你想寻找的研究、物种或实验条件" aria-label="科研发现问题" @keydown.enter.exact.prevent="send" /><NButton v-if="sending" type="warning" @click="cancel">取消检索</NButton><NButton v-else type="primary" attr-type="submit" :disabled="!draft.trim()">发送</NButton></form>
      </section>
    </section>
  </main>
</template>

<style scoped>
.treasure-page { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 24px clamp(16px, 3vw, 42px); background: var(--neutral-bg); color: var(--neutral-text-primary); }
.treasure-header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 1px solid var(--neutral-border); padding-bottom: 18px; }
.eyebrow { margin: 0; color: var(--primary-color); font-size: 12px; font-weight: 700; text-transform: uppercase; }
h1 { margin: 3px 0; font-size: 26px; } .treasure-header p { margin: 0; color: var(--neutral-text-secondary); }
.context-controls { display: flex; align-items: end; gap: 10px; min-width: min(460px, 100%); } .context-controls label { font-size: 12px; color: var(--neutral-text-secondary); }
.treasure-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 18px; flex: 1; min-height: 0; padding-top: 18px; }
.session-panel, .conversation-panel { min-height: 0; border: 1px solid var(--neutral-border); border-radius: 8px; background: var(--neutral-card); } .session-panel { padding: 12px; overflow: auto; }
.panel-title { display: flex; justify-content: space-between; margin-bottom: 10px; } .session-item { display: block; width: 100%; margin: 4px 0; border: 0; border-radius: 6px; padding: 9px; text-align: left; background: transparent; color: inherit; cursor: pointer; overflow-wrap: anywhere; } .session-item.active, .session-item:hover { background: var(--neutral-bg); color: var(--primary-color); }
.conversation-panel { display: flex; flex-direction: column; overflow: hidden; } .message-list { flex: 1; overflow: auto; padding: 22px clamp(14px, 4vw, 56px); } .empty-state, .loading-state { margin: auto; }
.message { max-width: 900px; margin: 0 auto 20px; } .message-role { margin-bottom: 4px; color: var(--neutral-text-secondary); font-size: 12px; font-weight: 700; } .message-body { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.65; } .message.user .message-body { padding: 10px 12px; border-radius: 7px; background: var(--neutral-bg); }
.proposal-list { display: grid; gap: 10px; margin-top: 14px; } .trace, .grounding { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px auto; max-width: 900px; color: var(--neutral-text-secondary); font-size: 12px; } .trace span { padding: 3px 7px; background: var(--neutral-bg); border-radius: 4px; } .grounding { color: var(--primary-color); }
.composer { display: flex; gap: 10px; align-items: end; padding: 14px clamp(14px, 4vw, 56px); border-top: 1px solid var(--neutral-border); } .composer :deep(.n-input) { flex: 1; } .error-text { margin: 0 20px 8px; color: var(--error-color, #c2410c); }
@media (max-width: 760px) { .treasure-page { padding: 16px 10px; } .treasure-header { flex-direction: column; } .context-controls { min-width: 0; align-items: stretch; flex-wrap: wrap; } .context-controls :deep(.n-select) { flex: 1 1 100%; } .treasure-layout { grid-template-columns: 1fr; } .session-panel { max-height: 150px; } .composer { flex-direction: column; align-items: stretch; } }
</style>
