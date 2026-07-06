<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { NAvatar, NButton, NIcon, NTag, NCollapseTransition } from 'naive-ui'
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
  /** 用户显示名 */
  userName?: string
  /** Agent 显示名 */
  agentName?: string
  /** Agent 头像/emoji */
  agentAvatar?: string
  /** Agent 主题色 */
  agentColor?: string
  modelName?: string
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false,
  streamingContent: '',
  streamingThought: '',
  userAvatar: '',
  userName: '我',
  agentName: 'OmicHub AI',
  agentAvatar: '🤖',
  agentColor: '#4f8ef7',
  modelName: 'AI 助手',
})

const emit = defineEmits<{
  feedback: [messageId: string, type: 'like' | 'dislike']
  copy: [mode: CopyMode]
  regenerate: [messageId: string]
  retryWithModel: [messageId: string]
  translate: [messageId: string]
  delete: [messageId: string]
  edit: [messageId: string]
}>()

const showThought = ref(false)
const hovered = ref(false)
const lottieRef = ref<InstanceType<typeof Vue3Lottie> | null>(null)

// 流式生成态：收到第一个非空字符后渐隐骨架屏
const showSkeleton = ref(true)
const streamingHasContent = computed(() =>
  (props.isStreaming ? props.streamingContent : props.message.content)?.length > 0,
)
watch(streamingHasContent, (hasContent) => {
  if (hasContent) {
    setTimeout(() => {
      showSkeleton.value = false
    }, 300)
  } else {
    showSkeleton.value = true
  }
})

// 思考完成且进入正式生成后，3 秒自动折叠思考面板
watch(
  () => props.isStreaming,
  (streaming, prev) => {
    if (prev && !streaming && thoughtContent.value) {
      // 流结束保持展开，让用户能看思考过程
      return
    }
    if (!streaming || !thoughtContent.value) return
    // 已有思考内容且开始正式生成时，延迟折叠
    if (props.streamingContent.length > 0 && thoughtContent.value.length > 0) {
      setTimeout(() => {
        showThought.value = false
      }, 3000)
    }
  },
)

const lottieUrl = `${import.meta.env.BASE_URL}lottie/ai-avatar.json`

watch(
  () => props.isStreaming,
  (streaming) => {
    lottieRef.value?.setSpeed(streaming ? 2 : 1)
  },
)

const thoughtContent = computed(() =>
  props.isStreaming ? props.streamingThought : props.message.thought || '',
)

const isThinking = computed(() => props.isStreaming && thoughtContent.value.length > 0 && !props.streamingContent.length)

const isError = computed(() => props.message.status === 'error' || (props.message.content?.startsWith('生成失败') ?? false))

const isEmpty = computed(() =>
  !props.isStreaming
  && !props.message.content?.trim().length
  && !props.message.toolCalls?.length
  && !props.message.charts?.length
  && !isError.value,
)

