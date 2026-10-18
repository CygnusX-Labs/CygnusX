// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { NMessageProvider } from 'naive-ui'
import { describe, expect, it, vi } from 'vitest'
import TreasureMouseView from '@/views/TreasureResearchWorkbench.vue'

const calls = vi.hoisted(() => ({ messages: vi.fn(), sessions: vi.fn(), related: vi.fn(), projects: vi.fn() }))
vi.mock('@/components/research/TreasureOriginalDisplay.vue', () => ({ default: {
  props: ['presentation'],
  template: `<div><span v-for="project in presentation.projects">{{ project.name }}</span><p>{{ presentation.accessError || presentation.historyError }}</p><p v-if="!presentation.loading && !presentation.accessError && !presentation.historyError && !presentation.sessions.length">暂无平台会话</p><button v-for="session in presentation.sessions" class="session-item" @click="presentation.onSelectSession(session.id)">{{ session.title }}</button><button class="send-message" @click="$emit('submit', 'A1 query')">发送</button><article v-for="message in presentation.messages">{{ message.content }}</article></div>`,
  emits: ['submit'],
} }))
vi.mock('@/api/projects', () => ({ projectsApi: { listProjects: calls.projects } }))
vi.mock('@/api/researchAgent', () => ({ researchFailure: () => '服务不可用', researchStreamUrl: (id: string) => '/stream/' + id,
  researchAgentApi: { capabilities: async () => ({ read_sessions: true, read_discovery: true, prepare_import: true }), listSessions: calls.sessions, getMessages: calls.messages } }))
vi.mock('@/api/agentTools', () => ({ agentToolsApi: { capabilities: async () => ({ tools: [{ capability_id: 'tasks.list_related' }] }), related: calls.related }, asToolProposal: () => null }))
const sessionA = { session_id: 'session-a', title: '会话 A', project_id: null }
const sessionB = { session_id: 'session-b', title: '会话 B', project_id: null }
async function settle() { for (let i = 0; i < 8; i++) { await Promise.resolve(); await nextTick() } }

describe('treasure session isolation', () => {
  it('late restore from previous session cannot replace current messages or tool records', async () => {
    calls.projects.mockResolvedValue([])
    calls.sessions.mockResolvedValue([sessionA, sessionB])
    calls.related.mockResolvedValue([])
    calls.messages.mockResolvedValue([])
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp({ render: () => h(NMessageProvider, null, { default: () => h(TreasureMouseView) }) })
    app.mount(host)
    try {
      await settle()
      let resolvePrevious!: (value: unknown[]) => void
      calls.messages.mockImplementation((session: string) => session === 'session-a'
        ? new Promise(resolve => { resolvePrevious = resolve })
        : Promise.resolve([{ message_id: 'b', role: 'assistant', content: 'B 的真实记录', metadata_json: {} }]))
      const sessions = host.querySelectorAll<HTMLButtonElement>('.session-item')
      sessions[0].click()
      await nextTick()
      sessions[1].click()
      await settle()
      resolvePrevious([{ message_id: 'a', role: 'assistant', content: 'A 的迟到记录', metadata_json: {} }])
      await settle()
      expect(host.textContent).toContain('B 的真实记录')
      expect(host.textContent).not.toContain('A 的迟到记录')
      expect(calls.related).toHaveBeenLastCalledWith('session-b')
    } finally { app.unmount(); host.remove(); vi.clearAllMocks() }
  })
  it('late SSE frames from A1 cannot contaminate A2 after switching sessions', async () => {
    calls.projects.mockResolvedValue([])
    calls.sessions.mockResolvedValue([sessionA, sessionB])
    calls.related.mockResolvedValue([])
    calls.messages.mockResolvedValue([])
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined
    const stream = new ReadableStream<Uint8Array>({ start: controller => { streamController = controller } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp({ render: () => h(NMessageProvider, null, { default: () => h(TreasureMouseView) }) })
    app.mount(host)
    try {
      await settle()
      host.querySelector<HTMLButtonElement>('.send-message')!.click()
      await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
      const sessions = host.querySelectorAll<HTMLButtonElement>('.session-item')
      sessions[1].click()
      await settle()
      streamController!.enqueue(new TextEncoder().encode('data: {"event":"delta","delta":"A1 stale SSE"}\n\ndata: {"event":"end"}\n\n'))
      streamController!.close()
      await settle()
      expect(host.textContent).not.toContain('A1 stale SSE')
      expect(calls.messages).toHaveBeenLastCalledWith('session-b')
    } finally { app.unmount(); host.remove(); vi.unstubAllGlobals(); vi.clearAllMocks() }
  })
  it('T12 stale project lists cannot overwrite the refreshed account context', async () => {
    let resolveOld!: (value: unknown[]) => void
    calls.projects.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockResolvedValue([{ id: 'p2', name: 'current project' }])
    calls.sessions.mockResolvedValue([])
    const host = document.createElement('div'); document.body.append(host)
    const app = createApp(TreasureMouseView); app.mount(host)
    try {
      await settle()
      window.dispatchEvent(new Event('focus')); await settle()
      resolveOld([{ id: 'p1', name: 'stale project' }]); await settle()
      expect(host.textContent).toContain('current project')
      expect(host.textContent).not.toContain('stale project')
    } finally { app.unmount(); host.remove(); vi.clearAllMocks() }
  })

})
