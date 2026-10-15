// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { NMessageProvider } from 'naive-ui'
import { describe, expect, it, vi } from 'vitest'
import TreasureMouseView from '@/views/TreasureMouseView.vue'

const calls = vi.hoisted(() => ({ messages: vi.fn(), sessions: vi.fn(), related: vi.fn() }))
vi.mock('@/api/projects', () => ({ projectsApi: { listProjects: async () => [] } }))
vi.mock('@/api/researchAgent', () => ({ researchStreamUrl: (id: string) => '/stream/' + id,
  researchAgentApi: { listSessions: calls.sessions, getMessages: calls.messages } }))
vi.mock('@/api/agentTools', () => ({ agentToolsApi: { related: calls.related }, asToolProposal: () => null }))
const sessionA = { session_id: 'session-a', title: '会话 A', project_id: null }
const sessionB = { session_id: 'session-b', title: '会话 B', project_id: null }
async function settle() { for (let i = 0; i < 8; i++) { await Promise.resolve(); await nextTick() } }

describe('treasure session isolation', () => {
  it('late restore from previous session cannot replace current messages or tool records', async () => {
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
})
