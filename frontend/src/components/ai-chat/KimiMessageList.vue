<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { ChevronDownOutline } from '@vicons/ionicons5'
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

const listRef = ref<HTMLDivElement>()
const showScrollToBottom = ref(false)

const messagesWithIndex = computed(() => props.messages.map((m, i) => ({ ...m, index: i })))

const streamingMessageId = computed(() => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (lastMsg?.role === 'assistant' && props.isTyping) {
    return lastMsg.id
  }
  return ''
})

function scrollToBottom() {
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

function handleScroll() {
  if (!listRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = listRef.value
  showScrollToBottom.value = scrollHeight - scrollTop - clientHeight > 100
}

watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (!showScrollToBottom.value) scrollToBottom()
    })
  }
)

watch(
  () => props.streamingContent,
  () => {
    nextTick(() => {
      if (!showScrollToBottom.value) scrollToBottom()
    })
  }
)

onMounted(() => {
  listRef.value?.addEventListener('scroll', handleScroll)
  scrollToBottom()
})

onUnmounted(() => {
  listRef.value?.removeEventListener('scroll', handleScroll)
})
</script>

<template>
  <div ref="listRef" class="kimi-message-list">
    <div class="message-container">
      <transition-group name="message-slide">
        <KimiMessageItem
          v-for="message in messages"
          :key="message.id"
          :message="message"
          :is-streaming="message.id === streamingMessageId"
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
      </transition-group>

      <div v-if="isTyping && !streamingContent" class="typing-indicator">
        <div class="typing-dot" />
        <div class="typing-dot" />
        <div class="typing-dot" />
      </div>
    </div>

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
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px 0;
  position: relative;

  .message-container {
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

.message-slide-enter-active,
.message-slide-leave-active {
  transition: all 0.3s ease;
}
.message-slide-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.message-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
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
