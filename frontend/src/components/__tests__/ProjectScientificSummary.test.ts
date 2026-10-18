// @vitest-environment jsdom
import { createApp, h, nextTick, reactive } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ProjectScientificSummary from '@/components/ProjectScientificSummary.vue'
import { projectReportApi, type ReportPreparation } from '@/api/projectReport'
import type { ClaimCellQuery } from '@/api/claimProvenance'
vi.mock('@/api/projectReport', () => ({ projectReportApi: { prepare: vi.fn(), create: vi.fn(), status: vi.fn(), preview: vi.fn(), download: vi.fn() } }))
const prepared = (): ReportPreparation => ({ prepare_digest: 'a'.repeat(64), source: { manifest: { selection: { kind: 'results', task_ids: [], report_ids: [] } }, source_manifest_digest: 'b'.repeat(64), selection_digest: 'c'.repeat(64), selection: { claims: [] } } })
const cleanup: (() => void)[] = []
async function settle() { for (let i = 0; i < 20; i++) { await Promise.resolve(); await nextTick() } }
function mount() {
  const props = reactive({ projectId: 'first', manifestId: 'm0', claims: [] as ClaimCellQuery[] })
  const host = document.createElement('div'), app = createApp({ render: () => h(ProjectScientificSummary, props) })
  app.mount(host); cleanup.push(() => app.unmount()); return { host, props }
}
async function click(host: HTMLElement, text: string) { const button = [...host.querySelectorAll('button')].find(b => b.textContent?.includes(text)); expect(button).toBeTruthy(); button!.click(); await settle() }
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); vi.mocked(projectReportApi.prepare).mockResolvedValue(prepared()) })
afterEach(() => cleanup.splice(0).forEach(fn => fn()))
it('invalidates confirmation after explicit claim selection changes', async () => {
  const { host, props } = mount(); await click(host, '核验来源并预览'); expect(host.textContent).toContain('确认冻结范围')
  props.claims = [{ task_id: 'task', file_record_id: 'file', feature_id: 'gene', column: 'pvalue' }]; await settle()
  expect(host.textContent).not.toContain('确认冻结范围'); expect(projectReportApi.create).not.toHaveBeenCalled()
})
it('ignores late prepare after project switch', async () => {
  let finish!: (value: ReportPreparation) => void
  vi.mocked(projectReportApi.prepare).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const { host, props } = mount(); await click(host, '核验来源并预览'); props.projectId = 'second'; await settle(); finish(prepared()); await settle()
  expect(host.textContent).not.toContain('确认冻结范围'); expect(projectReportApi.create).not.toHaveBeenCalled()
})
it.each([409, 503, 403])('shows safe failure for drift, closed gate or denial (%s)', async status => {
  vi.mocked(projectReportApi.prepare).mockRejectedValue({ response: { status }, message: '/private/token' })
  const { host } = mount(); await click(host, '核验来源并预览'); expect(host.querySelector('[role=alert]')).toBeTruthy(); expect(host.textContent).not.toContain('/private/token')
})
