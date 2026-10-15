<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NInput } from 'naive-ui'
import { agentToolsApi, asToolProposal, type ToolLink, type ToolProposal } from '@/api/agentTools'
import AgentToolProposalCard from './AgentToolProposalCard.vue'
import DatasetImportCard from './DatasetImportCard.vue'

const props = defineProps<{ sessionId: string }>()
const accession = ref('')
const preview = ref<ToolProposal | null>(null)
const links = ref<ToolLink[]>([])
const error = ref('')
const busy = ref(false)
let generation = 0
async function restore() {
  const snapshot = ++generation
  preview.value = null
  error.value = ''
  links.value = []
  try {
    const result = await agentToolsApi.related(props.sessionId)
    if (snapshot === generation) links.value = result
  } catch {
    if (snapshot === generation) error.value = '共享工具尚未开放或记录服务不可用。'
  }
}
async function prepare(value = accession.value) {
  const session = props.sessionId
  const snapshot = generation
  busy.value = true
  error.value = ''
  preview.value = null
  try {
    const response = await agentToolsApi.invoke(session, 'downloads.prepare', { accession: value })
    if (snapshot !== generation) return
    preview.value = asToolProposal(response.result)
    if (!preview.value) error.value = '该编号需要先解析为受支持 Run；当前没有下载任务。'
  } catch {
    if (snapshot === generation) error.value = '无法准备下载，请检查项目授权与编号；未创建任务。'
  } finally { busy.value = false }
}
function show(value: unknown) {
  const envelope = value as { result?: unknown } | null
  const proposal = asToolProposal(envelope?.result)
  if (proposal?.conversation_id === props.sessionId) preview.value = proposal
}
watch(() => props.sessionId, restore, { immediate: true })
defineExpose({ prepare, show })
</script>

<template>
  <section class="tool-panel" aria-label="共享科研工具">
    <div class="prepare"><NInput v-model:value="accession" placeholder="SRR / PRJNA / GEO 编号" aria-label="下载编号" /><NButton :loading="busy" @click="prepare()">检查获取方式</NButton><NButton @click="restore">刷新记录</NButton></div>
    <p v-if="error" role="status">{{ error }}</p>
    <AgentToolProposalCard v-if="preview" :proposal="preview" />
    <ul v-if="links.length"><li v-for="link in links" :key="link.invocation_id">{{ link.capability_id }} · {{ link.task?.status || link.state }}<RouterLink v-if="link.task_id" :to="`/tasks/${link.task_id}`">查看任务</RouterLink><span v-if="link.state === 'SUBMITTING' || link.state === 'RECONCILIATION_REQUIRED'"> 结果待对账，请勿重复提交</span><pre v-if="link.dataset_analysis">{{ JSON.stringify(link.dataset_analysis, null, 2) }}</pre><DatasetImportCard v-if="link.dataset_import" :proposal="link.dataset_import" /><AgentToolProposalCard v-if="link.proposal && link.invocation_id !== preview?.proposal_id" :proposal="link.proposal" /></li></ul>
  </section>
</template>

<style scoped>
.tool-panel { padding: 12px; border-top: 1px solid var(--neutral-border); max-height: 45vh; overflow: auto; }
.prepare { display: flex; flex-wrap: wrap; gap: 8px; }
.prepare :deep(.n-input) { flex: 1; min-width: 160px; }
li { overflow-wrap: anywhere; } a { margin-left: 10px; }
</style>
