<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NCheckbox, NEmpty, NSelect, NSpace, NTag } from 'naive-ui'
import { projectDeliveryApi, type DeliveryInventory, type ExportJob, type ExportPreview, type PackageKind } from '@/api/projectDelivery'
import ClaimEvidencePanel from '@/components/ClaimEvidencePanel.vue'
import ProjectScientificSummary from '@/components/ProjectScientificSummary.vue'
import type { ClaimCellQuery } from '@/api/claimProvenance'

const props = defineProps<{ projectId: string }>()
const inventory = ref<DeliveryInventory | null>(null)
const preview = ref<ExportPreview | null>(null)
const job = ref<ExportJob | null>(null)
const kind = ref<PackageKind>('evidence')
const tasks = ref<string[]>([])
const reports = ref<string[]>([])
const busy = ref(false)
const error = ref('')
const summary = ref<string | null>(null)
const claims = ref<ClaimCellQuery[]>([])
function selectClaim(query: ClaimCellQuery) {
  if (!claims.value.some(c => JSON.stringify(c) === JSON.stringify(query))) claims.value = [...claims.value, query]
}
let generation = 0
let abort = new AbortController()
let timer: ReturnType<typeof setTimeout> | undefined
let requestKey = ''
let selectionGeneration = 0
const options = [
  { label: '证据包（默认）', value: 'evidence' },
  { label: '结果包（含已登记的小型结果）', value: 'results' },
  { label: '复现材料包（原始输入仅保存引用）', value: 'reproduction_materials' },
]
const analyses = computed(() => {
  const rows = new Map<string, NonNullable<DeliveryInventory>['datasets'][number]['analyses'][number]>()
  for (const dataset of inventory.value?.datasets ?? []) for (const a of dataset.analyses) if (a.task_id) rows.set(a.task_id, a)
  return [...rows.values()].filter(a => a.task_id !== null)
})
function failure(exc: unknown) {
  const response = (exc as { response?: { status?: number; data?: { code?: string; error?: { code?: string } } } })?.response
  const code = response?.data?.code ?? response?.data?.error?.code
  if (code === 'FEATURE_DISABLED') return '项目科研交付功能尚未启用。'
  if (response?.status === 403) return '没有权限访问项目科研成果。'
  if (response?.status === 404) return '项目或导出记录不可用，请核对当前权限。'
  if (response?.status === 409) return '导出内容已变化，请重新预览并确认范围。'
  return '请求失败，请重试；已有任务不会因此重新分析或下载。'
}
function remember() {
  if (job.value) sessionStorage.setItem(`project-export:${props.projectId}`, job.value.id)
}
async function poll(current: number, project: string, id: string) {
  try {
    const value = await projectDeliveryApi.status(project, id, abort.signal)
    if (current !== generation || project !== props.projectId) return
    if (value.project_id !== project) throw new Error('Project mismatch')
    job.value = value
    if (!['ready', 'failed'].includes(value.status)) timer = setTimeout(() => poll(current, project, id), 2000)
  } catch (exc) { if (current === generation) error.value = failure(exc) }
}
async function load() {
  const current = ++generation, project = props.projectId
  abort.abort(); abort = new AbortController(); clearTimeout(timer)
  inventory.value = null; preview.value = null; job.value = null; summary.value = null
  tasks.value = []; reports.value = []; claims.value = []; error.value = ''; busy.value = true; requestKey = ''
  try {
    const result = await projectDeliveryApi.inventory(project, abort.signal)
    if (current !== generation || result.project_id !== props.projectId) return
    inventory.value = result
    const saved = sessionStorage.getItem(`project-export:${project}`)
    if (saved) void poll(current, project, saved)
  } catch (exc) { if (current === generation) error.value = failure(exc) }
  finally { if (current === generation) busy.value = false }
}
function invalidate() { selectionGeneration++; preview.value = null; requestKey = '' }
function selectTask(id: string, checked: boolean) {
  tasks.value = checked ? [...tasks.value, id] : tasks.value.filter(t => t !== id)
  reports.value = []; invalidate()
}
function selectReport(id: string, checked: boolean) {
  reports.value = checked ? [...reports.value, id] : reports.value.filter(r => r !== id)
  invalidate()
}
async function prepare() {
  const current = generation, project = props.projectId, selectionVersion = selectionGeneration
  busy.value = true; error.value = ''; preview.value = null
  try {
    const value = await projectDeliveryApi.prepare(project, { kind: kind.value, task_ids: tasks.value, report_ids: reports.value }, abort.signal)
    if (current === generation && selectionVersion === selectionGeneration && value.manifest.project_id === project) {
      preview.value = value; requestKey = crypto.randomUUID()
    }
  } catch (exc) { if (current === generation) error.value = failure(exc) }
  finally { if (current === generation) busy.value = false }
}
async function create() {
  if (!preview.value || !inventory.value?.export_enabled) return
  const current = generation, project = props.projectId
  busy.value = true; error.value = ''
  try {
    // request_key 是导出幂等键；预览确认后必须非空，兜底生成避免空 UUID 422。
    if (!requestKey) requestKey = crypto.randomUUID()
    const value = await projectDeliveryApi.create(project, preview.value, requestKey, abort.signal)
    if (current !== generation || value.project_id !== project) return
    job.value = value; remember(); clearTimeout(timer); void poll(current, project, value.id)
  } catch (exc) { if (current === generation) error.value = failure(exc) }
  finally { if (current === generation) busy.value = false }
}
async function retry() {
  if (!job.value) return
  const current = generation, project = props.projectId
  busy.value = true
  try {
    const value = await projectDeliveryApi.retry(project, job.value.id)
    if (current !== generation || value.project_id !== project) return
    job.value = value; clearTimeout(timer); void poll(current, project, value.id)
  } catch (exc) { if (current === generation) error.value = failure(exc) }
  finally { if (current === generation) busy.value = false }
}
async function download() {
  if (!job.value) return
  const current = generation, project = props.projectId, selectedJob = job.value
  busy.value = true; error.value = ''
  try {
    const blob = await projectDeliveryApi.download(project, selectedJob.id)
    if (current !== generation) return
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(x => x.toString(16).padStart(2, '0')).join('')
    if (current !== generation) return
    if (digest !== selectedJob.archive_sha256 || blob.size !== selectedJob.archive_size) throw new Error('Archive mismatch')
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    link.href = url; link.download = 'project-delivery.zip'; link.click(); URL.revokeObjectURL(url)
  } catch (exc) { if (current === generation) error.value = `下载或 SHA-256 核验失败。${failure(exc)}` }
  finally { if (current === generation) busy.value = false }
}
async function previewSummary() {
  if (!job.value) return
  const current = generation, project = props.projectId
  busy.value = true; summary.value = null; error.value = ''
  try {
    const html = await projectDeliveryApi.summaryPreview(project, job.value.id, abort.signal)
    if (current === generation) summary.value = html
  } catch (exc) { if (current === generation) error.value = failure(exc) }
  finally { if (current === generation) busy.value = false }
}
watch(() => props.projectId, load, { immediate: true })
watch(kind, invalidate)
onBeforeUnmount(() => { generation++; abort.abort(); clearTimeout(timer) })
</script>

