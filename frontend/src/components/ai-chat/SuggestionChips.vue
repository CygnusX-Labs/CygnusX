<script setup lang="ts">
/** 只负责建议展示与事件转发；会话、发送与流式状态由上层维护。 */
import { nextTick, ref } from 'vue'
import { ArrowUpRight } from '@vicons/carbon'
import { SparklesOutline } from '@vicons/ionicons5'
import type { SuggestedFollowUp } from '@/utils/nextStepSuggestions'

const props = withDefaults(defineProps<{
  suggestions: SuggestedFollowUp[]
  disabled?: boolean
}>(), { disabled: false })

const emit = defineEmits<{
  send: [prompt: string]
  prefill: [prompt: string]
}>()

// 先同步关闭本轮交互，覆盖父级发送状态更新并卸载建议前的同帧重复点击。
const activating = ref(false)
async function handleClick(item: SuggestedFollowUp) {
  if (props.disabled || activating.value) return
  activating.value = true
  try {
    if (item.action === 'prefill') emit('prefill', item.prompt)
    else emit('send', item.prompt)
  } finally {
    await nextTick()
    activating.value = false
  }
}

function chipAriaLabel(item: SuggestedFollowUp): string {
  return `${item.label}；${item.action === 'prefill' ? '填入输入框待补充' : '直接发送'}：${item.prompt}`
}
</script>

<template>
  <div v-if="props.suggestions.length" class="suggestion-chips" role="group" aria-label="你可以继续">
    <div class="suggestion-chips__header">
      <SparklesOutline class="suggestion-chips__sparkle" aria-hidden="true" />
      <span>你可以继续</span>
    </div>
    <div class="suggestion-chips__items">
      <button
        v-for="(item, index) in props.suggestions"
        :key="index"
        type="button"
        class="suggestion-chip"
        :disabled="props.disabled || activating"
        :title="`${item.label}\n${item.action === 'prefill' ? '填入输入框待补充：' : ''}${item.prompt}`"
        :aria-label="chipAriaLabel(item)"
        @click="handleClick(item)"
      >
        <span class="suggestion-chip__label">{{ item.label }}</span>
        <ArrowUpRight class="suggestion-chip__arrow" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.suggestion-chips {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  margin-top: var(--space-md, 12px);
  padding: var(--space-lg, 16px) var(--space-xl, 20px);
  border: 1px solid var(--bubble-border, var(--chat-border));
  border-radius: var(--card-radius, 12px);
  background: var(--chat-ai-card);
}

.suggestion-chips__header {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  margin-bottom: var(--space-md, 12px);
  color: var(--text-primary, var(--chat-text-primary));
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
}

.suggestion-chips__sparkle {
  width: 16px;
  height: 16px;
  color: var(--chat-accent);
}

.suggestion-chips__items {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 10px;
}

.suggestion-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  width: fit-content;
  max-width: 100%;
  min-width: 0;
  min-height: 40px;
  box-sizing: border-box;
  padding: 8px 16px;
  border: 1px solid var(--chat-chip-border);
  border-radius: 9999px;
  background: var(--chat-chip-bg);
  color: var(--text-primary, var(--chat-text-primary));
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease, color 0.16s ease;
}

.suggestion-chip:not(:disabled):hover {
  background: var(--surface-highlight, var(--chat-surface-hover));
  border-color: var(--border-focus, var(--chat-accent));
}

.suggestion-chip:focus-visible {
  outline: 2px solid var(--chat-accent);
  outline-offset: 3px;
}

.suggestion-chip:disabled { opacity: 0.55; cursor: default; }

.suggestion-chip__label {
  min-width: 0;
  white-space: normal;
  overflow-wrap: anywhere;
}

.suggestion-chip__arrow {
  flex: 0 0 14px;
  width: 14px;
  height: 14px;
  color: var(--text-secondary, var(--chat-text-secondary));
  transition: color 0.16s ease;
}

.suggestion-chip:not(:disabled):hover .suggestion-chip__arrow { color: var(--chat-accent); }

@media (max-width: 767px) {
  .suggestion-chips { padding: var(--space-md, 12px); }
}

@media (prefers-reduced-motion: reduce) {
  .suggestion-chip, .suggestion-chip__arrow { transition: none; }
}
</style>
