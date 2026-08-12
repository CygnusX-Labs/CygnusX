<script setup lang="ts">
import { computed, type Component } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { AnalyticsOutline, GitNetworkOutline, HardwareChipOutline } from '@vicons/ionicons5'
import type { RoutedAgentInfo } from './types'

const props = defineProps<{ route: RoutedAgentInfo }>()

const emit = defineEmits<{
  confirmExecution: [preset: string]
  adjustExecution: [preset: string]
}>()

const transition = computed(() => props.route.transition)
const accentStyle = computed(() => ({
  '--route-agent-color': props.route.color || 'var(--brand-primary)',
}))
const confidencePercent = computed(() => {
  const value = Number(props.route.confidence)
  if (!Number.isFinite(value)) return null
  return Math.round(Math.max(0, Math.min(100, value <= 1 ? value * 100 : value)))
})
const intentLabel = computed(() => {
  const labels: Record<string, string> = {
    chat: '通用问答',
    transfer: '专家转交',
    fanout: '并行分析',
    consult: '多专家会诊',
    case: '协作任务',
    dag: '分析工作流',
  }
  return labels[props.route.intent || ''] || transition.value?.title || '任务匹配'
})
const targetIcon = computed<Component>(() => {
  if (props.route.intent === 'dag') return AnalyticsOutline
  if (['fanout', 'consult', 'case'].includes(props.route.intent || '')) return GitNetworkOutline
  return HardwareChipOutline
})
const needsConfirmation = computed(() => Boolean(transition.value?.requiresExecutionConfirmation))
function handleConfirm() {
  emit('confirmExecution', '确认开始执行，请按上述方案启动专项分析。')
}
function handleAdjust() {
  emit('adjustExecution', '我想先调整参数或方案，暂不开始执行。')
}
</script>

<template>
  <Transition name="route-event" appear>
    <aside
      v-if="transition?.visible"
      class="route-event"
      :style="accentStyle"
      role="status"
      aria-live="polite"
      aria-label="Agent 路由已更新"
    >
      <div class="route-event__body">
        <div class="route-event__path">
          <span class="route-event__eyebrow">STELLAR ROUTER</span>
          <span class="route-event__source">星尘 AI</span>
          <span class="route-event__arrow" aria-hidden="true">→</span>
          <strong class="route-event__target">
            <NIcon class="route-event__target-icon" :component="targetIcon" :size="14" aria-hidden="true" />
            {{ route.name }}
          </strong>
          <span class="route-event__status">路由更新</span>
        </div>
        <p class="route-event__reason">{{ route.reason }}</p>
      </div>
      <div class="route-event__meta">
        <span>{{ intentLabel }}</span>
        <span v-if="confidencePercent !== null">{{ confidencePercent }}%</span>
        <span v-if="transition.requiresExecutionConfirmation" class="route-event__guard">
          执行前需确认
        </span>
      </div>
      <div v-if="needsConfirmation" class="route-event__actions">
        <NButton size="small" type="primary" @click="handleConfirm">
          <template #icon><NIcon><HardwareChipOutline /></NIcon></template>
          确认开始
        </NButton>
        <NButton size="small" tertiary @click="handleAdjust">
          调整参数
        </NButton>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.route-event {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  width: 100%;
  max-width: 1120px;
  margin: 0 0 var(--space-md, 12px);
  padding: 10px 12px;
  overflow: hidden;
  color: var(--neutral-text-1);
  background: color-mix(in srgb, var(--neutral-card) 99%, var(--route-agent-color) 1%);
  border: 1px solid color-mix(in srgb, var(--route-agent-color) 10%, var(--neutral-border));
  border-radius: 10px;
  box-shadow: none;
}

.route-event::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 2px;
  background: color-mix(in srgb, var(--route-agent-color) 68%, var(--neutral-border));
  content: '';
}

.route-event__body { min-width: 0; }

.route-event__path {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 12px;
}

.route-event__eyebrow {
  color: var(--route-agent-color);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.13em;
}

.route-event__source,
.route-event__arrow { color: var(--neutral-text-3); }

.route-event__target {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  color: var(--route-agent-color);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-event__target-icon { flex: 0 0 auto; }

.route-event__status {
  flex: 0 0 auto;
  padding: 2px 6px;
  color: var(--arco-success);
  background: color-mix(in srgb, var(--arco-success) 8%, transparent);
  border-radius: 999px;
  font-size: 10px;
  font-weight: 650;
}

.route-event__reason {
  overflow: hidden;
  margin: 3px 0 0;
  color: var(--neutral-text-3);
  font-size: 11px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-event__meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--neutral-text-3);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.route-event__meta > span {
  padding: 3px 7px;
  background: color-mix(in srgb, var(--neutral-fill-2) 78%, transparent);
  border-radius: 999px;
}

.route-event__meta .route-event__guard {
  color: var(--arco-warning);
  background: color-mix(in srgb, var(--arco-warning) 8%, transparent);
}

.route-event__actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.route-event-enter-active,
.route-event-leave-active {
  transition: opacity var(--motion-standard, 220ms) ease-out, transform var(--motion-standard, 220ms) ease-out;
}

.route-event-enter-from,
.route-event-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 680px) {
  .route-event { grid-template-columns: minmax(0, 1fr); }
  .route-event__meta { grid-column: 1; justify-content: flex-start; }
  .route-event__eyebrow,
  .route-event__source { display: none; }
}

@media (prefers-reduced-transparency: reduce) {
  .route-event { background: var(--neutral-card); }
}

@media (prefers-reduced-motion: reduce) {
  .route-event-enter-active,
  .route-event-leave-active { transition: none; }
  .route-event-enter-from,
  .route-event-leave-to { transform: none; }
}
</style>
