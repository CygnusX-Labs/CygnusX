<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NInput, NSelect } from 'naive-ui'
import { claimProvenanceApi, type ClaimCellQuery, type ClaimProvenance } from '@/api/claimProvenance'
import type { ResearchArtifact, ResearchReport } from '@/api/researchDelivery'

const props = defineProps<{ projectId: string; taskId: string; artifacts: ResearchArtifact[]; reports: ResearchReport[] }>()
const emit = defineEmits<{ select: [query: ClaimCellQuery] }>()
const feature = ref('')
const file = ref<string | null>(null)
const report = ref<string | null>(null)
const column = ref<ClaimCellQuery['column']>('padj')
const result = ref<ClaimProvenance | null>(null)
const error = ref('')
const busy = ref(false)
let generation = 0
let pending = new AbortController()
const files = computed(() => props.artifacts.filter(a => a.logical_name === 'deg.tsv' && a.file_record_id && a.integrity === 'VERIFIED').map(a => ({ label: `deg.tsv · ${a.file_record_id}`, value: a.file_record_id! })))
const reportOptions = computed(() => props.reports.filter(r => r.kind !== 'delivery' && r.state === 'completed').map(r => ({ label: `${r.kind} · v${r.version ?? '?'} · ${r.report_id}`, value: r.report_id })))
const columns = ['log2FoldChange', 'pvalue', 'padj', 'baseMean', 'lfcSE', 'stat'].map(value => ({ label: value, value }))
function reset() {
  generation++; pending.abort(); pending = new AbortController()
  feature.value = ''; file.value = files.value[0]?.value ?? null; report.value = null
  result.value = null; error.value = ''; busy.value = false
}
async function inspect() {
  if (!file.value || !feature.value.trim()) return
  const current = ++generation, project = props.projectId
  pending.abort(); pending = new AbortController()
  busy.value = true; result.value = null; error.value = ''
  try {
    const value = await claimProvenanceApi.inspect(project, { task_id: props.taskId, file_record_id: file.value, feature_id: feature.value.trim(), column: column.value, source_report_id: report.value }, pending.signal)
    if (current === generation && value.project_id === props.projectId && value.task_id === props.taskId) result.value = value
  } catch (exc) {
    if (current === generation) {
      const response = (exc as { response?: { status?: number; data?: { code?: string } } }).response
      error.value = response?.data?.code === 'FEATURE_DISABLED' ? '结果依据查询尚未启用。' : response?.status === 403 || response?.status === 404 ? '当前无权访问或证据记录不可用。' : '结果依据无法核验，请检查文件、版本、SHA 及缺失证据。'
    }
  } finally { if (current === generation) busy.value = false }
}
watch(() => [props.projectId, props.taskId], reset, { immediate: true })
onBeforeUnmount(() => { generation++; pending.abort() })
</script>
<template>
  <details class="claim-evidence">
    <summary>查看结果依据（DEG 单元格）</summary>
    <p>只核验指定基因与列的实际值，不验证机制、因果或自由文本科研解释。</p>
    <NAlert v-if="!files.length" type="info">没有可查询的受管且已核验 deg.tsv。</NAlert>
    <template v-else>
      <label>结果文件<NSelect v-model:value="file" :options="files" :disabled="busy" aria-label="结果文件" /></label>
      <label>来源报告版本（可选）<NSelect v-model:value="report" :options="reportOptions" :disabled="busy" clearable aria-label="来源报告版本" /></label>
      <label>基因 / feature identifier<NInput v-model:value="feature" :disabled="busy" :maxlength="256" aria-label="基因标识" /></label>
      <label>数值列<NSelect v-model:value="column" :options="columns" :disabled="busy" aria-label="数值列" /></label>
      <NButton :disabled="busy || !file || !feature.trim()" :loading="busy" @click="inspect">核验结果依据</NButton>
    </template>
    <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
    <div v-if="result" class="claim-proof">
      <NButton :disabled="result.verification_status !== 'VERIFIED_VALUE'" @click="emit('select', { task_id: result.task_id, file_record_id: result.file_record_id, feature_id: result.row_identifier, column: result.column_identifier as ClaimCellQuery['column'], source_report_id: result.source_report_id })">纳入项目报告</NButton>
      <p>单元值：{{ result.value ?? '未记录 / NA' }} · {{ result.verification_status }}</p>
      <p>有限陈述：{{ result.supported_statement || 'NOT_VERIFIED' }} · {{ result.supported_statement_status }}</p>
      <p v-if="result.interpretation_status">解释：{{ result.claim_text }} · AI_INTERPRETATION（未核验）</p>
      <p>文件 {{ result.file_record_id }} · SHA-256 {{ result.file_sha256 }}</p>
      <p>行 {{ result.row_identifier }}（{{ result.row_number }}） · 列 {{ result.column_identifier }}</p>
      <p>Observation {{ result.result_observation_id || 'NOT_RECORDED' }} · {{ result.observation_binding }}</p>
      <p><RouterLink :to="`/tasks/${result.task_id}`">Task {{ result.task_id }}</RouterLink></p>
      <p>DatasetVersion {{ result.dataset_version_id || 'NOT_RECORDED' }} · AnalysisLink {{ result.analysis_link_id || 'NOT_RECORDED' }}</p>
      <p>ExecutionDefinition {{ result.definition_digest || 'NOT_RECORDED' }} · {{ result.definition_status }}</p>
      <p>输入 FileRecord：{{ result.input_file_record_ids.join('、') || 'NOT_RECORDED' }}</p>
      <p>Snapshot {{ result.report_snapshot_id || 'NOT_RECORDED' }}</p>
      <p v-if="result.source_report_id"><RouterLink :to="{ path: '/reports', query: { reportId: result.source_report_id } }">来源报告 · 版本 {{ result.report_version }}</RouterLink></p>
      <p>复现状态 {{ result.reproducibility_status }}；数值核验不代表全链证据完整。</p>
      <p v-for="gap in result.missing_evidence" :key="gap">{{ gap }}</p>
    </div>
  </details>
</template>
<style scoped>
.claim-evidence { margin-block: 12px; }
.claim-evidence label { display: block; margin-block: 8px; }
.claim-proof { overflow-wrap: anywhere; }
</style>