const formattedTime = computed(() => {
  const d = new Date(props.message.createdAt)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

const tokenText = computed(() => {
  const t = props.message.tokens
  if (!t) return ''
  const input = t.input ?? 0
  const output = t.output ?? 0
  const total = t.total ?? input + output
  if (props.message.role === 'assistant') {
    return `Tokens: ${total} ↑${input} ↓${output}`
  }
  return `Tokens: ${total} ↑${input}`
})

const aiIdentityName = computed(() => {
  if (props.message.modelName) return props.message.modelName
  return props.agentName
})

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
function handleEdit() {
  emit('edit', props.message.id)
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
      <div class="message-header user-header">
        <div class="message-meta">
          <span v-if="tokenText" class="meta-item tokens">{{ tokenText }}</span>
          <span v-if="tokenText && formattedTime" class="meta-separator">|</span>
          <span v-if="formattedTime" class="meta-item">{{ formattedTime }}</span>
        </div>
        <div class="message-identity">
          <span class="message-name">{{ userName }}</span>
          <n-avatar
            round
            size="small"
            :src="userAvatar"
            fallback-src="https://api.dicebear.com/7.x/avataaars/svg?seed=user"
            class="message-avatar"
          />
        </div>
      </div>

      <div class="message-content user-bubble">
        {{ message.content }}
        <div v-if="message.attachments?.length" class="attachments">
          <div v-for="(file, idx) in message.attachments" :key="idx" class="attachment-tag">
            <n-icon size="14"><DocumentOutline /></n-icon>
            <span>{{ file.name }}</span>
          </div>
        </div>
      </div>

      <MessageActionBar
        :visible="hovered"
        :is-user="true"
        :content="message.content"
        :model-name="modelName"
        @copy="handleCopy"
        @delete="handleDelete"
        @regenerate="handleRegenerate"
        @edit="handleEdit"
      />
    </template>

    <template v-else-if="message.role === 'assistant'">
      <div class="message-header assistant-header">
        <div class="message-identity">
          <div class="ai-avatar">
            <Vue3Lottie
              v-if="agentAvatar === '🤖' || !agentAvatar"
              ref="lottieRef"
              :animation-link="lottieUrl"
              :loop="true"
              :auto-play="true"
              :width="32"
              :height="32"
            />
            <div
              v-else
              class="avatar-fallback"
              :style="{ background: agentColor }"
            >
              {{ agentAvatar }}
            </div>
          </div>
          <span class="message-name ai-name">{{ aiIdentityName }}</span>
        </div>
        <div class="message-meta">
          <span v-if="tokenText" class="meta-item tokens">{{ tokenText }}</span>
          <span v-if="tokenText && formattedTime" class="meta-separator">|</span>
          <span v-if="formattedTime" class="meta-item">{{ formattedTime }}</span>
        </div>
      </div>

      <!-- 生成中纯文本提示：已移除思考过程面板与骨架屏，仅保留静态文字 -->
      <transition name="fade">
        <div
          v-if="isStreaming && showSkeleton && !streamingHasContent && !isError && !isEmpty"
          class="waiting-hint-static"
        >
          星尘正在穿越神经网络，请稍候...
        </div>
      </transition>

      <!-- 空内容 / 错误态 -->
      <div v-if="isError" class="ai-empty-state error">
        <div class="empty-icon">💫</div>
        <div class="empty-title">星尘信号受到了干扰</div>
        <div class="empty-desc">{{ message.content || '生成失败，请稍后重试或切换模型' }}</div>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">🔄 重试</n-button>
          <n-button size="small" @click="handleRetryWithModel">⚙️ 切换模型</n-button>
        </div>
      </div>

      <div v-else-if="isEmpty" class="ai-empty-state">
        <div class="empty-icon">🌌</div>
        <div class="empty-title">这片星域暂时没有回应</div>
        <div class="empty-desc">
          模型似乎返回了空内容，可能是：<br>
          · 当前问题超出了模型的知识边界<br>
          · 网络连接出现波动
        </div>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">🔄 重新生成</n-button>
        </div>
      </div>

      <div v-else class="message-content ai-card" :class="{ 'streaming-active': isStreaming }">
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

        <!-- 流式光标 -->
        <span v-if="isStreaming && streamingHasContent" class="stream-cursor" />
      </div>

      <!-- 错误/空内容态下直接显示操作栏 -->
      <MessageActionBar
        v-if="(isError || isEmpty)"
        :visible="true"
        :is-user="false"
        :content="message.content"
        :model-name="modelName"
        @copy="handleCopy"
        @regenerate="handleRegenerate"
        @retry-with-model="handleRetryWithModel"
        @translate="handleTranslate"
        @delete="handleDelete"
      />
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
  padding: 20px 24px;
  transition: background 0.2s ease;
}
.kimi-message-item:hover {
  background: rgba(0, 0, 0, 0.01);
}

/* 头部：身份 + 元信息 */
.message-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.message-header.user-header {
  flex-direction: row-reverse;
  justify-content: flex-start;
}
.message-header.assistant-header {
  justify-content: flex-start;
}

.message-identity {
  display: flex;
  align-items: center;
  gap: 8px;
}
.message-header.user-header .message-identity {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}
.message-name {
  font-size: 13px;
  font-weight: 600;
}
.ai-name {
  color: var(--chat-accent, #4f8ef7);
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--chat-text-muted, #999);
}
.message-header.user-header .message-meta {
  justify-content: flex-end;
}
.message-header.assistant-header .message-meta {
  justify-content: flex-start;
}
.meta-separator {
  color: var(--chat-border, #ddd);
  font-size: 10px;
}
.meta-item.tokens {
  display: flex;
  align-items: center;
  gap: 4px;
}
.token-arrow {
  font-size: 11px;
  margin-left: 2px;
}
.token-arrow.up {
  color: var(--chat-status-ready, #52c41a);
}
.token-arrow.down {
  color: var(--chat-accent, #1890ff);
}

/* 用户消息气泡（右对齐渐变） */
.kimi-message-item.user {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.kimi-message-item.user .message-content.user-bubble {
  max-width: 80%;
  padding: 12px 16px;
  background: linear-gradient(135deg, #4A6CF7, #6B4B96);
  color: #ffffff;
  border-radius: 16px 16px 4px 16px;
  font-size: 14px;
  line-height: 1.7;
  box-shadow: 0 2px 8px rgba(74, 108, 247, 0.2);
  word-break: break-word;
  white-space: pre-wrap;
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
  background: rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.9);
}

/* AI 消息卡片 */
.kimi-message-item.assistant {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.kimi-message-item.assistant .ai-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}
.kimi-message-item.assistant .avatar-fallback {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
}
.kimi-message-item.assistant .message-content.ai-card {
  position: relative;
  max-width: 90%;
  padding: 16px 20px;
  background: var(--chat-ai-card, #ffffff);
  border: 1px solid var(--chat-border, #f0f0f0);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  font-size: 14px;
  line-height: 1.8;
  color: var(--chat-text-primary, #1a1a1a);
  transition: box-shadow 0.3s ease, border-color 0.3s ease;
}
.kimi-message-item.assistant .message-content.ai-card.streaming-active {
  border-color: rgba(99, 102, 241, 0.45);
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.12),
    0 0 20px rgba(168, 85, 247, 0.12),
    0 0 40px rgba(99, 102, 241, 0.08);
  animation: stream-breathe 2.4s ease-in-out infinite;
}

@keyframes stream-breathe {
  0%, 100% {
    box-shadow:
      0 0 0 1px rgba(99, 102, 241, 0.12),
      0 0 20px rgba(168, 85, 247, 0.10),
      0 0 40px rgba(99, 102, 241, 0.06);
  }
  50% {
    box-shadow:
      0 0 0 1px rgba(99, 102, 241, 0.22),
      0 0 28px rgba(168, 85, 247, 0.18),
      0 0 56px rgba(99, 102, 241, 0.12);
  }
}

/* 流式光标 */
.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 1.2em;
  margin-left: 3px;
  vertical-align: text-bottom;
  background: linear-gradient(180deg, #6366f1, #a855f7);
  border-radius: 2px;
  animation: cursor-blink 1s step-end infinite;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 生成中纯文本提示（替代原骨架屏 + 思考过程面板） */
.waiting-hint-static {
  width: 90%;
  padding: 8px 0;
  font-size: 13px;
  color: var(--chat-text-muted, #86909c);
  line-height: 1.6;
}

/* 空内容 / 错误态 */
.ai-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 90%;
  padding: 28px 20px;
  background: var(--chat-ai-card, #ffffff);
  border: 1px dashed var(--chat-border, #e0e0e0);
  border-radius: 12px;
  text-align: center;
}
.ai-empty-state.error {
  border-style: solid;
  border-color: rgba(208, 48, 80, 0.25);
  background: linear-gradient(180deg, #fff8f9 0%, #ffffff 100%);
}
.empty-icon {
  font-size: 36px;
  margin-bottom: 10px;
  filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.08));
}
.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--chat-text-primary, #1a1a1a);
  margin-bottom: 6px;
}
.empty-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--chat-text-secondary, #666);
  max-width: 420px;
}
.empty-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
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