// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, reactive } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ClaimEvidencePanel from '@/components/ClaimEvidencePanel.vue'
import { claimProvenanceApi, type ClaimProvenance } from '@/api/claimProvenance'

vi.mock('@/api/claimProvenance', () => ({ claimProvenanceApi: { inspect: vi.fn() } }))
const proof = (): ClaimProvenance => ({
  schema_version: 'cygnusx.claim_provenance.v1', claim_id: 'a'.repeat(64), claim_text: '<img src=x onerror=alert(1)>', claim_text_verified: false,
  project_id: 'first', task_id: 'task', source_report_id: null, report_version: null, report_snapshot_id: null, snapshot_digest: null,
  result_observation_id: 'observation', observation_digest: 'b'.repeat(64), observation_binding: 'VERIFIED_ASSOCIATION',
  file_record_id: 'file', file_sha256: 'c'.repeat(64), table_identifier: 'deg.tsv', row_identifier: 'fixture_gene', row_number: 2,
  column_identifier: 'padj', value: 0.03, verification_status: 'VERIFIED_VALUE', supported_statement: 'fixture_gene / padj = 0.03', supported_statement_status: 'SUPPORTED_CLAIM',
  interpretation_status: 'AI_INTERPRETATION', dataset_version_id: 'version', analysis_link_id: 'link', definition_digest: null, execution_binding_digest: null,
  definition_status: 'NOT_RECORDED', input_file_record_ids: [], missing_evidence: ['EXECUTION_DEFINITION_NOT_RECORDED'], reproducibility_status: 'NOT_RUN', verification_scope: 'current_cell_bytes_not_claim_truth_or_historical_execution',
})
const cleanup: (() => void)[] = []
async function settle() { for (let i = 0; i < 20; i++) { await Promise.resolve(); await nextTick() } }
function mount() {
  const props = reactive({ projectId: 'first', taskId: 'task', artifacts: [{ file_record_id: 'file', logical_name: 'deg.tsv', integrity: 'VERIFIED' as const, category: 'deg', size: 20, sha256: 'c'.repeat(64), declared_sha256: null, file_url: null }], reports: [] })
  const host = document.createElement('div'), app = createApp({ render: () => h(ClaimEvidencePanel, props) })
  app.component('RouterLink', defineComponent({ setup(_, { slots }) { return () => h('a', slots.default?.()) } }))
  app.mount(host); cleanup.push(() => app.unmount())
  return { host, props }
}
async function query(host: HTMLElement) {
  const label = [...host.querySelectorAll('label')].find(el => el.textContent?.includes('基因 / feature'))!
  const input = label.querySelector('input')!
  input.value = 'fixture_gene'; input.dispatchEvent(new Event('input', { bubbles: true })); await settle()
  const button = [...host.querySelectorAll('button')].find(el => el.textContent?.includes('核验结果依据'))!
  expect(button.disabled).toBe(false); button.click(); await settle()
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(claimProvenanceApi.inspect).mockResolvedValue(proof()) })
afterEach(() => cleanup.splice(0).forEach(fn => fn()))

it('shows the verified numeric scope, actual identities, missing evidence and escaped interpretation', async () => {
  const { host } = mount(); await query(host)
  expect(claimProvenanceApi.inspect).toHaveBeenCalledWith('first', { task_id: 'task', file_record_id: 'file', feature_id: 'fixture_gene', column: 'padj', source_report_id: null }, expect.any(AbortSignal))
  expect(host.textContent).toContain('VERIFIED_VALUE')
  expect(host.textContent).toContain('AI_INTERPRETATION（未核验）')
  expect(host.textContent).toContain('EXECUTION_DEFINITION_NOT_RECORDED')
  expect(host.textContent).toContain('DatasetVersion version')
  expect(host.textContent).toContain('0.03')
  expect(host.querySelector('img')).toBeNull()
  expect(host.textContent).not.toContain('FULLY_REPRODUCIBLE')
})

it('discards a late proof after project/task change and clears the form', async () => {
  let complete!: (value: ClaimProvenance) => void
  vi.mocked(claimProvenanceApi.inspect).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const { host, props } = mount(); await query(host)
  props.projectId = 'second'; props.taskId = 'other'; await settle()
  complete(proof()); await settle()
  expect(host.textContent).not.toContain('0.03')
  expect(host.textContent).not.toContain('DatasetVersion version')
})

it('shows access denial instead of empty evidence or raw errors', async () => {
  vi.mocked(claimProvenanceApi.inspect).mockRejectedValueOnce({ response: { status: 403 }, message: '/private/token' })
  const { host } = mount(); await query(host)
  expect(host.textContent).toContain('当前无权访问或证据记录不可用')
  expect(host.textContent).not.toContain('/private/token')
})
