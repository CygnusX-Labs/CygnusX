<script setup lang="ts">
import { ref, computed } from 'vue'
import { NAvatar, NButton, NIcon, NTag, NCollapseTransition } from 'naive-ui'
import {
  SparklesOutline,
  ChevronForwardOutline,
  CopyOutline,
  RefreshOutline,
  ThumbsUpOutline,
  ThumbsDownOutline,
  DocumentOutline,
  BuildOutline,
} from '@vicons/ionicons5'
import md, { VChart } from './setup'
import type { ChatMessage } from './types'

interface Props {
  message: ChatMessage
  isStreaming?: boolean
  streamingContent?: string
  streamingThought?: string
  userAvatar?: string
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false,
  streamingContent: '',
  streamingThought: '',
  userAvatar: '',
})

const emit = defineEmits<{
  feedback: [messageId: string, type: 'like' | 'dislike']
  copyMessage: [content: string]
  retry: [messageId: string]
}>()

const showThought = ref(false)

const thoughtContent = computed(() =>
  props.isStreaming ? props.streamingThought : props.message.thought || ''
)

const renderedContent = computed(() => {
  const c = props.isStreaming ? props.streamingContent : props.message.content
  return c ? md.render(c) : ''
})

function handleBodyClick(e: MouseEvent) {
  const t = (e.target as HTMLElement).closest('.copy-btn') as HTMLElement | null
  if (!t) return
  navigator.clipboard.writeText(decodeURIComponent(t.dataset.code || ''))
  t.textContent = '已复制!'
  setTimeout(() => {
    t.textContent = '复制'
  }, 1500)
}

function handleCopy() {
  navigator.clipboard.writeText(props.message.content)
  emit('copyMessage', props.message.content)
}

function handleRetry() {
  emit('retry', props.message.id)
}

function handleFeedback(type: 'like' | 'dislike') {
  emit('feedback', props.message.id, type)
}
</script>

<template>
  <div class="kimi-message-item" :class="message.role">
    <template v-if="message.role === 'user'">
      <div class="user-message-wrapper">
        <div class="user-bubble">
          <div class="message-content">{{ message.content }}</div>
          <div v-if="message.attachments?.length" class="attachments">
            <div v-for="(file, idx) in message.attachments" :key="idx" class="attachment-tag">
              <n-icon size="14"><DocumentOutline /></n-icon>
              <span>{{ file.name }}</span>
            </div>
          </div>
        </div>
        <div class="user-avatar">
          <n-avatar
            round
            size="small"
            :src="userAvatar"
            fallback-src="https://api.dicebear.com/7.x/avataaars/svg?seed=user"
          />
        </div>
      </div>
    </template>

    <template v-else-if="message.role === 'assistant'">
      <div class="ai-message-wrapper">
        <div class="ai-avatar">
          <n-avatar round size="small" :style="{ background: 'var(--chat-accent)' }">
            <n-icon size="16"><SparklesOutline /></n-icon>
          </n-avatar>
        </div>
        <div class="ai-content">
          <div class="ai-name">OmicHub AI</div>

          <div v-if="thoughtContent" class="thought-section">
            <div class="thought-toggle" @click="showThought = !showThought">
              <n-icon size="14" class="toggle-icon" :class="{ expanded: showThought }">
                <ChevronForwardOutline />
              </n-icon>
              <span class="thought-label">思考过程</span>
              <n-tag size="small" :bordered="false" type="info" class="thought-status">
                {{ isStreaming ? '思考中...' : '已完成' }}
              </n-tag>
            </div>
            <n-collapse-transition>
              <div v-show="showThought" class="thought-content">
                <pre>{{ thoughtContent }}</pre>
              </div>
            </n-collapse-transition>
          </div>

          <div class="message-body markdown-body" v-html="renderedContent" @click="handleBodyClick" />

          <div v-if="message.toolCalls?.length" class="tool-results">
            <div v-for="(tool, idx) in message.toolCalls" :key="idx" class="tool-card">
              <div class="tool-header">
                <n-icon size="16"><BuildOutline /></n-icon>
                <span>{{ tool.name }}</span>
              </div>
              <div class="tool-content">
                <pre>{{ JSON.stringify(tool.result, null, 2) }}</pre>
              </div>
            </div>
          </div>

          <div v-if="message.charts?.length" class="chart-results">
            <div v-for="(chart, idx) in message.charts" :key="idx" class="chart-container">
              <VChart :option="chart.option" autoresize style="height: 300px" />
            </div>
          </div>

          <div class="message-actions">
            <n-button text size="tiny" class="action-btn" @click="handleCopy">
              <template #icon><n-icon size="14"><CopyOutline /></n-icon></template>
              复制
            </n-button>
            <n-button v-if="false" text size="tiny" class="action-btn" @click="handleRetry">
              <template #icon><n-icon size="14"><RefreshOutline /></n-icon></template>
              重试
            </n-button>
            <n-button text size="tiny" class="action-btn" @click="handleFeedback('like')">
              <template #icon><n-icon size="14"><ThumbsUpOutline /></n-icon></template>
            </n-button>
            <n-button text size="tiny" class="action-btn" @click="handleFeedback('dislike')">
              <template #icon><n-icon size="14"><ThumbsDownOutline /></n-icon></template>
            </n-button>
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="message.role === 'system'">
      <div class="system-message">
        <span>{{ message.content }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.kimi-message-item {
  margin-bottom: 24px;
}
.kimi-message-item.user .user-message-wrapper {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  gap: 12px;
}
.kimi-message-item.user .user-bubble {
  max-width: 80%;
  padding: 12px 18px;
  background: var(--chat-user-bubble);
  border-radius: 18px 18px 4px 18px;
  color: var(--chat-text-primary);
  font-size: 15px;
  line-height: 1.6;
}
.kimi-message-item.user .message-content {
  white-space: pre-wrap;
  word-break: break-word;
}
.kimi-message-item.user .attachments {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.kimi-message-item.user .attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: rgba(79, 142, 247, 0.1);
  border-radius: 6px;
  font-size: 12px;
  color: var(--chat-accent);
}
.kimi-message-item.user .user-avatar {
  flex-shrink: 0;
}
.kimi-message-item.assistant .ai-message-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.kimi-message-item.assistant .ai-avatar {
  flex-shrink: 0;
  margin-top: 4px;
}
.kimi-message-item.assistant .ai-content {
  flex: 1;
  max-width: calc(100% - 60px);
}
.kimi-message-item.assistant .ai-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--chat-accent);
  margin-bottom: 6px;
}
.kimi-message-item.assistant .message-actions {
  display: flex;
  gap: 4px;
  margin-top: 10px;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.kimi-message-item.assistant:hover .message-actions {
  opacity: 1;
}
.kimi-message-item .system-message {
  text-align: center;
  padding: 8px 0;
  font-size: 13px;
  color: var(--chat-text-muted);
}
</style>
