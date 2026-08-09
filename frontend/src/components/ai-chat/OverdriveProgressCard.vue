<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NInput, NProgress, NSelect, useMessage } from 'naive-ui'
import type { OverdriveProgress } from './types'
import { chatApi } from '@/api/chat'
import { useAgentHubStore } from '@/stores/agentHub'

const props = defineProps<{
  progress: OverdriveProgress
  compact?: boolean
}>()

const store = useAgentHubStore()
const message = useMessage()
const selectedTaskId = ref<string | null>(null)
const directive = ref('')
const controlling = ref(false)
const pendingOptions = computed(() => (props.progress.tasks || [])
  .filter((task) => ['pending', 'ready'].includes(task.status))
  .map((task) => ({ label: `${task.taskId} · ${task.agentId}`, value: task.taskId })))
const failedTasks = computed(() => (props.progress.tasks || [])
  .filter((task) => ['failed', 'skipped'].includes(task.status) && task.errorSummary))

function taskStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '等待中',
    ready: '已就绪',
    running: '执行中',
    completed: '已完成',
    success: '已完成',
    failed: '失败',
    skipped: '已跳过',
  }
  return labels[status] || status
}

function taskStatusClass(status: string): string {
  if (['completed', 'success'].includes(status)) return 'is-complete'
  if (['failed', 'skipped'].includes(status)) return 'is-error'
  if (['running', 'ready'].includes(status)) return 'is-running'
  return 'is-pending'
}

async function control(action: 'pause' | 'resume' | 'skip' | 'terminate') {
  if (!store.currentSessionId || controlling.value) return
  if (action === 'skip' && !selectedTaskId.value) {
    message.warning('请先选择要跳过的待执行任务')
    return
  }
  controlling.value = true
  try {
    await chatApi.controlOverdrive(store.currentSessionId, action, {
      taskId: action === 'skip' ? selectedTaskId.value || undefined : undefined,
    })
    message.success(action === 'terminate' ? '终止指令已发送' : '调度指令已发送')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '调度指令发送失败')
  } finally {
    controlling.value = false
  }
}

async function submitDirective() {
  if (!store.currentSessionId || !directive.value.trim() || controlling.value) return
  controlling.value = true
  try {
    await chatApi.controlOverdrive(store.currentSessionId, 'directive', {
      directive: directive.value.trim(),
    })
    directive.value = ''
    message.success('补充指令将在下一 Wave 生效')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '补充指令发送失败')
  } finally {
    controlling.value = false
  }
}

function phaseLabel(phase: OverdriveProgress['phase']): string {
  const labels: Record<OverdriveProgress['phase'], string> = {
    manager_ready: '规划中',
    workers_starting: '准备中',
    worker_running: '协作中',
    tool_running: '执行中',
    worker_finished: '协作中',
    peer_reviewing: '复核中',
    summarizing: '整合中',
    awaiting_input: '等待你',
    paused: '已暂停',
    completed: '已完成',
  }
  return labels[phase]
}

function stepClass(phase: OverdriveProgress['phase'], step: number): string {
  const activeStep = phase === 'completed'
    ? 4
    : ['peer_reviewing', 'summarizing'].includes(phase)
      ? 3
      : phase === 'manager_ready'
        ? 1
        : 2
  if (step < activeStep) return 'is-complete'
  return step === activeStep ? 'is-active' : ''
}

function percentage(progress: OverdriveProgress): number {
  if (progress.phase === 'completed') return 100
  if (progress.phase === 'awaiting_input') return progress.total ? 88 : 32
  if (progress.phase === 'paused') return progress.total ? Math.max(24, (progress.completed / progress.total) * 68) : 24
  if (progress.phase === 'peer_reviewing') return 86
  if (progress.phase === 'summarizing') return 92
  if (!progress.total) return progress.phase === 'manager_ready' ? 12 : 24
  const workerPercentage = (progress.completed / progress.total) * 68
  return Math.min(88, Math.max(24, 24 + workerPercentage))
}
</script>

