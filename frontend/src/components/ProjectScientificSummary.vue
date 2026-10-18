<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NSpace } from 'naive-ui'
import { projectReportApi, type ReportPreparation, type ReportRequest, type ProjectReportJob } from '@/api/projectReport'
import type { ClaimCellQuery } from '@/api/claimProvenance'
import { projectDeliveryApi, type ExportPreview, type ExportJob } from '@/api/projectDelivery'
const props = defineProps<{ projectId: string; manifestId: string; claims: ClaimCellQuery[] }>()
const emit = defineEmits<{ published: [id: string] }>()
const prepared = ref<ReportPreparation | null>(null), job = ref<ProjectReportJob | null>(null)
const html = ref(''), error = ref(''), busy = ref(false)
const m1 = ref<ExportPreview | null>(null), m1Job = ref<ExportJob | null>(null)
let generation = 0, abort = new AbortController(), timer: ReturnType<typeof setTimeout> | undefined
let request: ReportRequest | null = null, key = ''
function reset() { generation++; abort.abort(); abort = new AbortController(); clearTimeout(timer); prepared.value = null; m1.value = null; m1Job.value = null; job.value = null; html.value = ''; error.value = ''; busy.value = false; request = null; key = '' }
function failure(exc: unknown) {
  const status = (exc as { response?: { status?: number } }).response?.status
  error.value = status === 409 ? '来源已变化，请重新预览并确认。' : status === 503 ? '正式报告生成门禁尚未开放。' : status === 403 || status === 404 ? '当前无权访问或报告不可用。' : '报告请求失败，请重新核对状态。'
}
async function prepare() {
  const current = generation; busy.value = true; error.value = ''; prepared.value = null
  const selected: ReportRequest = { source_manifest_job_id: props.manifestId, claims: structuredClone(props.claims.map(c => ({ ...c }))), format: 'html' }
  try { const value = await projectReportApi.prepare(props.projectId, selected, abort.signal); if (current === generation) { prepared.value = value; request = selected; key = crypto.randomUUID() } }
  catch (exc) { if (current === generation) failure(exc) } finally { if (current === generation) busy.value = false }
}
async function poll(current: number, project: string, id: string) {
  try {
    const value = await projectReportApi.status(project, id, abort.signal)
    if (current !== generation || value.project_id !== props.projectId) return
    job.value = value
    if (value.status === 'ready') emit('published', id)
    else if (value.status !== 'failed') timer = setTimeout(() => poll(current, project, id), 2000)
  } catch (exc) { if (current === generation) failure(exc) }
}
async function create() {
  if (!prepared.value || !request) return
  const current = generation, project = props.projectId; busy.value = true; error.value = ''
  try { const value = await projectReportApi.create(project, request, prepared.value.prepare_digest, key, abort.signal); if (current === generation) { sessionStorage.setItem(`project-report:${project}:${props.manifestId}`, value.id); void poll(current, project, value.id) } }
  catch (exc) { if (current === generation) failure(exc) } finally { if (current === generation) busy.value = false }
}
async function prepareM1() {
  const selection = job.value?.source_selection ?? prepared.value?.source.manifest.selection
  if (!job.value || !selection) { error.value = '请先重新核验 M0 范围。'; return }
  const current = generation; busy.value = true
  try {
    const value = await projectDeliveryApi.prepare(props.projectId, { ...selection, source_manifest_job_id: props.manifestId, project_report_job_ids: [job.value.id] }, abort.signal)
    if (current === generation) { m1.value = value; key = crypto.randomUUID() }
  } catch (exc) { if (current === generation) failure(exc) } finally { if (current === generation) busy.value = false }
}
async function createM1() {
  if (!m1.value) return
  const current = generation; busy.value = true
  try {
    const value = await projectDeliveryApi.create(props.projectId, m1.value, key, abort.signal)
    if (current === generation) void pollM1(current, props.projectId, value.id)
  } catch (exc) { if (current === generation) failure(exc) } finally { if (current === generation) busy.value = false }
}
async function pollM1(current: number, project: string, id: string) {
  try {
    const value = await projectDeliveryApi.status(project, id, abort.signal)
    if (current !== generation || value.project_id !== props.projectId) return
    m1Job.value = value
    if (!['ready', 'failed'].includes(value.status)) timer = setTimeout(() => pollM1(current, project, id), 2000)
  } catch (exc) { if (current === generation) failure(exc) }
}
async function preview() {
  if (!job.value) return
  const current = generation
  try { const value = await projectReportApi.preview(props.projectId, job.value.id, abort.signal); if (current === generation) html.value = value } catch (exc) { if (current === generation) failure(exc) }
}
async function downloadM1() {
  if (!m1Job.value) return
  const current = generation, selected = m1Job.value
  try {
    const blob = await projectDeliveryApi.download(props.projectId, selected.id)
    const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(x => x.toString(16).padStart(2, '0')).join('')
    if (current !== generation) return
    if (sha !== selected.archive_sha256 || blob.size !== selected.archive_size) throw new Error('ZIP drifted')
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'project-delivery-m1.zip'; link.click(); URL.revokeObjectURL(url)
  } catch (exc) { if (current === generation) failure(exc) }
}
async function download(format: 'html' | 'pdf') {
  if (!job.value) return
  const current = generation, selected = job.value
  try {
    const blob = await projectReportApi.download(props.projectId, selected.id, format, abort.signal)
    const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(x => x.toString(16).padStart(2, '0')).join('')
    if (current !== generation) return
    if (sha !== selected[`${format}_sha256`] || blob.size !== selected[`${format}_size`]) throw new Error('Report bytes changed')
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = `project-report.${format}`; link.click(); URL.revokeObjectURL(url)
  } catch (exc) { if (current === generation) failure(exc) }
}
watch(() => [props.projectId, props.manifestId], () => { reset(); const saved = sessionStorage.getItem(`project-report:${props.projectId}:${props.manifestId}`); if (saved) void poll(generation, props.projectId, saved) }, { immediate: true })
watch(() => props.claims, reset, { deep: true })
onBeforeUnmount(reset)
</script>
<template>
  <NCard title="生成项目综合报告" size="small">
    <NSpace vertical>
      <p>已显式选择 {{ claims.length }} 个结果单元格。空选择将显示“无已验证结论”。不会启动分析或重新下载数据。</p>
      <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
      <NButton :disabled="busy" @click="prepare">核验来源并预览报告范围</NButton>
      <template v-if="prepared">
        <p>M0 {{ prepared.source.source_manifest_digest }} · Claim 选择 {{ prepared.source.selection_digest }}</p>
        <p v-for="c in prepared.source.selection.claims" :key="c.claim_id">{{ c.verification_status }} · {{ c.value ?? 'NA' }} · {{ c.supported_statement }}</p>
        <NButton :disabled="busy" @click="create">确认冻结范围并生成正式报告</NButton>
      </template>
      <template v-if="job">
        <p role="status">报告 v{{ job.version }} · {{ job.status }} · {{ job.pdf_status }}</p>
        <NAlert v-if="job.status === 'failed'" type="error">{{ job.error_code }}</NAlert>
        <template v-if="job.status === 'ready'">
          <NButton @click="preview">预览已发布 HTML</NButton><NButton @click="download('html')">核验并下载 HTML</NButton>
          <NButton v-if="job.pdf_sha256" @click="download('pdf')">核验并下载 PDF</NButton>
          <p v-else>PDF 未生成；HTML 可独立交付。</p>
          <NButton :disabled="busy" @click="prepareM1">预览含此报告的新 M1 交付范围</NButton>
        </template>
      </template>
      <template v-if="m1">
        <p>M1 包含 {{ m1.manifest.files.length }} 个文件 · {{ m1.manifest.evidence_status }} · {{ m1.manifest_digest }}</p>
        <p v-for="gap in m1.manifest.gaps" :key="gap">{{ gap }}</p>
        <NButton :disabled="busy" @click="createM1">确认新范围并创建 M1</NButton>
      </template>
      <p v-if="m1Job" role="status">M1 {{ m1Job.status }} · {{ m1Job.error_code }} · {{ m1Job.id }}</p>
      <NButton v-if="m1Job?.status === 'ready'" @click="downloadM1">核验并下载 M1 ZIP</NButton>
      <iframe v-if="html" :srcdoc="html" sandbox="" title="已发布项目综合报告" style="width:100%;height:70vh;border:0" />
    </NSpace>
  </NCard>
</template>
