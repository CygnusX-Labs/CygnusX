<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import { datasetsApi, type ImportProposal } from '@/api/datasets'
const props = defineProps<{ proposal: ImportProposal }>()
const current = ref(props.proposal)
const error = ref('')
const busy = ref(false)
const now = ref(Date.now())
let generation = 0
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(timer))
watch(() => props.proposal, value => { ++generation; current.value = value; error.value = ''; busy.value = false })
const expired = computed(() => !current.value.expires_at || Date.parse(current.value.expires_at) <= now.value)
const canApprove = computed(() => !expired.value && ['PENDING', 'PREPARED'].includes(current.value.state))
async function decide(approve: boolean) {
  const snapshot = generation
  const proposal = current.value
  busy.value = true
  error.value = ''
  try {
    const result = await datasetsApi.decide(proposal.project_id, proposal.proposal_id, approve)
    if (snapshot === generation) current.value = result
  } catch { if (snapshot === generation) error.value = '审批失败或预案已过期。未提交下载，请刷新核对。' }
  finally { if (snapshot === generation) busy.value = false }
}
</script>
<template>
  <article class="dataset-import" aria-label="科研数据导入预案">
    <h4>导入预案 · {{ expired && !current.tasks.length ? 'EXPIRED' : current.state }}</h4>
    <p>批准只记录授权。下载与分析的运行验收尚未完成，执行保持关闭。</p>
    <details open><summary>来源、目标文件、容量与限制</summary><pre>{{ JSON.stringify(current.preview, null, 2) }}</pre></details>
    <details><summary>规范化下载参数</summary><pre>{{ JSON.stringify(current.normalized_parameters, null, 2) }}</pre></details>
    <p class="digest">参数摘要：{{ current.parameters_hash }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <NButton :disabled="!canApprove || busy" @click="decide(true)">批准预案</NButton>
    <NButton :disabled="!canApprove || busy" @click="decide(false)">拒绝</NButton>
    <NButton disabled>执行尚未开放</NButton>
    <ul v-if="current.tasks.length"><li v-for="task in current.tasks" :key="task.task_id"><RouterLink :to="`/tasks/${task.task_id}`">查看任务</RouterLink> · {{ task.status }} · 进度未知</li></ul>
    <pre v-if="current.errors.length">{{ JSON.stringify(current.errors, null, 2) }}</pre>
  </article>
</template>
<style scoped>
.dataset-import { border: 1px solid var(--neutral-border); border-radius: 8px; padding: 12px; }
h4 { margin: 0 0 8px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 260px; overflow: auto; font-size: 12px; } .digest { overflow-wrap: anywhere; font-size: 11px; } button { margin: 4px; }
</style>