<template>
  <div class="overdrive-progress-card" :class="{ 'is-compact': compact }" role="status" aria-live="polite">
    <div class="overdrive-progress-card__header">
      <div class="overdrive-progress-card__copy">
        <div class="overdrive-progress-card__eyebrow">
          <span
            class="overdrive-progress-card__pulse"
            :class="{ 'is-complete': progress.phase === 'completed' }"
            aria-hidden="true"
          />
          超频协作
        </div>
        <div class="overdrive-progress-card__label">{{ progress.label }}</div>
        <div class="overdrive-progress-card__badges">
          <span v-if="progress.waveMode" class="overdrive-progress-card__badge">
            Wave {{ progress.wave || 1 }}/{{ progress.waveTotal || 1 }} · {{ progress.waveMode === 'parallel' ? '并行' : '串行' }}
          </span>
          <span v-if="progress.fallback" class="overdrive-progress-card__badge is-warning">已使用默认分工</span>
          <span v-if="progress.stalledTaskIds?.length" class="overdrive-progress-card__badge is-stalled">
            {{ progress.stalledTaskIds.length }} 个任务疑似停滞
          </span>
        </div>
      </div>
      <span class="overdrive-progress-card__phase">{{ phaseLabel(progress.phase) }}</span>
    </div>

    <div v-if="progress.warning" class="overdrive-progress-card__warning">{{ progress.warning }}</div>

    <div
      v-if="!progress.readonly && progress.phase !== 'completed' && progress.phase !== 'awaiting_input'"
      class="overdrive-progress-card__controls"
    >
      <NButton size="tiny" secondary :loading="controlling" @click="control(progress.phase === 'paused' ? 'resume' : 'pause')">
        {{ progress.phase === 'paused' ? '继续' : '暂停' }}
      </NButton>
      <NSelect v-model:value="selectedTaskId" size="tiny" clearable placeholder="选择待跳过任务" :options="pendingOptions" />
      <NButton size="tiny" secondary :disabled="!pendingOptions.length" :loading="controlling" @click="control('skip')">跳过</NButton>
      <NButton size="tiny" secondary type="error" :loading="controlling" @click="control('terminate')">终止</NButton>
      <NInput v-model:value="directive" size="small" placeholder="补充给下一 Wave 的指令" @keyup.enter="submitDirective" />
      <NButton size="small" secondary :disabled="!directive.trim()" :loading="controlling" @click="submitDirective">发送</NButton>
    </div>

    <details v-for="task in failedTasks" :key="task.taskId" class="overdrive-progress-card__error">
      <summary>{{ task.taskId }} · {{ task.status === 'failed' ? '失败' : '已跳过' }}</summary>
      <pre>{{ task.errorSummary }}</pre>
    </details>

    <div class="overdrive-progress-card__steps" aria-hidden="true">
      <span :class="stepClass(progress.phase, 1)">Manager 规划</span>
      <span :class="stepClass(progress.phase, 2)">专家协作</span>
      <span :class="stepClass(progress.phase, 3)">结论交付</span>
    </div>

    <div class="overdrive-progress-card__bar-row">
      <NProgress
        type="line"
        :percentage="percentage(progress)"
        :show-indicator="false"
        :processing="progress.phase !== 'completed' && progress.phase !== 'awaiting_input'"
        :status="progress.phase === 'completed' ? 'success' : 'default'"
      />
      <span v-if="progress.total" class="overdrive-progress-card__count">
        {{ progress.completed }}/{{ progress.total }}
      </span>
    </div>

    <div v-if="progress.tasks?.length" class="overdrive-progress-card__tasks" aria-label="并行 Agent 任务状态">
      <div class="overdrive-progress-card__tasks-heading">
        <span>并行 Agent</span>
        <span>{{ progress.completed }}/{{ progress.total || progress.tasks.length }} 已完成</span>
      </div>
      <div class="overdrive-progress-card__task-grid">
        <div v-for="task in progress.tasks" :key="task.taskId" class="overdrive-progress-card__task">
          <span class="overdrive-progress-card__task-dot" :class="taskStatusClass(task.status)" aria-hidden="true" />
          <span class="overdrive-progress-card__task-copy">
            <strong>{{ task.agentId || task.taskId }}</strong>
            <span>{{ taskStatusLabel(task.status) }}</span>
          </span>
          <span v-if="task.errorSummary" class="overdrive-progress-card__task-error" :title="task.errorSummary">!</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.overdrive-progress-card {
  width: min(calc(100vw - 48px), 1120px);
  padding: 12px 14px;
  border: 1px solid var(--chat-border);
  border-radius: var(--radius-lg, 14px);
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--chat-surface) 94%, var(--chat-accent) 6%),
    var(--chat-surface)
  );
  box-shadow: 0 8px 24px color-mix(in srgb, var(--chat-accent) 8%, transparent);
}

.overdrive-progress-card.is-compact {
  padding: 12px 14px;
  box-shadow: 0 6px 18px color-mix(in srgb, var(--chat-accent) 9%, transparent);
}

.overdrive-progress-card__header,
.overdrive-progress-card__bar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.overdrive-progress-card__header {
  align-items: flex-start;
  justify-content: space-between;
}

.overdrive-progress-card__copy {
  min-width: 0;
}

.overdrive-progress-card__eyebrow {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--chat-accent);
  font-size: 12px;
  font-weight: 650;
}

.overdrive-progress-card__pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--chat-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--chat-accent) 16%, transparent);
  animation: overdrive-pulse 1.5s ease-in-out infinite;
}

