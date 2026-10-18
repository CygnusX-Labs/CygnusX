// @vitest-environment jsdom
import { effectScope, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ResearchSession } from '@/api/researchAgent'
import { useResearchWorkflow } from '../useResearchWorkflow'
const calls = vi.hoisted(() => ({ invoke: vi.fn(), related: vi.fn(), detail: vi.fn(), decide: vi.fn(), analysis: vi.fn(), catalog: vi.fn(), status: vi.fn(), describe: vi.fn() }))
vi.mock('@/api/agentTools', () => ({ agentToolsApi: { capabilities: calls.catalog, invoke: (session: string, capability: string, args: unknown) => capability === 'downloads.describe_capabilities' ? calls.describe() : capability === 'tasks.get_status' ? calls.status(session, capability, args) : calls.invoke(session, capability, args), related: calls.related } }))
vi.mock('@/api/datasets', () => ({ datasetsApi: { detail: calls.detail, decide: calls.decide, decideAnalysis: calls.analysis } }))
let stop: () => void
function mount(project: string | null = 'p1') {
  const scope = effectScope()
  const session = ref<ResearchSession | null>({ session_id: 's1', project_id: project } as ResearchSession)
  const workflow = scope.run(() => useResearchWorkflow(session))!
  stop = () => scope.stop()
  return { ...workflow, session }
}
afterEach(() => stop?.())
beforeEach(() => {
  vi.resetAllMocks()
  calls.catalog.mockResolvedValue({ tools: ['downloads.describe_capabilities', 'dataset.discover', 'dataset.prepare_import', 'dataset.list_project_assets', 'dataset.inspect', 'analysis.list_compatible_workflows', 'analysis.prepare_from_dataset', 'tasks.list_related', 'tasks.get_status', 'research.project_delivery'].map(capability_id => ({ capability_id })) })
  calls.describe.mockResolvedValue({ result: { capabilities: [] } })
  calls.status.mockResolvedValue({ result: { status: 'running' } })
})
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
describe('T11–T14/T24/T25/T35/T41/T42 safe workflow adapter', () => {
  it('does not replay an interrupted prepare and restores only persisted tasks after refresh', async () => {
    calls.invoke.mockRejectedValueOnce(new TypeError('connection interrupted'))
    const w = mount()
    await w.action({ type: 'dataset.prepare_import', discoveryRef: 'GSE1', mode: 'raw', selectedIds: ['SRR1'], maxBytes: 123, requestKey: 'interrupted-key' })
    expect(w.view.proposals).toEqual([])
    expect(w.view.tasks).toEqual([])
    expect(w.view.allowedTools).toEqual([])
    expect(w.view.busy).toBe(false)
    calls.related.mockResolvedValue([{ task: { task_id: 'persisted', status: 'success' } }])
    calls.status.mockResolvedValue({ result: { status: 'running' } })
    await w.action({ type: 'records.refresh' })
    expect(calls.invoke).toHaveBeenCalledTimes(1)
    expect(calls.decide).not.toHaveBeenCalled()
    expect(w.view.tasks).toEqual([{ id: 'persisted', status: 'running' }])
  })
  it('consumes server catalog, exposes blocked reasons and never trusts execution claims', async () => {
    calls.describe.mockResolvedValue({ result: { capabilities: [{ source_type: 'ftp', states: ['CODE_AVAILABLE', 'EXECUTION_BLOCKED'], limitations: ['TRANSPORT_RUNTIME_UNVERIFIED'], execution_allowed: true, binary_path: '/private/tool', token: 'secret' }] } })
    const w = mount()
    await w.action({ type: 'capabilities.refresh' })
    expect(w.view.downloadCapabilities?.[0].executionAllowed).toBe(false)
    expect(w.view.downloadCapabilities?.[0].reasons).toContain('TRANSPORT_RUNTIME_UNVERIFIED')
    expect(JSON.stringify(w.view)).not.toContain('/private')
    expect(JSON.stringify(w.view)).not.toContain('secret')
    expect(calls.invoke).not.toHaveBeenCalled()
  })
  it('drops late permissions and all previous views on a project switch within the same session', async () => {
    const wait = deferred<{ tools: { capability_id: string }[] }>()
    calls.catalog.mockReturnValueOnce(wait.promise)
    const w = mount()
    const pending = w.action({ type: 'dataset.inspect', discoveryRef: 'GSE1' })
    w.session.value = { session_id: 's1', project_id: 'p2' } as ResearchSession
    wait.resolve({ tools: [{ capability_id: 'dataset.discover' }] })
    await pending
    expect(w.view.allowedTools).toEqual([])
    expect(w.view.accession).toBeUndefined()
    expect(calls.invoke).not.toHaveBeenCalled()
  })
  it('rechecks changed permissions before prepare and never posts a forbidden intent', async () => {
    const w = mount()
    await w.action({ type: 'capabilities.refresh' })
    calls.catalog.mockResolvedValue({ tools: [] })
    await w.action({ type: 'dataset.prepare_import', discoveryRef: 'GSE1', mode: 'raw', selectedIds: ['SRR1'], maxBytes: 20, requestKey: 'key' })
    expect(calls.invoke).not.toHaveBeenCalled()
    expect(w.view.allowedTools).toEqual([])
    expect(w.view.error).toBeTruthy()
    expect(calls.decide).not.toHaveBeenCalled()
  })
  it('uses bounded Gateway versions without a second project REST query', async () => {
    calls.invoke.mockResolvedValue({ result: [{ id: 'd', name: 'dataset', versions: [{ version_id: 'v', number: 2, status: 'DRAFT' }], version_query_limit: 200 }] })
    const w = mount()
    await w.action({ type: 'dataset.list' })
    expect(w.view.datasets[0].versions[0].id).toBe('v')
    expect(w.view.gaps).toContain('VERSION_LIST_BOUNDED_NOT_COMPLETE_HISTORY')
    expect(calls.detail).not.toHaveBeenCalled()
  })
  it('restores status from the Task query rather than historical proposal success', async () => {
    calls.related.mockResolvedValue([{ dataset_analysis: { analysis_proposal_id: 'p', task_id: 'task', state: 'succeeded' } }])
    calls.status.mockResolvedValue({ result: { task_id: 'task', status: 'failed' } })
    const w = mount()
    await w.action({ type: 'records.refresh' })
    expect(w.view.tasks).toEqual([{ id: 'task', status: 'failed' }])
    expect(calls.status).toHaveBeenCalledWith('s1', 'tasks.get_status', { task_id: 'task' })
  })
  it('feature disable clears historical permissions and approval information', async () => {
    const w = mount()
    await w.action({ type: 'capabilities.refresh' })
    w.view.proposals = [{ id: 'old', kind: 'import', state: 'APPROVED', hash: '', expires: '', details: [] }]
    calls.catalog.mockRejectedValue({ response: { status: 403 } })
    await w.action({ type: 'records.refresh' })
    expect(w.view.catalogStatus).toBe('UNAVAILABLE')
    expect(w.view.proposals).toEqual([])
    expect(w.view.allowedTools).toEqual([])
  })
  it('inspects public metadata without a project and retains multiple runs, samples and gaps', async () => {
    calls.invoke.mockResolvedValue({ result: { primary_accession: 'GSE1', status: 'RESOLVED', samples: [{ sample_key: 'GSM1', title: ['sample'] }], runs: [{ run_accession: 'SRR1', sample_accession: 'GSM1' }, { run_accession: 'SRR2', sample_accession: 'GSM1' }], files: [], related_accessions: [{ from: 'GSM1', to: 'SRX1', relation: 'sample_relation' }, { from: 'SRX1', to: 'SRR1', relation: 'ena_read_run' }], confidence_flags: ['groups_unknown'], source_evidence: [{ url: 'https://www.ncbi.nlm.nih.gov/geo/', response_sha256: 'abc' }] } })
    const w = mount(null)
    await w.action({ type: 'dataset.inspect', discoveryRef: 'GSE1' })
    expect(w.view.files.map(file => file.id)).toEqual(['SRR1', 'SRR2'])
    expect(w.view.samples[0].id).toBe('GSM1')
    expect(w.view.relations.map(edge => edge.to)).toEqual(['SRX1', 'SRR1'])
    expect(w.view.gaps).toContain('groups_unknown')
    expect(w.view.projectSelected).toBe(false)
    expect(calls.invoke).toHaveBeenCalledWith('s1', 'dataset.discover', { accession: 'GSE1' })
  })
  it('drops late source results after a project/session switch and on close', async () => {
    const wait = deferred<unknown>(); calls.invoke.mockReturnValue(wait.promise)
    const w = mount()
    const pending = w.action({ type: 'dataset.inspect', discoveryRef: 'GSE1' })
    w.session.value = { session_id: 's2', project_id: 'p2' } as ResearchSession
    wait.resolve({ result: { primary_accession: 'GSE1', runs: [] } }); await pending
    expect(w.view.accession).toBeUndefined(); expect(w.view.open).toBe(false)
  })
  it('prevents concurrent prepare and never submits a Task or approval automatically', async () => {
    const wait = deferred<unknown>(); calls.invoke.mockReturnValue(wait.promise)
    const w = mount()
    const intent = { type: 'dataset.prepare_import' as const, discoveryRef: 'GSE1', mode: 'raw' as const, selectedIds: ['SRR1'], maxBytes: 123, requestKey: 'fixed-key' }
    const first = w.action(intent); await w.action(intent); await vi.waitFor(() => expect(calls.invoke).toHaveBeenCalledTimes(1))
    expect(calls.invoke).toHaveBeenCalledTimes(1)
    expect(calls.invoke.mock.calls[0][2].request.request_key).toBe('fixed-key')
    wait.resolve({ result: { ingestion_id: 'i1', parameters_hash: 'hash', state: 'PREPARED', preview: { target_directory: '/private', accession: 'GSE1' } } }); await first
    expect(w.view.proposals[0].state).toBe('PREPARED')
    expect(JSON.stringify(w.view)).not.toContain('/private')
    expect(calls.decide).not.toHaveBeenCalled()
  })
  it('does not prepare imports without an authorized project', async () => {
    const w = mount(null)
    await w.action({ type: 'dataset.prepare_import', discoveryRef: 'GSE1', mode: 'raw', selectedIds: ['SRR1'], maxBytes: 123, requestKey: 'key' })
    expect(calls.invoke).not.toHaveBeenCalled(); expect(w.view.error).toBeTruthy()
  })
  it('keeps unsafe/unknown data incompatible and never invents counts flows', async () => {
    calls.invoke.mockResolvedValueOnce({ result: { manifest_hash: 'frozen', handoff_frozen: false, validation: { worker_paths_verified: false, blocking_reasons: ['UNKNOWN_DATA_TYPE'] }, assets: [] } }).mockResolvedValueOnce({ result: { workflows: [] } })
    const w = mount()
    await w.action({ type: 'dataset.version', datasetId: 'd', versionId: 'v' })
    expect(w.view.workflows).toEqual([]); expect(w.view.gaps).toContain('UNKNOWN_DATA_TYPE')
    expect(w.view.gaps).toContain('WORKER_PATHS_NOT_VERIFIED')
    expect(w.view.manifestHash).toBe('')
    expect(w.view.gaps).toContain('HANDOFF_NOT_FROZEN')
  })
  it('restores only persisted task IDs and proposals and keeps analysis decisions separate', async () => {
    calls.related.mockResolvedValue([{ task: { task_id: 'real-task', status: 'running' }, dataset_analysis: { analysis_proposal_id: 'a1', dataset_id: 'd', dataset_version_id: 'v', state: 'pending', parameters_hash: 'hash' } }])
    calls.analysis.mockResolvedValue({ state: 'REJECTED' })
    const w = mount()
    await w.action({ type: 'records.refresh' })
    expect(w.view.tasks).toEqual([{ id: 'real-task', status: 'running' }])
    await w.action({ type: 'proposal.decide', proposalId: 'a1', kind: 'analysis', approve: false })
    expect(calls.analysis).toHaveBeenCalledWith('p1', 'd', 'v', 'a1', false)
    expect(calls.decide).not.toHaveBeenCalled()
  })
  it('restores import and analysis tasks from their actual persisted nested references', async () => {
    calls.status.mockImplementation((_session, _tool, args) => Promise.resolve({ result: { status: args.task_id === 'download-task' ? 'failed' : 'succeeded' } }))
    calls.related.mockResolvedValue([
      { dataset_import: { ingestion_id: 'i', state: 'PARTIAL', preview: {}, tasks: [{ task_id: 'download-task', status: 'failed' }] } },
      { dataset_analysis: { analysis_proposal_id: 'a', task_id: 'analysis-task', state: 'succeeded' } },
    ])
    const w = mount()
    await w.action({ type: 'records.refresh' })
    expect(w.view.tasks).toEqual([{ id: 'download-task', status: 'failed' }, { id: 'analysis-task', status: 'succeeded' }])
  })
  it('reports missing scientific outputs as NOT_GENERATED and creates no fake links', async () => {
    calls.invoke.mockResolvedValue({ result: { datasets: [{ analyses: [{ task_id: null, gaps: ['TASK_NOT_CREATED'], reports: [] }] }] } })
    const w = mount()
    await w.action({ type: 'delivery.read' })
    expect(w.view.deliveryStatus).toBe('NOT_GENERATED')
    expect(w.view.reports).toEqual([]); expect(w.view.tasks).toEqual([])
  })
})
