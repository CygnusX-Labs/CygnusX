// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import ResearchPlanWorkbench from '@/components/ResearchPlanWorkbench.vue'
import { researchPlansApi, type ResearchPlan } from '@/api/researchPlans'
vi.mock('@/api/researchPlans', () => ({ researchPlansApi: { list: vi.fn(), get: vi.fn(), review: vi.fn(), advance: vi.fn(), control: vi.fn(), events: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

it.each([
  [{ response: { status: 403, data: { code: 'FEATURE_DISABLED' } } }, '服务未启用'],
  [{ response: { status: 403 } }, '当前用户无权限'],
  [new Error('private'), '请求失败'],
])('classifies plan loading failure (%s)', async (error, text) => {
  vi.mocked(researchPlansApi.list).mockRejectedValueOnce(error)
  const card = mount()
  try { await settle(); expect(card.host.textContent).toContain(text) }
  finally { card.close() }
})
function plan(project: string, title = 'Synthetic plan'): ResearchPlan {
  return { schema_version: 'cygnusx.research_plan.v1', plan_id: 'plan', version: 1, project_id: project, digest: 'a'.repeat(64), status: 'READY_FOR_REVIEW', mode: 'PLAN_ONLY',
    draft: { schema_version: 'cygnusx.research_plan.v1', research_question: title, assumptions: [], steps: [{ step_id: 'discover', kind: 'DISCOVERY', goal: 'Read sources', depends_on: [], arguments: {}, bindings: [], failure_policy: 'STOP_AND_RECONCILE' }], budget: { max_tool_calls: 20, max_elapsed_seconds: 300, max_model_tokens: 10000, max_retries: 0, estimated_compute_seconds: null, estimated_storage_bytes: null } },
    steps: [{ step_id: 'discover', kind: 'DISCOVERY', capability_id: 'dataset.discover', effect: 'READ_ONLY', approval_required: false, expected_output: 'discovery_proposal', status: 'WAITING_INPUT', invocation_id: null, task_id: null, error_code: null }], gaps: ['LIVE_EXECUTION_BLOCKED'], created_at: '2026-10-15T00:00:00Z', reviewed_at: null, superseded_by: null }
}
async function settle() { for (let i=0; i<10; i++) { await Promise.resolve(); await nextTick() } }
function mount(initialPlanId?: string) {
  const selectedPlan = ref(initialPlanId)
  const project = ref('first'), host = document.createElement('div')
  const app = createApp({ render: () => h(ResearchPlanWorkbench, { projectId: project.value, planId: selectedPlan.value }) })
  app.component('RouterLink', defineComponent({ props: ['to'], setup(props, { slots }) { return () => h('a', { 'data-target': JSON.stringify(props.to) }, slots.default?.()) } }))
  app.mount(host)
  return { project, selectedPlan, host, close: () => app.unmount() }
}
it('does not auto-write and discards stale project plans', async () => {
  let finish!: (value: ResearchPlan[]) => void
  vi.mocked(researchPlansApi.list).mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValueOnce([plan('second', 'Current plan')])
  const card = mount()
  try {
    card.project.value = 'second'; await settle()
    finish([plan('first', 'Stale plan')]); await settle()
    expect(card.host.textContent).toContain('Current plan')
    expect(card.host.textContent).not.toContain('Stale plan')
    expect(researchPlansApi.review).not.toHaveBeenCalled()
    expect(researchPlansApi.advance).not.toHaveBeenCalled()
  } finally { card.close() }
})
it('clears old data after failed switch without exposing provider errors', async () => {
  vi.mocked(researchPlansApi.list).mockResolvedValueOnce([plan('first', 'Private plan')]).mockRejectedValueOnce(new Error('/home/secret token'))
  const card = mount()
  try {
    await settle(); card.project.value = 'second'; await settle()
    expect(card.host.textContent).not.toContain('Private plan')
    expect(card.host.textContent).not.toContain('/home/secret')
    expect(card.host.textContent).toContain('科研计划暂不可用')
  } finally { card.close() }
})
it('binds human review to exact version digest and distinguishes it from execution', async () => {
  const before = plan('first')
  vi.mocked(researchPlansApi.list).mockResolvedValueOnce([before])
  vi.mocked(researchPlansApi.review).mockResolvedValueOnce({ ...before, status: 'APPROVED', reviewed_at: '2026-10-15T01:00:00Z' })
  const card = mount()
  try {
    await settle()
    const button = Array.from(card.host.querySelectorAll('button')).find(b => b.textContent?.includes('确认已审阅计划'))!
    expect(button).toBeTruthy(); button.click(); await settle()
    expect(researchPlansApi.review).toHaveBeenCalledWith('first', 'plan', before.digest)
    expect(researchPlansApi.advance).not.toHaveBeenCalled()
    expect(card.host.textContent).toContain('不会批准后续写动作')
    expect(card.host.textContent).toContain('未知')
    expect(card.host.textContent).toContain('APPROVED')
  } finally { card.close() }
})

it('prevents refresh from invalidating an in-flight review action', async () => {
  const before = plan('first')
  let finish!: (value: ResearchPlan) => void
  vi.mocked(researchPlansApi.list).mockResolvedValueOnce([before])
  vi.mocked(researchPlansApi.review).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const card = mount()
  try {
    await settle()
    const buttons = () => Array.from(card.host.querySelectorAll('button'))
    buttons().find(b => b.textContent?.includes('确认已审阅计划'))!.click()
    await settle()
    const refresh = buttons().find(b => b.textContent?.includes('刷新计划'))!
    expect(refresh.disabled).toBe(true)
    refresh.click(); await settle()
    expect(researchPlansApi.list).toHaveBeenCalledTimes(1)
    finish({ ...before, status: 'APPROVED', reviewed_at: '2026-10-15T01:00:00Z' })
    await settle()
    expect(refresh.disabled).toBe(false)
    expect(card.host.textContent).toContain('APPROVED')
  } finally { card.close() }
})

it('restores an exact persisted version even outside the recent list', async () => {
  const restored = { ...plan('first', 'Historical plan'), plan_id: 'history', version: 2, superseded_by: 'new-version' }
  vi.mocked(researchPlansApi.get).mockResolvedValueOnce(restored)
  const card = mount('history')
  try {
    await settle()
    expect(researchPlansApi.list).not.toHaveBeenCalled()
    expect(researchPlansApi.get).toHaveBeenCalledWith('first', 'history', expect.any(AbortSignal))
    expect(card.host.textContent).toContain('Historical plan')
    const links = Array.from(card.host.querySelectorAll('a')).map(a => JSON.parse(a.getAttribute('data-target')!))
    expect(links).toContainEqual({ path: '/projects/first', query: { planId: 'history' } })
    expect(links).toContainEqual({ path: '/projects/first', query: { planId: 'new-version' } })
    expect(card.host.textContent).not.toContain('确认已审阅计划（不批准执行）')
  } finally { card.close() }
})
it('discards a late version response within the same project', async () => {
  let finish!: (value: ResearchPlan) => void
  vi.mocked(researchPlansApi.get)
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    .mockResolvedValueOnce({ ...plan('first', 'Current version'), plan_id: 'current' })
  const card = mount('old')
  try {
    card.selectedPlan.value = 'current'; await settle()
    finish({ ...plan('first', 'Late historical version'), plan_id: 'old' }); await settle()
    expect(card.host.textContent).toContain('Current version')
    expect(card.host.textContent).not.toContain('Late historical version')
    expect(researchPlansApi.review).not.toHaveBeenCalled()
  } finally { card.close() }
})