<template>
  <NCard title="项目科研成果与可追溯导出" size="small" class="project-delivery">
    <NSpace vertical>
      <NButton size="small" :loading="busy" @click="load">刷新科研成果</NButton>
      <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
      <template v-if="inventory">
        <NAlert v-if="!inventory.export_enabled" type="info">项目导出功能尚未启用；可查看已有关联与证据。</NAlert>
        <NAlert type="info">仅按可信 Dataset 关联展示任务。历史无项目关联的 Task：未记录，不自动补录。不默认复制 FASTQ/BAM；文件完整性不表示科学复现成功。</NAlert>
        <p>项目数据资产：{{ inventory.datasets.length }} 个数据版本 · 分析任务：{{ analyses.length }} 个</p>
        <NEmpty v-if="!analyses.length" description="没有可信关联的分析任务；仍可预览空范围及缺口" />
        <div v-for="a in analyses" :key="a.task_id!" class="task-entry">
          <NCheckbox :disabled="busy" :checked="tasks.includes(a.task_id!)" @update:checked="value => selectTask(a.task_id!, value)">选择任务 {{ a.task_id }}</NCheckbox>
          <RouterLink :to="`/tasks/${a.task_id}`">查看分析任务</RouterLink>
          <ClaimEvidencePanel :project-id="projectId" :task-id="a.task_id!" :artifacts="a.artifacts" :reports="a.reports" @select="selectClaim" />
          <p v-for="r in a.reports" :key="r.report_id">
            <NCheckbox :disabled="busy || (tasks.length > 0 && !tasks.includes(a.task_id!))" :checked="reports.includes(r.report_id)" @update:checked="value => selectReport(r.report_id, value)">
              {{ r.kind === 'scientific' ? '科学报告' : r.kind === 'reproducibility' ? '执行证据' : '单任务交付包' }} · 版本 {{ r.version ?? '未记录' }} · {{ r.state }} · {{ r.integrity }}
            </NCheckbox>
            <RouterLink :to="{ path: '/reports', query: { reportId: r.report_id } }">查看已有报告</RouterLink>
          </p>
        </div>
        <p>未勾选任务或报告时，包含当前容量范围内所有可信关联任务或报告版本。</p>
        <NSelect v-model:value="kind" :options="options" aria-label="导出包类型" :disabled="busy" />
        <NButton :disabled="busy || inventory.truncated" @click="prepare">导出科研成果：预览范围</NButton>
        <NAlert v-if="inventory.truncated" type="warning">项目记录超过首版容量，不能将截断列表作为完整导出。</NAlert>
        <template v-if="preview">
          <NTag>{{ preview.manifest.evidence_status === 'partial' ? '证据不完整，可导出 partial 包' : '包内证据完整' }}</NTag>
          <p>包含 {{ preview.manifest.files.length }} 个文件，{{ preview.manifest.files.reduce((sum, f) => sum + f.size, 0) }} 字节</p>
          <details><summary>实际包含文件与 SHA-256</summary><p v-for="f in preview.manifest.files" :key="f.path">{{ f.path }} · {{ f.size }} B · {{ f.sha256 }}</p></details>
          <details><summary>引用、缺失与排除内容</summary><p v-for="(r, index) in preview.manifest.references" :key="index">{{ r.kind }} {{ r.id || '未记录' }} · {{ r.status }} · {{ r.disposition }} · {{ r.reason }}</p></details>
          <details open><summary>实际证据缺口</summary><p v-for="gap in preview.manifest.gaps" :key="gap">{{ gap }}</p></details>
          <NButton type="primary" :disabled="busy || !inventory.export_enabled" @click="create">确认范围并后台生成</NButton>
        </template>
        <template v-if="job">
          <p role="status">真实导出状态：{{ job.status }} · 尝试 {{ job.attempt_count }} 次</p>
          <NAlert v-if="job.status === 'failed'" type="error">导出失败：{{ job.error_code }}。已冻结清单保留。</NAlert>
          <NButton v-if="job.status === 'failed' && job.retryable" :disabled="busy" @click="retry">重试同一导出</NButton>
          <NAlert v-if="job.status === 'ready' && job.evidence_partial" type="warning">导出完成，但科研证据不完整，请查看包内缺口。</NAlert>
          <NButton v-if="job.status === 'ready'" :disabled="busy" @click="download">核验 SHA-256 并下载 ZIP</NButton>
          <p v-if="job.archive_sha256">ZIP SHA-256：{{ job.archive_sha256 }}</p>
          <ProjectScientificSummary v-if="job.status === 'ready'" :project-id="projectId" :manifest-id="job.id" :claims="claims" />
          <NButton :disabled="busy" @click="previewSummary">查看项目综合报告只读原型</NButton>
          <p>原型不发布正式报告、不生成 PDF、不改写此 ZIP；正式整合需新的交付范围版本。</p>
          <iframe v-if="summary" :srcdoc="summary" sandbox="" title="项目综合报告只读原型" style="width:100%;height:70vh;border:0" />
        </template>
        <p>离线核验：解出 verify_project_delivery.py，执行 python verify_project_delivery.py project-delivery.zip。缺失报告请进入既有报告流程；导出不会生成报告或启动分析。</p>
      </template>
    </NSpace>
  </NCard>
</template>

<style scoped>
.project-delivery { margin-top: 16px; }
.project-delivery p, .project-delivery a { overflow-wrap: anywhere; }
.task-entry { border-bottom: 1px solid var(--border-color, #d9d9df); padding: 12px 0; }
.task-entry a { margin-inline-start: 8px; }
@media (max-width: 640px) { .task-entry a { display: block; margin-inline-start: 0; } }
</style>
