<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NEmpty, NSelect, NSpace, NTag } from 'naive-ui'
import { researchPlansApi, type PlanEvent, type ResearchPlan } from '@/api/researchPlans'
const props = defineProps<{ projectId: string; planId?: string; sessions?: { id: string; title: string; status: string }[] }>()
const plans = ref<ResearchPlan[]>([])
const traces = ref<Record<string, PlanEvent[]>>({})
const error = ref('')
const loading = ref(false)
const busy = ref(false)
const selectedSession = ref<string | null>(null)
const sessionOptions = computed(() => (props.sessions || []).filter(s => s.status === 'active').map(s => ({ label: s.title || '项目会话', value: s.id })))
let generation = 0
let pending: AbortController | null = null
async function load() {
  const current = ++generation, project = props.projectId, requestedPlan = props.planId
  pending?.abort(); pending = new AbortController()
  plans.value = []; traces.value = {}; error.value = ''; loading.value = true
  try {
    const result = requestedPlan
      ? [await researchPlansApi.get(project, requestedPlan, pending.signal)]
      : await researchPlansApi.list(project, pending.signal)
    if (current === generation && project === props.projectId) {
      plans.value = result.filter(p => p.project_id === project && (!requestedPlan || p.plan_id === requestedPlan))
    }
  } catch { if (current === generation) error.value = '科研计划暂不可用，请检查功能是否启用及当前项目权限。' }
  finally { if (current === generation) loading.value = false }
}
async function act(plan: ResearchPlan, action: 'review' | 'advance' | 'pause' | 'resume' | 'cancel' | 'reconcile') {
  if (busy.value) return
  const current = generation, project = props.projectId
  busy.value = true; error.value = ''
  try {
    let result: ResearchPlan
    if (action === 'review') result = await researchPlansApi.review(project, plan.plan_id, plan.digest)
    else if (action === 'advance') {
      if (!selectedSession.value) return
      result = await researchPlansApi.advance(project, plan.plan_id, selectedSession.value)
    } else if (action === 'reconcile') result = await researchPlansApi.reconcile(project, plan.plan_id)
    else result = await researchPlansApi.control(project, plan.plan_id, action)
    if (current === generation && result.project_id === project && project === props.projectId) {
      plans.value = plans.value.map(p => p.plan_id === result.plan_id ? result : p)
    }
  } catch { if (current === generation) error.value = '操作未完成，请刷新核对计划版本、权限和审阅状态。' }
  finally { if (current === generation) busy.value = false }
}
async function showTrace(plan: ResearchPlan) {
  const current = generation, project = props.projectId
  try {
    const events = await researchPlansApi.events(project, plan.plan_id)
    if (current === generation && project === props.projectId) traces.value[plan.plan_id] = events
  } catch { if (current === generation) error.value = '当前计划轨迹不可读取。' }
}
function detail(plan: ResearchPlan, stepId: string) { return plan.draft.steps.find(s => s.step_id === stepId) }
watch(() => [props.projectId, props.planId], () => { selectedSession.value = null; busy.value = false; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++; pending?.abort() })
</script>
<template>
  <NCard title="科研计划与审阅" size="small">
    <NSpace vertical>
      <NAlert type="info">仅规划与受控预案，尚未开放下载、计算或发布。审阅整份计划不会批准后续写动作。</NAlert>
      <NButton size="small" :loading="loading" :disabled="busy" @click="load">刷新计划</NButton>
      <NAlert v-if="error" type="warning">{{ error }}</NAlert>
      <NEmpty v-if="!loading && !plans.length && !error" description="暂无科研计划，可在项目 AI 助手或寻宝鼠中准备计划。" />
      <NSelect v-model:value="selectedSession" :options="sessionOptions" placeholder="选择用于只读查询的项目会话" clearable />
      <NCard v-for="plan in plans" :key="plan.plan_id" size="small" :title="plan.draft.research_question">
        <p>版本 {{ plan.version }} · {{ plan.status }} · {{ plan.mode }}</p>
        <RouterLink :to="{path: `/projects/${plan.project_id}`, query: {planId: plan.plan_id}}">打开此计划版本</RouterLink>
        <p>计划指纹 {{ plan.digest }}</p>
        <p v-if="plan.superseded_by">该版本已被新版本替代，仅保留历史。
          <RouterLink :to="{path: `/projects/${plan.project_id}`, query: {planId: plan.superseded_by}}">查看新版本</RouterLink>
        </p>
        <p>假设：{{ plan.draft.assumptions.join('；') || '尚未声明' }}</p>
        <p>计算时间估计：{{ plan.draft.budget.estimated_compute_seconds ?? '未知' }}；存储估计：{{ plan.draft.budget.estimated_storage_bytes ?? '未知' }}</p>
        <p>缺口：{{ plan.gaps.join('、') || '无已记录缺口' }}</p>
        <NCollapse>
          <NCollapseItem v-for="step in plan.steps" :key="step.step_id" :name="step.step_id" :title="`${step.step_id} · ${detail(plan, step.step_id)?.goal || ''}`">
            <NSpace><NTag>{{ step.status }}</NTag><NTag>{{ step.effect }}</NTag></NSpace>
            <p>依赖：{{ detail(plan, step.step_id)?.depends_on.join('、') || '无' }}；工具：{{ step.capability_id || '尚未开放' }}</p>
            <p>输入：{{ JSON.stringify(detail(plan, step.step_id)?.arguments || {}) }}</p>
            <p>预期产物：{{ step.expected_output }}；实际调用：{{ step.invocation_id || '尚未调用' }}</p>
            <p v-if="step.approval_required">本步骤需要独立人类审批；真实执行门禁尚未通过。</p>
            <RouterLink v-if="step.task_id" :to="`/tasks/${step.task_id}`">查看真实任务与日志</RouterLink>
            <p v-else>仅规划或预案，尚未提交真实任务。</p>
            <p v-if="step.result_manifest_sha256">结果清单 SHA-256 {{ step.result_manifest_sha256 }}</p>
            <p v-for="report in step.reports || []" :key="report.report_id"><RouterLink :to="{path: '/reports', query: {reportId: report.report_id}}">{{ report.kind === 'scientific' ? '科学报告' : '执行证据报告' }}</RouterLink> · {{ report.integrity }}</p>
            <p v-if="step.error_code">{{ step.error_code }}</p>
          </NCollapseItem>
        </NCollapse>
        <NSpace v-if="!plan.superseded_by">
          <NButton v-if="plan.status === 'READY_FOR_REVIEW' && !plan.reviewed_at" :disabled="busy" @click="act(plan, 'review')">确认已审阅计划（不批准执行）</NButton>
          <NButton v-if="['APPROVED', 'RUNNING'].includes(plan.status)" :disabled="busy || !selectedSession" @click="act(plan, 'advance')">推进一个只读或预案步骤</NButton>
          <NButton v-if="['APPROVED', 'RUNNING'].includes(plan.status)" :disabled="busy" @click="act(plan, 'pause')">暂停后续调度</NButton>
          <NButton v-if="plan.status === 'PAUSED'" :disabled="busy" @click="act(plan, 'resume')">恢复计划</NButton>
          <NButton v-if="!['COMPLETED', 'FAILED', 'CANCELLED'].includes(plan.status)" :disabled="busy" @click="act(plan, 'cancel')">取消后续计划</NButton>
        </NSpace>
        <NButton size="small" :disabled="busy" @click="act(plan, 'reconcile')">核对已有调用与任务（不重跑）</NButton>
        <NButton size="small" @click="showTrace(plan)">查看审阅与工具轨迹</NButton>
        <p v-for="(event, index) in traces[plan.plan_id] || []" :key="index">{{ event.at }} · {{ event.kind }} · {{ event.step_id || '' }} · {{ event.invocation_id || '' }}</p>
      </NCard>
    </NSpace>
  </NCard>
</template>
