// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, reactive } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import ProjectDetailView from '@/views/ProjectDetailView.vue'
import { projectsApi, type ProjectOverview } from '@/api/projects'
const route = reactive({ params: { projectId: 'first' }, query: { planId: 'persisted-plan' } })
const message = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/api/projects', () => ({ projectsApi: { getProjectOverview: vi.fn(), getCapabilityStatus: vi.fn(), updateProjectSettings: vi.fn() } }))
vi.mock('@/api/chat', () => ({ chatApi: {} }))
vi.mock('naive-ui', async () => ({ ...await vi.importActual('naive-ui'), useMessage: () => message }))
vi.mock('@/components/ResearchPlanWorkbench.vue', () => ({ default: {
  props: ['projectId', 'planId', 'sessions'],
  setup: (props: { projectId: string; planId: string }) => () => h('div', { 'data-plan-context': true }, `${props.projectId}/${props.planId}`),
} }))
vi.mock('@/components/ResearchDeliveryChain.vue', () => ({ default: { render: () => null } }))
function overview(id: string): ProjectOverview {
  return { project: { id, name: `Project ${id}`, slug: id, description: `Description ${id}`, created_at: null, updated_at: null }, sessions: { total: 0, limit: 100, offset: 0, items: [] }, runs: [] }
}
async function settle() { for (let i=0; i<15; i++) { await Promise.resolve(); await nextTick() } }
function mount() {
  const host = document.createElement('div')
  const app = createApp(ProjectDetailView)
  app.component('RouterLink', defineComponent({ setup(_, { slots }) { return () => h('a', slots.default?.()) } }))
  app.mount(host)
  return { host, close: () => app.unmount() }
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(projectsApi.getCapabilityStatus).mockResolvedValue({ research_plan: { enabled: true, allowed: true, reason: 'AVAILABLE' }, research_delivery_read: { enabled: false, allowed: false, reason: 'SERVICE_DISABLED' }, project_export: { enabled: false, allowed: false, reason: 'SERVICE_DISABLED' } }); route.params.projectId = 'first'; route.query.planId = 'persisted-plan' })
it('isolates project overview and persisted plan context from late previous-project responses', async () => {
  let finish!: (value: ProjectOverview) => void
  vi.mocked(projectsApi.getProjectOverview)
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    .mockResolvedValueOnce(overview('second'))
  const card = mount()
  try {
    route.params.projectId = 'second'; await settle()
    finish(overview('first')); await settle()
    expect(card.host.textContent).toContain('Description second')
    expect(card.host.textContent).not.toContain('Description first')
    expect(card.host.querySelector('[data-plan-context]')?.textContent).toBe('second/persisted-plan')
  } finally { card.close() }
})
it('clears previous project data when the next overview fails without leaking raw errors', async () => {
  vi.mocked(projectsApi.getProjectOverview).mockResolvedValueOnce(overview('first')).mockRejectedValueOnce(new Error('/private/secret'))
  const card = mount()
  try {
    await settle(); expect(card.host.textContent).toContain('Description first')
    route.params.projectId = 'second'; await settle()
    expect(card.host.textContent).not.toContain('Description first')
    expect(card.host.querySelector('[data-plan-context]')).toBeNull()
    expect(message.error).toHaveBeenCalledWith('加载项目总览失败')
    expect(card.host.textContent).not.toContain('/private/secret')
  } finally { card.close() }
})

it('hydrates saved research mode and resets it from the next project settings', async () => {
  const first = overview('first')
  first.project.settings = { research_mode: { enabled: true } }
  vi.mocked(projectsApi.getProjectOverview).mockResolvedValueOnce(first).mockResolvedValueOnce(overview('second'))
  const card = mount()
  try {
    await settle()
    expect(card.host.querySelector('[data-test="project-research-default"]')?.getAttribute('aria-checked')).toBe('true')
    route.params.projectId = 'second'; await settle()
    expect(card.host.querySelector('[data-test="project-research-default"]')?.getAttribute('aria-checked')).toBe('false')
  } finally { card.close() }
})

it('does not mount or request research surfaces when service gates are disabled', async () => {
  vi.mocked(projectsApi.getProjectOverview).mockResolvedValueOnce(overview('first'))
  const disabled = { enabled: false, allowed: false, reason: 'SERVICE_DISABLED' as const }
  vi.mocked(projectsApi.getCapabilityStatus).mockResolvedValueOnce({
    research_plan: disabled, research_delivery_read: disabled, project_export: disabled,
  })
  const card = mount()
  try {
    await settle()
    expect(card.host.querySelector('[data-plan-context]')).toBeNull()
    expect(card.host.textContent?.match(/服务未启用/g)).toHaveLength(3)
    expect(card.host.textContent).not.toContain('刷新交付记录')
    expect(card.host.textContent).not.toContain('刷新科研成果')
  } finally { card.close() }
})

it('distinguishes denied capability from a failed capability request', async () => {
  vi.mocked(projectsApi.getProjectOverview).mockResolvedValueOnce(overview('first')).mockResolvedValueOnce(overview('second'))
  const denied = { enabled: true, allowed: false, reason: 'NO_PERMISSION' as const }
  vi.mocked(projectsApi.getCapabilityStatus)
    .mockResolvedValueOnce({ research_plan: denied, research_delivery_read: denied, project_export: denied })
    .mockRejectedValueOnce(new Error('/private/secret'))
  const card = mount()
  try {
    await settle()
    expect(card.host.textContent?.match(/当前用户无权限/g)).toHaveLength(3)
    route.params.projectId = 'second'; await settle()
    expect(card.host.textContent?.match(/请求失败/g)).toHaveLength(3)
    expect(card.host.textContent).not.toContain('/private/secret')
    expect(card.host.querySelector('[data-plan-context]')).toBeNull()
  } finally { card.close() }
})
