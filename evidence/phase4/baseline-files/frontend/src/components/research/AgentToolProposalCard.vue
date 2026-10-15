<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { NButton, NTag } from 'naive-ui'
import { agentToolsApi, type ToolProposal } from '@/api/agentTools'

const props = defineProps<{ proposal: ToolProposal }>()
const state = ref(props.proposal.state)
const busy = ref(false)
const error = ref('')
const now = ref(Date.now())
const expired = computed(() => now.value >= Date.parse(props.proposal.expires_at))
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
watch(() => [props.proposal.proposal_id, props.proposal.state], () => { state.value = props.proposal.state; error.value = '' })
async function decide(approve: boolean) {
  now.value = Date.now()
  if (busy.value || expired.value || state.value !== 'PENDING') return
  busy.value = true
  error.value = ''
  const proposalId = props.proposal.proposal_id
  try {
    const result = await agentToolsApi.decide(props.proposal.conversation_id, props.proposal.proposal_id, approve)
    if (props.proposal.proposal_id === proposalId) state.value = result.state
  } catch {
    if (props.proposal.proposal_id === proposalId) error.value = '审批失败或已过期；未提交任务。请刷新记录后检查，系统不会自动重试。'
  } finally { busy.value = false }
}
</script>

<template>
  <article class="tool-proposal" aria-label="执行预案">
    <strong>{{ proposal.operation === 'downloads.submit' ? '下载预案' : '分析预案' }}</strong>
    <NTag size="small">{{ expired ? 'EXPIRED' : state }}</NTag>
    <p>当前执行尚未开放。批准仅记录对这份参数的同意，不会创建下载或分析任务。</p>
    <pre>{{ JSON.stringify(proposal.normalized_parameters, null, 2) }}</pre>
    <details><summary>参数摘要与限制</summary><code>{{ proposal.parameters_hash }}</code><pre>{{ JSON.stringify(proposal.preview, null, 2) }}</pre></details>
    <p>有效期至 {{ proposal.expires_at }}</p>
    <div class="actions">
      <NButton :loading="busy" :disabled="expired || state !== 'PENDING'" @click="decide(true)">批准预案</NButton>
      <NButton :disabled="busy || expired || state !== 'PENDING'" @click="decide(false)">拒绝</NButton>
      <NButton disabled>执行尚未开放</NButton>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
  </article>
</template>

<style scoped>
.tool-proposal { padding: 14px; border: 1px solid var(--neutral-border); border-radius: 8px; }
pre { max-height: 240px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
code { overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
