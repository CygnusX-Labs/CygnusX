// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, reactive } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ProjectResearchDelivery from '@/components/ProjectResearchDelivery.vue'
import { projectDeliveryApi, type DeliveryInventory, type ExportJob, type ExportPreview } from '@/api/projectDelivery'

vi.mock('@/api/projectDelivery', () => ({ projectDeliveryApi: {
  inventory: vi.fn(), summaryPreview: vi.fn(), prepare: vi.fn(), create: vi.fn(), status: vi.fn(), retry: vi.fn(), download: vi.fn(),
} }))
const inventory = (id = 'first'): DeliveryInventory => ({
  project_id: id, datasets: [], runtime_admission: 'BLOCKED', truncated: false,
  association_status: 'VERIFIED_ASSOCIATION', historical_tasks: { status: 'NOT_RECORDED', reason: 'NO_FK' }, export_enabled: true,
})
const preview = (id = 'first'): ExportPreview => ({
  manifest_digest: 'a'.repeat(64), manifest: {
    project_id: id, selection: { kind: 'evidence', task_ids: [], report_ids: [] },
    evidence_status: 'partial', files: [{ path: 'README.md', size: 20, sha256: 'b'.repeat(64) }],
    references: [{ kind: 'task', id: null, status: 'NOT_RECORDED', disposition: 'missing', reason: 'NO_TASK' }],
    gaps: ['SCIENTIFIC_REPORT_MISSING', 'REPORT_SNAPSHOT_MISSING'], reproduction_status: 'NOT_RUN',
  },
})
const ready = (): ExportJob => ({
  id: 'job', project_id: 'first', status: 'ready', manifest_digest: 'a'.repeat(64), evidence_partial: true,
  attempt_count: 1, retryable: false, error_code: null, archive_sha256: 'b'.repeat(64), archive_size: 50, file_record_id: 'file',
})
async function settle() { for (let i = 0; i < 20; i++) { await Promise.resolve(); await nextTick() } }
const cleanups: (() => void)[] = []
function mount() {
  const props = reactive({ projectId: 'first' })
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(ProjectResearchDelivery, props) })
  app.component('RouterLink', defineComponent({ setup(_, { slots }) { return () => h('a', slots.default?.()) } }))
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return { host, props }
}
async function click(host: HTMLElement, text: string) {
  const button = [...host.querySelectorAll('button')].find(b => b.textContent?.includes(text))
  expect(button).toBeTruthy(); button!.click(); await settle()
}
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear()
  vi.mocked(projectDeliveryApi.inventory).mockResolvedValue(inventory())
  vi.mocked(projectDeliveryApi.prepare).mockResolvedValue(preview())
  vi.mocked(projectDeliveryApi.create).mockResolvedValue({ ...ready(), status: 'queued' })
  vi.mocked(projectDeliveryApi.status).mockResolvedValue(ready())
})
afterEach(() => { cleanups.splice(0).forEach(fn => fn()) })

it('previews the default evidence selection, shows actual gaps, confirms and polls a real job response', async () => {
  const { host } = mount(); await settle()
  expect(host.textContent).toContain('没有可信关联的分析任务')
  await click(host, '预览范围')
  expect(projectDeliveryApi.prepare).toHaveBeenCalledWith('first', { kind: 'evidence', task_ids: [], report_ids: [] }, expect.any(AbortSignal))
  expect(host.textContent).toContain('REPORT_SNAPSHOT_MISSING')
  expect(host.textContent).toContain('SCIENTIFIC_REPORT_MISSING')
  await click(host, '确认范围并后台生成')
  expect(projectDeliveryApi.create).toHaveBeenCalledWith('first', preview(), expect.any(String), expect.any(AbortSignal))
  expect(host.textContent).toContain('真实导出状态：ready')
  expect(host.textContent).toContain('导出完成，但科研证据不完整')
  expect(host.textContent).toContain('离线核验')
})

it('drops a late inventory from the old project and clears old preview and job', async () => {
  let finish!: (value: DeliveryInventory) => void
  vi.mocked(projectDeliveryApi.inventory).mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValueOnce(inventory('second'))
  const { host, props } = mount()
  props.projectId = 'second'; await settle(); finish(inventory('first')); await settle()
  await click(host, '预览范围')
  expect(projectDeliveryApi.prepare).toHaveBeenCalledWith('second', expect.anything(), expect.any(AbortSignal))
  expect(host.textContent).not.toContain('REPORT_SNAPSHOT_MISSING') // stale first-project preview refused
  expect(projectDeliveryApi.create).not.toHaveBeenCalled()
})

it.each([
  [{ response: { status: 403, data: { code: 'FEATURE_DISABLED' } } }, '尚未启用'],
  [{ response: { status: 403 } }, '没有权限'],
  [new Error('/private/secret'), '请求失败'],
])('distinguishes disabled, denied and failed requests without exposing raw errors (%s)', async (error, text) => {
  vi.mocked(projectDeliveryApi.inventory).mockRejectedValueOnce(error)
  const { host } = mount(); await settle()
  expect(host.textContent).toContain(text)
  expect(host.textContent).not.toContain('/private/secret')
})

it('disables confirmation while export is disabled and stops at truncated coverage', async () => {
  vi.mocked(projectDeliveryApi.inventory).mockResolvedValueOnce({ ...inventory(), export_enabled: false, truncated: true })
  const { host } = mount(); await settle()
  expect(host.textContent).toContain('项目导出功能尚未启用')
  expect(host.textContent).toContain('不能将截断列表作为完整导出')
  expect([...host.querySelectorAll('button')].find(b => b.textContent?.includes('预览范围'))?.disabled).toBe(true)
})

it('restores the persisted job and displays failure and retry independently of reports', async () => {
  sessionStorage.setItem('project-export:first', 'job')
  vi.mocked(projectDeliveryApi.status).mockResolvedValueOnce({ ...ready(), status: 'failed', retryable: true, error_code: 'storage_or_timeout' })
  vi.mocked(projectDeliveryApi.retry).mockResolvedValueOnce({ ...ready(), status: 'queued' })
  const { host } = mount(); await settle()
  expect(host.textContent).toContain('导出失败：storage_or_timeout')
  await click(host, '重试同一导出')
  expect(projectDeliveryApi.retry).toHaveBeenCalledWith('first', 'job')
  expect(host.textContent).toContain('真实导出状态：ready')
})


it('previews only a script-sandboxed prototype and clears it on project switch', async () => {
  sessionStorage.setItem('project-export:first', 'job')
  vi.mocked(projectDeliveryApi.summaryPreview).mockResolvedValueOnce('<h1>只读原型</h1>')
  const { host, props } = mount(); await settle()
  await click(host, '查看项目综合报告只读原型')
  const frame = host.querySelector('iframe')!
  expect(frame.getAttribute('sandbox')).toBe('')
  expect(frame.getAttribute('srcdoc')).toContain('只读原型')
  expect(projectDeliveryApi.summaryPreview).toHaveBeenCalledWith('first', 'job', expect.any(AbortSignal))
  props.projectId = 'second'; await settle()
  expect(host.querySelector('iframe')).toBeNull()
})
