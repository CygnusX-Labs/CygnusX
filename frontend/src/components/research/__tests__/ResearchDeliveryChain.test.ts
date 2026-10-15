// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { expect, it, vi } from 'vitest'
import ResearchDeliveryChain from '@/components/ResearchDeliveryChain.vue'
import { researchDeliveryApi, type ResearchProvenance, type ProjectDelivery } from '@/api/researchDelivery'
vi.mock('@/api/researchDelivery', () => ({ researchDeliveryApi: { project: vi.fn() } }))
const response = (id: string): ProjectDelivery => ({ project_id: id, datasets: [], runtime_admission: 'BLOCKED', truncated: false })
async function settle() { for (let i=0;i<8;i++) { await Promise.resolve(); await nextTick() } }
function mount() {
  const project=ref('first'), host=document.createElement('div')
  const app=createApp({render:()=>h(ResearchDeliveryChain,{projectId:project.value})})
  app.component('RouterLink', defineComponent({props:['to'], setup(props,{slots}) {return ()=>h('a',{'data-target':JSON.stringify(props.to)},slots.default?.())}}))
  app.mount(host)
  return {project,host,close:()=>app.unmount()}
}
it('discards late responses after project switch', async () => {
  let finish!: (v: ProjectDelivery) => void
  vi.mocked(researchDeliveryApi.project).mockImplementationOnce(() => new Promise(resolve => { finish=resolve })).mockResolvedValueOnce(response('second'))
  const card=mount()
  try {
    card.project.value='second'; await settle()
    finish({...response('first'), truncated:true}); await settle()
    expect(card.host.textContent).toContain('BLOCKED')
    expect(card.host.textContent).not.toContain('当前仅展示部分记录')
  } finally {card.close()}
})
it('clears old project data and hides internal error text', async () => {
  vi.mocked(researchDeliveryApi.project).mockResolvedValueOnce(response('first')).mockRejectedValueOnce(new Error('secret token'))
  const card=mount()
  try {
    await settle(); expect(card.host.textContent).toContain('BLOCKED')
    card.project.value='second'; await settle()
    expect(card.host.textContent).toContain('科研交付记录暂不可用')
    expect(card.host.textContent).not.toContain('secret token')
    expect(card.host.textContent).not.toContain('BLOCKED')
  } finally {card.close()}
})

it('shows independent states and actual task/report links', async () => {
  const graph: ResearchProvenance = {
    schema_version:'cygnusx.research_provenance.v1', task_id:'task', owner_id:'owner', project_id:'first',
    dataset_id:'dataset',dataset_version_id:'version',analysis_link_id:'link',handoff_hash:'a'.repeat(64),run_id:null,
    parameters_sha256:'b'.repeat(64),result_observation_id:null,manifest_sha256:null,analysis_parameters:{design:'~ group'},
    flow:{id:'counts_deg',version:'0.1.0'},source:[{repository:'GEO',accession:'GSE1'}],samples:[],inputs:[],
    compute_state:'success',input_integrity:'VERIFIED',result_integrity:'MISSING',evidence_state:'PARTIAL',delivery_state:'PARTIAL',
    artifacts:[],reports:[{report_id:'report',kind:'scientific',state:'completed',integrity:'VERIFIED',result_observation_id:null,report_url:'/reports?reportId=report'}],
    report_jobs:[],gaps:['RESULT_MANIFEST_MISSING'],runtime:{},started_at:null,finished_at:null,observation_scope:'capture_time_bytes_not_execution_attestation',
  }
  vi.mocked(researchDeliveryApi.project).mockResolvedValueOnce({...response('first'),datasets:[{dataset_id:'dataset',dataset_version_id:'version',handoff_hash:graph.handoff_hash,gaps:[],analyses:[graph]}]})
  const card=mount()
  try {
    await settle()
    for (const state of ['分析 success','产物 MISSING','证据 PARTIAL','交付 PARTIAL','GEO GSE1']) expect(card.host.textContent).toContain(state)
    const targets=Array.from(card.host.querySelectorAll('a')).map(a=>a.getAttribute('data-target')).join(' ')
    expect(targets).toContain('/tasks/task'); expect(targets).toContain('reportId')
  } finally {card.close()}
})
