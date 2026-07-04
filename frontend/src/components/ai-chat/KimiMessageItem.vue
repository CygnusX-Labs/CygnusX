<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { NAvatar, NIcon, NTag, NCollapseTransition } from 'naive-ui'
import {
  ChevronForwardOutline,
  DocumentOutline,
  BuildOutline,
} from '@vicons/ionicons5'
import { Vue3Lottie } from 'vue3-lottie'
import md, { VChart } from './setup'
import { usePyodide } from '@/composables/usePyodide'
import MessageActionBar from './MessageActionBar.vue'
import type { ChatMessage, CopyMode } from './types'

interface Props {
  message: ChatMessage
  isStreaming?: boolean
  streamingContent?: string
  streamingThought?: string
  userAvatar?: string
  modelName?: string
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false,
  streamingContent: '',
  streamingThought: '',
  userAvatar: '',
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

const showThought = ref(false)
const hovered = ref(false)
const lottieRef = ref<InstanceType<typeof Vue3Lottie> | null>(null)

const lottieUrl = `${import.meta.env.BASE_URL}lottie/ai-avatar.json`

watch(
  () => props.isStreaming,
  (streaming) => {
    lottieRef.value?.setSpeed(streaming ? 2 : 1)
  },
)

const thoughtContent = computed(() =>
  props.isStreaming ? props.streamingThought : props.message.thought || ''
)

const renderedContent = ref('')
let renderRafId: number | null = null

function renderMarkdown(source: string) {
  renderedContent.value = source ? md.render(source) : ''
}

watch(
  () => (props.isStreaming ? props.streamingContent : props.message.content),
  (source) => {
    if (props.isStreaming) {
      // 流式输出高频触发时，通过 requestAnimationFrame 批量渲染，
      // 避免 markdown-it/highlight.js 每收到一个 chunk 都阻塞主线程。
      if (renderRafId) return
      renderRafId = requestAnimationFrame(() => {
        renderMarkdown(props.streamingContent)
        renderRafId = null
      })
    } else {
      renderMarkdown(source || '')
    }
  },
  { immediate: true },
)

// 组件卸载时取消未执行的渲染帧
onUnmounted(() => {
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }
})

const { execute } = usePyodide()

function handleBodyClick(e: MouseEvent) {
  const t = (e.target as HTMLElement).closest('.copy-btn') as HTMLElement | null
  if (t) {
    navigator.clipboard.writeText(decodeURIComponent(t.dataset.code || ''))
    t.textContent = '已复制!'
    setTimeout(() => {
      t.textContent = '复制'
    }, 1500)
    return
  }

  const runBtn = (e.target as HTMLElement).closest('.run-btn') as HTMLElement | null
  if (runBtn) {
    const code = decodeURIComponent(runBtn.dataset.code || '')
    if (!code) return
    runBtn.textContent = '运行中...'
    runBtn.setAttribute('disabled', 'true')
    execute(code).then((res) => {
      runBtn.textContent = '▶ 运行'
      runBtn.removeAttribute('disabled')
      // 在当前 pre 后插入结果面板
      const pre = runBtn.closest('pre')
      if (!pre) return
      let resultPanel = pre.nextElementSibling as HTMLElement | null
      if (!resultPanel || !resultPanel.classList.contains('execution-result')) {
        resultPanel = document.createElement('div')
        resultPanel.className = 'execution-result'
        pre.parentNode?.insertBefore(resultPanel, pre.nextSibling)
      }
      const outputHtml = res.error
        ? `<div class="exec-error">${escapeHtml(res.error)}</div>`
        : `<pre class="exec-output">${escapeHtml(res.output || '（无输出）')}</pre>`
      const imagesHtml = res.images.map((img) => `<img src="${img}" class="exec-image" />`).join('')
      resultPanel.innerHTML = outputHtml + imagesHtml
    })
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function handleCopy(mode: CopyMode) {
  emit('copy', mode)
}
function handleRegenerate() {
  emit('regenerate', props.message.id)
}
function handleRetryWithModel() {
  emit('retryWithModel', props.message.id)
}
function handleTranslate() {
  emit('translate', props.message.id)
}
function handleDelete() {
  emit('delete', props.message.id)
}
</script>

<template>
  <div
    class="kimi-message-item"
    :class="message.role"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
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
          <MessageActionBar
            :visible="hovered"
            :is-user="true"
            :content="message.content"
            @delete="handleDelete"
          />
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
          <Vue3Lottie
            ref="lottieRef"
            :animation-link="lottieUrl"
            :loop="true"
            :auto-play="true"
            :width="40"
            :height="40"
          />
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

          <MessageActionBar
            v-if="!isStreaming"
            :visible="hovered"
            :is-user="false"
            :content="message.content"
            :model-name="modelName"
            @copy="handleCopy"
            @regenerate="handleRegenerate"
            @retry-with-model="handleRetryWithModel"
            @translate="handleTranslate"
            @delete="handleDelete"
          />
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
  width: 40px;
  height: 40px;
  margin-top: 2px;
  border-radius: 50%;
  overflow: hidden;
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
.kimi-message-item .system-message {
  text-align: center;
  padding: 8px 0;
  font-size: 13px;
  color: var(--chat-text-muted);
}

:deep(.code-header) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--chat-surface, #f5f5f5);
  border-bottom: 1px solid var(--chat-border);
  font-size: 12px;
}

:deep(.code-lang) {
  color: var(--chat-text-muted);
  text-transform: uppercase;
  margin-right: auto;
}

:deep(.copy-btn),
:deep(.run-btn) {
  background: transparent;
  border: 1px solid var(--chat-border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  color: var(--chat-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

:deep(.copy-btn:hover),
:deep(.run-btn:hover) {
  color: var(--chat-accent);
  border-color: var(--chat-accent);
}

:deep(.run-btn:disabled) {
  opacity: 0.6;
  cursor: not-allowed;
}

:deep(.execution-result) {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--chat-surface-hover, rgba(0,0,0,0.03));
  border-radius: 6px;
  font-size: 13px;
}

:deep(.exec-output) {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: monospace;
}

:deep(.exec-error) {
  color: var(--chat-error, #d03050);
  white-space: pre-wrap;
}

:deep(.exec-image) {
  max-width: 100%;
  margin-top: 8px;
  border-radius: 4px;
}
</style>
