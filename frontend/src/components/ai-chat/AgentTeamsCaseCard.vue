<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NTag } from 'naive-ui'
import { useRouter } from 'vue-router'
import type { AgentTeamsCaseStatus } from '@/api/agentTeams'
import { useAgentTeamsStore } from '@/stores/agentTeams'
import { shouldPollAgentTeamsCase } from '@/utils/agentTeamsState'
import { agentTeamsNextActor, agentTeamsStatusLabel } from '@/utils/agentTeamsStatus'
import type { AgentTeamsCaseCardPayload } from './types'

const props = defineProps<{ caseInfo: AgentTeamsCaseCardPayload }>()

const router = useRouter()
const agentTeamsStore = useAgentTeamsStore()
const detail = ref<AgentTeamsCaseCardPayload>({ ...props.caseInfo })
const loading = ref(false)
const decisionLoading = ref(false)
const decisionError = ref('')
let timer: ReturnType<typeof setInterval> | null = null

const isApprovalPending = computed(() => detail.value.status === 'approval_pending')
const displayStatus = computed(() => agentTeamsStatusLabel[detail.value.status as AgentTeamsCaseStatus] || detail.value.status)
const updatedAt = computed(() => {
  if (!detail.value.updated_at) return ''
  const value = new Date(detail.value.updated_at)
  return Number.isNaN(value.getTime()) ? '' : value.toLocaleString()
})
const planShortHash = computed(() => detail.value.plan_hash ? detail.value.plan_hash.slice(0, 12) : '')

async function refresh() {
  if (!shouldPollAgentTeamsCase(document.visibilityState) || loading.value) return
  loading.value = true
  try {
    const value = await agentTeamsStore.refreshCase(detail.value.case_id)
    detail.value = {
      ...detail.value,
      title: value.intent.slice(0, 80) || detail.value.title,
      status: value.status,
      next_actor: agentTeamsNextActor[value.status] || detail.value.next_actor,
      updated_at: value.updated_at,
      plan_hash: value.plan_hash,
      proposed_submission: value.proposed_submission,
    }
  } catch {
  } finally {
    loading.value = false
  }
}

async function approveCase() {
  if (decisionLoading.value) return
  decisionLoading.value = true
  decisionError.value = ''
  try {
    await agentTeamsStore.submitCase(detail.value.case_id, { task_name: detail.value.title.slice(0, 128) })
    await refresh()
  } catch (cause: any) {
    decisionError.value = cause?.response?.data?.detail || '审批失败，请刷新后重试。'
  } finally {
    decisionLoading.value = false
  }
}

function openCase() {
  void router.push(detail.value.case_url || `/agent-teams/cases/${detail.value.case_id}`)
}

onMounted(() => {
  void refresh()
  timer = setInterval(() => void refresh(), 20_000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <section class="agentteams-case-card">
    <div class="case-header">
      <div>
        <p class="eyebrow">AgentTeams 协作 Case</p>
        <strong>{{ detail.title }}</strong>
      </div>
      <NTag size="small" :type="isApprovalPending ? 'warning' : 'info'">{{ displayStatus }}</NTag>
    </div>
    <p class="case-meta">下一责任方：{{ detail.next_actor }}</p>
    <p v-if="updatedAt" class="case-updated">最近更新：{{ updatedAt }}</p>
    <div v-if="isApprovalPending" class="approval-rail">
      <p>审批待处理：确认冻结计划后继续执行。</p>
      <p v-if="planShortHash" class="plan-hash">计划短码：{{ planShortHash }}</p>
      <NButton size="small" type="primary" :loading="decisionLoading" @click="approveCase">批准并继续</NButton>
      <span v-if="decisionError" class="decision-error" role="alert">{{ decisionError }}</span>
    </div>
    <div class="case-actions">
      <NButton size="small" :loading="loading" @click="refresh">刷新状态</NButton>
      <NButton size="small" type="primary" @click="openCase">打开 Case</NButton>
    </div>
  </section>
</template>

<style scoped>
.agentteams-case-card { margin-top: 12px; padding: 14px; border: 1px solid var(--chat-border); border-radius: 12px; background: color-mix(in srgb, var(--chat-bg) 88%, #6366f1 12%); }
.case-header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.eyebrow { margin: 0 0 4px; color: var(--chat-text-muted); font-size: 12px; }
.case-meta, .case-updated, .approval-rail { margin: 10px 0 0; font-size: 13px; color: var(--chat-text-secondary); }
.approval-rail { display: grid; gap: 8px; padding: 8px; border-left: 3px solid var(--warning-color, #f59e0b); background: color-mix(in srgb, var(--warning-color, #f59e0b) 12%, transparent); }
.approval-rail p { margin: 0; }
.plan-hash { color: var(--chat-text-muted); font-family: ui-monospace, monospace; font-size: 12px; }
.decision-error { color: var(--error-color, #d03050); font-size: 12px; }
.case-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
</style>
