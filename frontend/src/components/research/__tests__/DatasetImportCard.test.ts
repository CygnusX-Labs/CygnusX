// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import DatasetImportCard from '../DatasetImportCard.vue'
import { datasetsApi, type ImportProposal } from '@/api/datasets'
vi.mock('@/api/datasets', () => ({ datasetsApi: { decide: vi.fn() } }))
const proposal: ImportProposal = { proposal_id:'a', ingestion_id:'a', project_id:'project-a', dataset_version_id:null, state:'PREPARED', preview:{ source:'GSE123' }, normalized_parameters:{mode:'raw'}, parameters_hash:'sha256-evidence', expires_at:'2099-01-01T00:00:00Z', write_enabled:false, gate:'BLOCKED', tasks:[], errors:[] }
async function settle() { for (let n=0;n<6;n++) { await Promise.resolve(); await nextTick() } }
function mount(value: ImportProposal) {
  const current = ref(value), host = document.createElement('div')
  const app = createApp({ render: () => h(DatasetImportCard,{proposal:current.value}) })
  app.mount(host)
  return {current, host, close: () => app.unmount()}
}
describe('Dataset import approval', () => {
  it('shows bound evidence and approves without any execution request',async()=>{
    vi.mocked(datasetsApi.decide).mockResolvedValue({...proposal,state:'APPROVED'})
    const card=mount(proposal)
    try {
      expect(card.host.textContent).toContain('GSE123')
      expect(card.host.textContent).toContain('sha256-evidence')
      expect(card.host.querySelectorAll('button')[2].disabled).toBe(true)
      card.host.querySelector('button')!.click(); await settle()
      expect(datasetsApi.decide).toHaveBeenLastCalledWith('project-a','a',true)
      expect(card.host.textContent).toContain('APPROVED')
    } finally {card.close()}
  })
  it('expired approvals and errors never auto-retry',async()=>{
    const expired=mount({...proposal,expires_at:'2000-01-01T00:00:00Z'})
    expect(expired.host.querySelector('button')!.disabled).toBe(true); expired.close()
    vi.mocked(datasetsApi.decide).mockRejectedValue(new Error('offline'))
    const card=mount(proposal)
    try { card.host.querySelector('button')!.click(); await settle(); expect(card.host.querySelector('[role=alert]')?.textContent).toContain('未提交下载') } finally {card.close()}
  })
  it('late old-project approval cannot replace restored proposal',async()=>{
    let resolve!: (value: ImportProposal)=>void
    vi.mocked(datasetsApi.decide).mockImplementation(()=>new Promise(done=>{resolve=done}))
    const card=mount(proposal)
    try {
      card.host.querySelector('button')!.click()
      card.current.value={...proposal,project_id:'project-b',proposal_id:'b',preview:{source:'GSE456'}}
      await settle(); resolve({...proposal,state:'APPROVED'}); await settle()
      expect(card.host.textContent).toContain('GSE456'); expect(card.host.textContent).not.toContain('GSE123')
    } finally {card.close()}
  })
})
