<script setup lang="ts">
/**
 * 建议追问 Chips（Suggested Follow-ups）。
 * 渲染在 assistant 回复气泡/产物卡片下方的一行可点击胶囊：
 * - action='send'：emit('send', prompt)，由页面侧走与输入框相同的发送 action；
 * - action='prefill'：emit('prefill', prompt)，由页面侧写入输入框并聚焦。
 * suggestions 为空时不渲染任何占位；组件独立挂载，出问题一行 v-if 即可隐藏。
 * 可访问性：每个 chip 为原生 button（Tab 聚焦、Enter/Space 触发），带 aria-label；
 * 长 label CSS 截断，完整 prompt 入 title；动画仅 transform/opacity 且 ≤200ms，
 * 尊重 prefers-reduced-motion；窄屏横向滚动并以边缘渐隐遮罩提示可滑动。
 */
import type { SuggestedFollowUp } from '@/utils/nextStepSuggestions'

interface Props {
  suggestions: SuggestedFollowUp[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  send: [prompt: string]
  prefill: [prompt: string]
}>()

function handleClick(item: SuggestedFollowUp) {
  if (item.action === 'prefill') {
    emit('prefill', item.prompt)
  } else {
    emit('send', item.prompt)
  }
}

function chipAriaLabel(item: SuggestedFollowUp): string {
  return item.action === 'prefill'
    ? `建议追问（填入输入框待补充）：${item.prompt}`
    : `建议追问（直接发送）：${item.prompt}`
}
</script>

<template>
  <div v-if="props.suggestions.length" class="suggestion-chips" role="group" aria-label="建议追问">
    <button
      v-for="(item, index) in props.suggestions"
      :key="index"
      type="button"
      class="suggestion-chip"
      :class="{ 'is-prefill': item.action === 'prefill' }"
      :title="item.prompt"
      :aria-label="chipAriaLabel(item)"
      @click="handleClick(item)"
    >
      <span class="suggestion-chip__label">{{ item.label }}</span>
      <span v-if="item.action === 'prefill'" class="suggestion-chip__hint" aria-hidden="true">✎</span>
    </button>
  </div>
</template>

<style scoped lang="scss">
.suggestion-chips {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  margin-top: 10px;
  padding-bottom: 2px;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb, rgba(29, 33, 41, 0.15)) transparent;
  animation: suggestion-chips-in 0.18s ease-out both;
  /* 窄屏横向滚动时的边缘渐隐遮罩，提示两侧还有内容可滑 */
  mask-image: linear-gradient(
    to right,
    transparent 0,
    #000 16px,
    #000 calc(100% - 16px),
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0,
    #000 16px,
    #000 calc(100% - 16px),
    transparent 100%
  );
}

.suggestion-chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 260px;
  padding: 5px 12px;
  border: 1px solid var(--stardust-border-soft, rgba(46, 91, 255, 0.08));
  border-radius: 999px;
  background: var(--bg-card, #fff);
  color: var(--stardust-blue, #2e5bff);
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.16s ease, border-color 0.16s ease;
}

.suggestion-chip:hover {
  background: var(--brand-primary-light, #eef1ff);
  border-color: rgba(46, 91, 255, 0.2);
}

.suggestion-chip:focus-visible {
  outline: 2px solid var(--stardust-blue, #2e5bff);
  outline-offset: 1px;
}

/* label 超过约 20 字截断为省略号，完整 prompt 见 button 的 title/aria-label */
.suggestion-chip__label {
  max-width: 20ch;
  overflow: hidden;
  text-overflow: ellipsis;
}

.suggestion-chip__hint {
  font-size: 11px;
  opacity: 0.7;
}

@keyframes suggestion-chips-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .suggestion-chips {
    animation: none;
  }

  .suggestion-chip {
    transition: none;
  }
}
</style>
