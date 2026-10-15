<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'
import { projectsApi, type ProjectItem } from '@/api/projects'
import { asImportProposal, datasetsApi, type DataHandoff, type DatasetItem, type GeoCandidate, type ImportProposal } from '@/api/datasets'
import DatasetImportCard from './DatasetImportCard.vue'
const props = defineProps<{ projectId?: string | null; datasetId?: string; versionId?: string; analysisMode?: boolean }>()
const projects = ref<ProjectItem[]>([])
const localProject = ref<string | null>(props.projectId || null)
const project = computed(() => props.projectId === undefined ? localProject.value : props.projectId)
const items = ref<DatasetItem[]>([])
const selected = ref('')
const handoff = ref<DataHandoff | null>(null)
const candidate = ref<GeoCandidate | null>(null)
const proposal = ref<ImportProposal | null>(null)
const restoredImports = ref<ImportProposal[]>([])
const accession = ref('')
const mode = ref<'raw' | 'processed'>('raw')
const importTarget = ref<string | null>(null)
const selectedIds = ref<string[]>([])
const budget = ref('67108864')
const error = ref('')
const busy = ref(false)
const flow = ref('rna_seq')
const sampleGroups = ref<Record<string, string>>({})
const assetRoles = ref<Record<string, string>>({})
const assay = ref('unknown')
const reviewReason = ref('')
let discoveryRequest = 0
const optionsJson = ref('{"parameters":{}}')
const analysisPreview = ref<Record<string, unknown> | null>(null)
let generation = 0
const candidates = computed(() => mode.value === 'raw' ? candidate.value?.runs.map(run => ({ label: `${run.run_accession} · ${run.library_layout}`, value: run.run_accession })) || [] : candidate.value?.files.map(file => ({ label: `${file.original_name} · 类型待校验 · ${file.size === null ? '大小未知' : file.size}`, value: file.url })) || [])
async function run(action: (snapshot: number) => Promise<void>) {
  const snapshot = generation
  error.value = ''; busy.value = true
  try { await action(snapshot) } catch { if (snapshot === generation) error.value = '数据资产入口尚未开放、无权限或服务不可用。未创建下载或分析任务。' }
  finally { if (snapshot === generation) busy.value = false }
}
async function load() {
  ++generation; importTarget.value = null; restoredImports.value = []; items.value = []; handoff.value = null; proposal.value = null; candidate.value = null; analysisPreview.value = null; selectedIds.value = []; selected.value = ''; error.value = ''
  const pid = project.value
  if (!pid) return
  await run(async snapshot => { const [result, imports] = await Promise.all([datasetsApi.list(pid), datasetsApi.imports(pid)]); if (snapshot === generation) { items.value = result; restoredImports.value = imports } })
  if (props.datasetId) await chooseDataset(props.datasetId)
}
async function chooseDataset(id: string) {
  const pid = project.value
  if (!pid) return
  selected.value = id; handoff.value = null; analysisPreview.value = null
  await run(async snapshot => {
    const detail = await datasetsApi.detail(pid, id)
    const version = props.versionId || detail.versions[0]?.id
    if (!version) return
    const result = await datasetsApi.handoff(pid, id, version)
    if (snapshot === generation && selected.value === id) handoff.value = result
  })
}
async function discover(value = accession.value) {
  const pid = project.value
  if (!pid) { error.value = '先选择获授权项目。'; return }
  const request = ++discoveryRequest
  accession.value = value; selectedIds.value = []; proposal.value = null; candidate.value = null
  await run(async snapshot => { const result = await datasetsApi.discover(pid, value); if (snapshot === generation && request === discoveryRequest) candidate.value = result })
}
async function prepare() {
  const pid = project.value
  if (!pid || !candidate.value || !selectedIds.value.length) return
  const args = { dataset_id: importTarget.value, accession: candidate.value.primary_accession, mode: mode.value, selected_ids: [...selectedIds.value], name: candidate.value.primary_accession, request_key: crypto.randomUUID(), max_bytes: Number(budget.value) }
  await run(async snapshot => {
    const result = await datasetsApi.prepare(pid, args)
    if (snapshot === generation) { proposal.value = asImportProposal(result); if (!proposal.value) error.value = '来源暂不可用，没有导入预案。' }
  })
}
async function inspectHandoff(action: 'verify' | 'freeze') {
  const current = handoff.value
  if (!current) return
  await run(async snapshot => { const result = await datasetsApi[action](current.project_id, current.dataset_id, current.dataset_version_id); if (snapshot === generation && selected.value === current.dataset_id) handoff.value = result })
}
async function reviewSample(sample: string) {
  const current = handoff.value
  const group = sampleGroups.value[sample]?.trim()
  if (!current || !group) return
  await run(async snapshot => {
    await datasetsApi.reviewSample(current.project_id, current.dataset_id, current.dataset_version_id, sample, group)
    const result = await datasetsApi.handoff(current.project_id, current.dataset_id, current.dataset_version_id)
    if (snapshot === generation && selected.value === current.dataset_id) handoff.value = result
  })
}
async function reviseVersion() {
  const current = handoff.value
  if (!current || !reviewReason.value.trim()) return
  await run(async snapshot => {
    const created = await datasetsApi.newVersion(current.project_id, current.dataset_id, reviewReason.value)
    const result = await datasetsApi.handoff(current.project_id, current.dataset_id, created.version_id)
    if (snapshot === generation && selected.value === current.dataset_id) handoff.value = result
  })
}
async function reviewRole(asset: string) {
  const current = handoff.value
  const role = assetRoles.value[asset]
  if (!current || !role || !reviewReason.value.trim()) return
  await run(async snapshot => {
    await datasetsApi.reviewRole(current.project_id, current.dataset_id, current.dataset_version_id, asset, role, reviewReason.value)
    const result = await datasetsApi.handoff(current.project_id, current.dataset_id, current.dataset_version_id)
    if (snapshot === generation && selected.value === current.dataset_id) handoff.value = result
  })
}
async function reviewVersion() {
  const current = handoff.value
  if (!current || !reviewReason.value.trim()) return
  await run(async () => { await datasetsApi.reviewVersion(current.project_id, current.dataset_id, current.dataset_version_id, assay.value, reviewReason.value) })
}
async function prepareAnalysis() {
  const current = handoff.value
  if (!current) return
  await run(async snapshot => {
    const options = JSON.parse(optionsJson.value) as Record<string, unknown>
    const result = await datasetsApi.prepareAnalysis(current.project_id, current.dataset_id, current.dataset_version_id, flow.value, options)
    if (snapshot === generation) analysisPreview.value = result
  })
}
function show(value: unknown) {
  const envelope = value as { result?: unknown } | null
  const result = asImportProposal(envelope?.result)
  if (result?.project_id === project.value) proposal.value = result
}
watch(() => project.value, load, { immediate: true })
watch(mode, () => { selectedIds.value = [] })
onMounted(async () => { if (props.projectId === undefined) { try { projects.value = await projectsApi.listProjects() } catch { error.value = '项目列表不可用。' } } })
defineExpose({ discover, show })
</script>
<template>
  <details class="dataset-workspace" :open="analysisMode || !!projectId" aria-label="项目科研数据资产">
    <summary>Dataset · 来源、文件校验与分析交接</summary>
    <NSelect v-if="projectId === undefined" v-model:value="localProject" placeholder="选择项目" :options="projects.map(p => ({ label: p.name, value: p.id }))" />
    <p v-if="!project">请选择项目。现有文件不会自动推断为 Dataset。</p>
    <div v-else>
      <p v-if="error" role="status">{{ error }}</p>
      <div class="actions"><NInput v-model:value="accession" aria-label="GEO 或 SRA 编号" placeholder="GSE / GSM / SRX / SRR" /><NButton :loading="busy" @click="discover()">查看来源与样本</NButton><NButton :disabled="busy" @click="load">刷新资产</NButton></div>
      <section v-if="candidate"><h4>{{ candidate.primary_accession }} · {{ candidate.status }}</h4><p>外部文本为来源证据，不作为分组结论。{{ candidate.confidence_flags.join('；') }}</p><details><summary>样本原始信息与来源</summary><pre>{{ JSON.stringify({ samples: candidate.samples, evidence: candidate.source_evidence }, null, 2) }}</pre></details><NSelect v-model:value="mode" :options="[{label:'原始 FASTQ 候选',value:'raw'},{label:'处理后附件候选',value:'processed'}]" /><NSelect v-model:value="selectedIds" multiple :options="candidates" placeholder="选择有来源证据的 Run 或附件" /><NSelect v-model:value="importTarget" clearable :options="items.map(item => ({label:item.name,value:item.id}))" placeholder="导入为已有 Dataset 的新版本（留空创建新 Dataset）" /><label>最大字节预算（未知大小也受此边界限制）<NInput v-model:value="budget" /></label><NButton :disabled="busy || !selectedIds.length" @click="prepare">生成导入预案</NButton></section>
      <DatasetImportCard v-if="proposal" :proposal="proposal" />
      <DatasetImportCard v-for="item in restoredImports.filter(p => p.proposal_id !== proposal?.proposal_id)" :key="item.proposal_id" :proposal="item" />
      <NSelect :value="selected || null" :options="items.map(d => ({ label: `${d.name} · ${d.status}`, value: d.id }))" placeholder="已有项目 Dataset" @update:value="chooseDataset" />
      <section v-if="handoff"><h4>数据版本 {{ handoff.dataset_version_id }}</h4><p>数据校验：{{ handoff.validation.dataset_ready ? '通过' : '需审查' }}；Worker 路径运行验收：{{ handoff.validation.worker_paths_verified ? '通过' : '未通过' }}</p><ul><li v-for="reason in handoff.validation.blocking_reasons" :key="reason">{{ reason }}</li></ul><div class="table-scroll"><table><thead><tr><th>资产 ID</th><th>类型</th><th>校验</th><th>SHA-256</th></tr></thead><tbody><tr v-for="asset in handoff.assets" :key="asset.file_record_id"><td>{{ asset.file_record_id }}</td><td>{{ asset.data_type }}</td><td>{{ asset.checksum_status }}</td><td>{{ asset.sha256 || '未计算' }}</td></tr></tbody></table></div><details><summary>样本、来源与人工审查</summary><pre>{{ JSON.stringify({ samples: handoff.samples, source: handoff.source }, null, 2) }}</pre></details><section aria-label="人工审阅"><p>审阅保留来源原文；冻结后修订需新建版本。</p><NSelect v-model:value="assay" :options="[{label:'未知',value:'unknown'},{label:'Bulk RNA-seq',value:'bulk_rnaseq'},{label:'芯片',value:'microarray'},{label:'单细胞',value:'scrna'}]" /><NInput v-model:value="reviewReason" placeholder="填写判断依据" /><NButton :disabled="busy || !reviewReason.trim()" @click="reviewVersion">记录实验类型审阅</NButton><NButton :disabled="busy || !reviewReason.trim()" @click="reviseVersion">创建修订版本</NButton><div v-for="asset in handoff.assets" :key="asset.asset_id"><label>{{ asset.file_record_id }} · {{ asset.asset_role }}<NSelect v-model:value="assetRoles[asset.asset_id]" :options="['raw_reads','raw_counts','metadata','annotation','normalized_expression','archive','other'].map(value => ({label:value,value}))" placeholder="指定文件用途" /></label><NButton :disabled="busy || !reviewReason.trim() || !assetRoles[asset.asset_id]" @click="reviewRole(asset.asset_id)">审阅用途并重新校验</NButton></div><div v-for="sample in handoff.samples" :key="sample.sample_key"><label>{{ sample.sample_key }} · {{ sample.mapping_status }}<NInput v-model:value="sampleGroups[sample.sample_key]" placeholder="人工确认分组" /></label><NButton :disabled="busy || !sampleGroups[sample.sample_key]?.trim()" @click="reviewSample(sample.sample_key)">确认样本分组</NButton></div></section><NButton :disabled="busy" @click="inspectHandoff('verify')">校验本地受管文件</NButton><NButton :disabled="busy" @click="inspectHandoff('freeze')">冻结交接版本</NButton><RouterLink v-if="!analysisMode" :to="{path:'/flows',query:{project:handoff.project_id,dataset:handoff.dataset_id,version:handoff.dataset_version_id}}">在分析中心准备任务</RouterLink><section v-if="analysisMode"><NSelect v-model:value="flow" :options="[{label:'FASTQ RNAFlow',value:'rna_seq'},{label:'原始 counts DEG（隔离验收中）',value:'counts_deg'}]" /><label>人工选择参考、链特异性与比较组；counts 需明确 design/reference/treatment<NInput v-model:value="optionsJson" type="textarea" /></label><NButton :disabled="busy" @click="prepareAnalysis">生成分析参数预案</NButton><pre v-if="analysisPreview">{{ JSON.stringify(analysisPreview, null, 2) }}</pre><NButton v-if="analysisPreview" disabled>分析执行尚未开放</NButton></section></section>
    </div>
  </details>
</template>
<style scoped>
.dataset-workspace { margin: 12px 0; padding: 12px; border: 1px solid var(--neutral-border); border-radius: 8px; } summary { cursor: pointer; font-weight: 600; } section { margin-top: 12px; } .actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; } .actions :deep(.n-input) { flex: 1; min-width: 140px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 280px; overflow: auto; font-size: 12px; } .table-scroll { overflow: auto; } table { width: 100%; font-size: 12px; border-collapse: collapse; } td, th { padding: 6px; text-align: left; border-bottom: 1px solid var(--neutral-border); max-width: 220px; overflow-wrap: anywhere; } button { margin: 4px; }
</style>
