// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Workbench from '@/views/TreasureResearchWorkbench.vue'
import { researchFailure } from '@/api/researchAgent'
const calls = vi.hoisted(() => ({ capabilities: vi.fn(), projects: vi.fn(), sessions: vi.fn(), messages: vi.fn() }))
vi.mock('@/api/projects', () => ({ projectsApi: { listProjects: calls.projects } }))
vi.mock('@/api/researchAgent', async (original) => ({
  ...await original<typeof import('@/api/researchAgent')>(),
  researchAgentApi: { capabilities: calls.capabilities, listSessions: calls.sessions, getMessages: calls.messages },
}))
vi.mock('@/components/research/TreasureOriginalDisplay.vue', () => ({ default: {
  props: ['presentation'],
  template: `<div><p>{{ presentation.accessError || presentation.historyError }}</p><p v-if="!presentation.loading && !presentation.accessError && !presentation.historyError && !presentation.sessions.length">暂无平台会话</p><button v-for="session in presentation.sessions" class="session-item" @click="presentation.onSelectSession(session.id)">{{ session.title }}</button><article v-for="message in presentation.messages">{{ message.content }}</article></div>`,
} }))
vi.mock('@/components/research/AgentToolPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/research/DatasetWorkspace.vue', () => ({ default: { template: '<div />' } }))
async function settle() { for (let i = 0; i < 12; i++) { await Promise.resolve(); await nextTick() } }
let cleanup: (() => void) | undefined
async function mount() {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(Workbench)
  app.mount(host)
  cleanup = () => { app.unmount(); host.remove() }
  await settle()
  return host
}
beforeEach(() => {
  vi.resetAllMocks()
  calls.projects.mockResolvedValue([])
  calls.sessions.mockResolvedValue([])
  calls.messages.mockResolvedValue([])
})
afterEach(() => cleanup?.())
describe('treasure access preflight', () => {
  it('skips protected calls when disabled', async () => {
    calls.capabilities.mockResolvedValue({ read_sessions: false, read_discovery: false, reason_code: 'FEATURE_DISABLED' })
    const host = await mount()
    expect(calls.projects).not.toHaveBeenCalled()
    expect(calls.sessions).not.toHaveBeenCalled()
    expect(host.textContent).toContain('入口尚未启用')
    expect(host.querySelector('.session-panel')).toBeNull()
    expect(host.textContent).not.toContain('暂无平台会话')
  })
  it('loads capabilities before projects and sessions', async () => {
    calls.capabilities.mockResolvedValue({ read_sessions: true, read_discovery: true })
    const host = await mount()
    expect(calls.capabilities.mock.invocationCallOrder[0]).toBeLessThan(calls.projects.mock.invocationCallOrder[0])
    expect(calls.projects.mock.invocationCallOrder[0]).toBeLessThan(calls.sessions.mock.invocationCallOrder[0])
    expect(host.textContent).toContain('暂无平台会话')
  })
  it('clears private history after revocation', async () => {
    calls.capabilities.mockResolvedValueOnce({ read_sessions: true, read_discovery: true })
      .mockResolvedValueOnce({ read_sessions: false, reason_code: 'MODULE_LOCKED' })
    calls.sessions.mockResolvedValue([{ session_id: 's', title: '会话一', project_id: null }])
    calls.messages.mockResolvedValue([{ message_id: 'm', role: 'assistant', content: '私有历史内容', metadata_json: {} }])
    const host = await mount()
    expect(host.textContent).toContain('私有历史内容')
    window.dispatchEvent(new Event('focus'))
    await settle()
    expect(host.textContent).not.toContain('私有历史内容')
    expect(host.textContent).toContain('尚无寻宝鼠模块权限')
    expect(calls.sessions).toHaveBeenCalledTimes(1)
  })
  it('does not disguise a failed preflight as empty history', async () => {
    calls.capabilities.mockRejectedValue({ response: { status: 401 } })
    const host = await mount()
    expect(host.textContent).toContain('登录状态已失效')
    expect(host.textContent).not.toContain('暂无平台会话')
    expect(calls.sessions).not.toHaveBeenCalled()
  })
})
describe('safe research errors', () => {
  it.each([
    [401, undefined, '登录状态已失效'], [403, 'MODULE_LOCKED', '尚无寻宝鼠模块权限'],
    [403, 'PROJECT_FORBIDDEN', '项目授权已变更'], [422, undefined, '请求参数不符合要求'],
    [503, 'PROVIDER_UNAVAILABLE', '平台模型暂不可用'], [503, 'NODE_UNAVAILABLE', '科研发现服务暂不可用'],
  ])('maps %s/%s without exposing details', (status, code, expected) => {
    const result = researchFailure({ response: { status, data: { code, detail: 'SECRET INTERNAL TRACE' } } })
    expect(result).toContain(expected)
    expect(result).not.toContain('SECRET')
  })
})
