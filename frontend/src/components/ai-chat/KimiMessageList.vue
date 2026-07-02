<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { ChevronDownOutline } from '@vicons/ionicons5'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import KimiMessageItem from './KimiMessageItem.vue'
import type { ChatMessage, CopyMode } from './types'

interface Props {
  messages: ChatMessage[]
  isTyping?: boolean
  streamingContent?: string
  streamingThought?: string
  modelName?: string
}

const props = withDefaults(defineProps<Props>(), {
  isTyping: false,
  streamingContent: '',
  streamingThought: '',
  modelName: 'AI 助手',
})

const emit = defineEmits<{
  feedback: [messageId: string, type: 'like' | 'dislike']
  copy: [mode: CopyMode]
  regenerate: [messageId: string]
  retryWithModel: [messageId: string]
  translate: [messageId: string]
  delete: [messageId: string]
}>()

interface ScrollerExpose {
  scrollToBottom: () => void
}

const scrollerRef = ref<InstanceType<typeof DynamicScroller> & ScrollerExpose>()
const showScrollToBottom = ref(false)

const streamingMessageId = computed(() => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (lastMsg?.role === 'assistant' && props.isTyping) {
    return lastMsg.id
  }
  return ''
})

function scrollToBottom() {
  scrollerRef.value?.scrollToBottom()
}

function handleScroll() {
  const el = scrollerRef.value?.$el as HTMLElement | undefined
  if (!el) return
  const { scrollTop, scrollHeight, clientHeight } = el
  showScrollToBottom.value = scrollHeight - scrollTop - clientHeight > 100
}

watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (!showScrollToBottom.value) scrollToBottom()
    })
  },
)

watch(
  () => props.streamingContent,
  () => {
    nextTick(() => {
      if (!showScrollToBottom.value) scrollToBottom()
    })
  },
)

onMounted(() => {
  const el = scrollerRef.value?.$el as HTMLElement | undefined
  el?.addEventListener('scroll', handleScroll)
  scrollToBottom()
})

onUnmounted(() => {
  const el = scrollerRef.value?.$el as HTMLElement | undefined
  el?.removeEventListener('scroll', handleScroll)
})
</script>

<template>
  <div class="kimi-message-list">
    <DynamicScroller
      ref="scrollerRef"
      :items="messages"
      :min-item-size="80"
      key-field="id"
      class="message-scroller"
    >
      <template #default="{ item, index, active }">
        <DynamicScrollerItem
          :item="item"
          :active="active"
          :size-dependencies="[
            item.content,
            item.thought,
            streamingMessageId === item.id ? streamingContent : '',
            streamingMessageId === item.id ? streamingThought : '',
          ]"
          :data-index="index"
        >
          <KimiMessageItem
            :message="item"
            :is-streaming="item.id === streamingMessageId"
            :streaming-content="streamingContent"
            :streaming-thought="streamingThought"
            :model-name="modelName"
            @feedback="(id, type) => emit('feedback', id, type)"
            @copy="(mode) => emit('copy', mode)"
            @regenerate="(id) => emit('regenerate', id)"
            @retry-with-model="(id) => emit('retryWithModel', id)"
            @translate="(id) => emit('translate', id)"
            @delete="(id) => emit('delete', id)"
          />
        </DynamicScrollerItem>
      </template>

      <template #after>
        <div v-if="isTyping && !streamingContent" class="typing-indicator">
          <div class="typing-dot" />
          <div class="typing-dot" />
          <div class="typing-dot" />
        </div>
      </template>
    </DynamicScroller>

    <transition name="fade">
      <n-button v-if="showScrollToBottom" circle class="scroll-to-bottom" @click="scrollToBottom">
        <template #icon>
          <n-icon><ChevronDownOutline /></n-icon>
        </template>
      </n-button>
    </transition>
  </div>
</template>

<style scoped lang="scss">
.kimi-message-list {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;

  .message-scroller {
    height: 100%;
    padding: 16px 0;
  }

  :deep(.vue-recycle-scroller__item-wrapper) {
    padding: 0 24px;
    max-width: 900px;
    margin: 0 auto;
  }

  .typing-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 16px 20px;
    margin-left: 48px;

    .typing-dot {
      width: 8px;
      height: 8px;
      background: var(--chat-text-muted);
      border-radius: 50%;
      animation: typingBounce 1.4s ease-in-out infinite;
    }

    .typing-dot:nth-child(2) {
      animation-delay: 0.2s;
    }

    .typing-dot:nth-child(3) {
      animation-delay: 0.4s;
    }
  }

  .scroll-to-bottom {
    position: absolute;
    bottom: 20px;
    right: 40px;
    background: var(--chat-surface);
    border: 1px solid var(--chat-border);
    color: var(--chat-text-secondary);
  }

  .scroll-to-bottom:hover {
    background: var(--chat-surface-hover);
    color: var(--chat-text-primary);
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes typingBounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-6px);
  }
}
</style>
