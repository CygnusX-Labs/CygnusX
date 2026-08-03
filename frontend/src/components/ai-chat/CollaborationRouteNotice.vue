<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NTag } from 'naive-ui'
import type { CollaborationRouteInfo } from './types'

const props = defineProps<{ route: CollaborationRouteInfo }>()
const emit = defineEmits<{ correct: [route: CollaborationRouteInfo] }>()

const tagType = computed(() => {
  if (props.route.degraded) return 'warning'
  if (!props.route.available) return 'error'
  return 'info'
})

const stateText = computed(() => {
  if (props.route.degraded) return '当前不可用'
  if (!props.route.available) return '需要澄清'
  return '已选择'
})
</script>

<template>
  <details class="collaboration-route-notice" :class="{ 'is-degraded': route.degraded, 'is-blocked': !route.available }" aria-live="polite">
    <summary class="notice-summary">
      <div class="notice-heading">
        <strong>{{ route.label }}</strong>
        <NTag size="small" :type="tagType" :bordered="false">{{ stateText }}</NTag>
      </div>
      <span class="notice-reason">{{ route.available ? route.reason : route.message }}</span>
    </summary>
    <div class="notice-detail">
      <p>{{ route.available ? route.reason : route.message }}</p>
      <NButton quaternary size="tiny" @click="emit('correct', route)">走错了？</NButton>
    </div>
  </details>
</template>

<style scoped>
.collaboration-route-notice { margin: 10px 0; padding: 10px 12px; border: 1px solid var(--chat-border); border-left: 3px solid var(--primary-color, #6366f1); border-radius: 10px; background: var(--chat-bg); }
.collaboration-route-notice.is-degraded { border-left-color: var(--warning-color, #d97706); }
.collaboration-route-notice.is-blocked { border-left-color: var(--error-color, #dc2626); }
.notice-summary { display: flex; align-items: center; justify-content: space-between; gap: 10px; cursor: pointer; list-style: none; }
.notice-summary::-webkit-details-marker { display: none; }
.notice-heading { display: flex; align-items: center; gap: 8px; }
.notice-heading strong { color: var(--chat-text-primary); font-size: 13px; }
.notice-reason { overflow: hidden; color: var(--chat-text-secondary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.notice-detail { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-top: 8px; }
p { margin: 0; color: var(--chat-text-secondary); font-size: 12px; line-height: 1.5; }
@media (max-width: 640px) { .notice-summary, .notice-detail { align-items: flex-start; flex-direction: column; gap: 6px; } .notice-reason { white-space: normal; } }
</style>