.overdrive-progress-card__pulse.is-complete {
  background: var(--success-color, #18a058);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--success-color, #18a058) 16%, transparent);
  animation: none;
}

.overdrive-progress-card__label {
  margin-top: 4px;
  overflow: hidden;
  color: var(--chat-text-primary);
  font-size: 14px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overdrive-progress-card__badges,
.overdrive-progress-card__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.overdrive-progress-card__badge {
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--chat-text-secondary);
  background: color-mix(in srgb, var(--chat-text-primary) 7%, transparent);
  font-size: 11px;
}

.overdrive-progress-card__badge.is-warning,
.overdrive-progress-card__warning {
  color: var(--warning-color, #d97706);
}

.overdrive-progress-card__badge.is-stalled {
  color: var(--warning-color, #d97706);
  animation: overdrive-stalled 1.6s ease-in-out infinite;
}

.overdrive-progress-card__warning {
  margin-top: 10px;
  font-size: 12px;
}

.overdrive-progress-card__controls :deep(.n-select) {
  min-width: 260px;
  flex: 1;
}

.overdrive-progress-card__controls :deep(.n-input) {
  min-width: 260px;
  flex: 1;
}

.overdrive-progress-card__error {
  margin-top: 6px;
  color: var(--error-color, #d03050);
  font-size: 12px;
}

.overdrive-progress-card__error pre {
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
}

.overdrive-progress-card__phase {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  color: var(--chat-text-secondary);
  background: color-mix(in srgb, var(--chat-text-primary) 6%, transparent);
  font-size: 11px;
}

.overdrive-progress-card__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 7px;
}

.overdrive-progress-card__steps span {
  position: relative;
  padding-top: 8px;
  color: var(--chat-text-muted);
  font-size: 11px;
}

.overdrive-progress-card__steps span::before {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--chat-text-primary) 10%, transparent);
  content: '';
}

.overdrive-progress-card__steps span.is-active {
  color: var(--chat-text-primary);
  font-weight: 600;
}

.overdrive-progress-card__steps span.is-active::before {
  background: var(--chat-accent);
}

.overdrive-progress-card__steps span.is-complete::before {
  background: var(--success-color, #18a058);
}

.overdrive-progress-card__bar-row :deep(.n-progress) {
  min-width: 0;
  flex: 1;
}

.overdrive-progress-card__bar-row :deep(.n-progress-graph) {
  min-width: 0;
}

.overdrive-progress-card__count {
  min-width: 34px;
  color: var(--chat-text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.overdrive-progress-card__tasks {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid color-mix(in srgb, var(--chat-border) 70%, transparent);
}

.overdrive-progress-card__tasks-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
  color: var(--chat-text-muted);
  font-size: 11px;
}

.overdrive-progress-card__task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 6px;
}

.overdrive-progress-card__task {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid color-mix(in srgb, var(--chat-border) 75%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--chat-surface) 86%, var(--chat-accent) 14%);
}

.overdrive-progress-card__task-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--chat-text-muted);
}

.overdrive-progress-card__task-dot.is-running { background: var(--chat-accent); animation: overdrive-pulse 1.4s ease-in-out infinite; }
.overdrive-progress-card__task-dot.is-complete { background: var(--success-color, #18a058); }
.overdrive-progress-card__task-dot.is-error { background: var(--error-color, #d03050); }

.overdrive-progress-card__task-copy {
  display: grid;
  min-width: 0;
  gap: 1px;
}

.overdrive-progress-card__task-copy strong,
.overdrive-progress-card__task-copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overdrive-progress-card__task-copy strong { color: var(--chat-text-primary); font-size: 12px; }
.overdrive-progress-card__task-copy span { color: var(--chat-text-muted); font-size: 11px; }
.overdrive-progress-card__task-error { margin-left: auto; color: var(--error-color, #d03050); font-weight: 700; }

@keyframes overdrive-pulse {
  50% { opacity: 0.55; transform: scale(0.86); }
}

@keyframes overdrive-stalled {
  50% { opacity: 0.5; transform: scale(0.98); }
}

@media (max-width: 640px) {
  .overdrive-progress-card {
    width: calc(100vw - 20px);
  }

  .overdrive-progress-card__steps {
    margin-top: 10px;
  }

  .overdrive-progress-card__controls :deep(.n-select),
  .overdrive-progress-card__controls :deep(.n-input) {
    min-width: 100%;
  }

  .overdrive-progress-card__label {
    white-space: normal;
  }
}

@media (prefers-reduced-motion: reduce) {
  .overdrive-progress-card__pulse { animation: none; }
  .overdrive-progress-card__badge.is-stalled { animation: none; }
}
</style>
