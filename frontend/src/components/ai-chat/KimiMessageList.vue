<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { ChevronDownOutline } from '@vicons/ionicons5'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import KimiMessageItem from './KimiMessageItem.vue'
import type { ChatMessage, CollaborationRouteInfo, CopyMode } from './types'

interface Props {
  messages: ChatMessage[]
  isTyping?: boolean
  streamingContent?: string
  streamingThought?: string
  modelName?: string
  userName?: string
  userAvatar?: string
  agentName?: string
  agentAvatar?: string
  agentColor?: string
  sessionId?: string
  targetMessageId?: string
}

const props = withDefaults(defineProps<Props>(), {
  isTyping: false,
  streamingContent: '',
  streamingThought: '',
  modelName: 'AI 助手',
  userName: '我',
  userAvatar: '',
  agentName: 'OmicHub AI',
  agentAvatar: '🤖',
  agentColor: '#4f8ef7',
  sessionId: '',
  targetMessageId: '',
})

const emit = defineEmits<{
  feedback: [messageId: string, type: 'like' | 'dislike']
  copy: [mode: CopyMode]
  regenerate: [messageId: string]
  retryWithModel: [messageId: string]
  translate: [messageId: string]
  delete: [messageId: string]
  edit: [messageId: string]
  confirmTool: [toolName: string, args: Record<string, unknown>]
  openToolPage: [route: string, args: Record<string, unknown>]
  createCaseFromConsultation: [summary: string, consultationId?: string]
  correctCollaborationRoute: [route: CollaborationRouteInfo]
}>()

interface ScrollerExpose {
  scrollToBottom: () => void
  scrollToItem?: (index: number) => void
}

const scrollerRef = ref<InstanceType<typeof DynamicScroller> & ScrollerExpose>()
/** 用户是否已上翻离开底部（true 时暂停自动跟随，并显示"回到底部"悬浮按钮） */
const showScrollToBottom = ref(false)
/** 暂停吸底期间是否有新内容到达（悬浮按钮上的红点提示） */
const hasNewWhileAway = ref(false)

/** 距底多少像素内视为"接近底部"，自动跟随流式输出 */
const NEAR_BOTTOM_THRESHOLD = 100

const streamingMessageId = computed(() => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (lastMsg?.role === 'assistant' && props.isTyping && !lastMsg.senderAgent) {
    return lastMsg.id
  }
  return ''
})

function getScrollerEl(): HTMLElement | undefined {
  return scrollerRef.value?.$el as HTMLElement | undefined
}

/** 自动跟随滚动的缓动时长（ms）。每个流式 token 会重启该动画，形成连续"缓跟"。 */
const SCROLL_EASE_MS = 220

/** 正在进行的平滑跟随动画句柄；新一轮滚动前先取消，避免叠加抖动。 */
let scrollAnim: number | null = null

function cancelScrollAnim() {
  if (scrollAnim !== null) {
    cancelAnimationFrame(scrollAnim)
    scrollAnim = null
  }
}

/**
 * 平滑跟随到底部。
 * 用 easeOutCubic 把 scrollTop 从当前位置缓动到 scrollHeight，而非每帧硬设：
 * 流式期间每个 token 触发一次调用，新动画读取"当前"scrollTop 向新目标缓动，
 * 视觉上是一条连续、丝滑的跟随曲线，而不是逐 token 的"跳动"。
 * force=true（点击"回到底部" / 新审批 / 澄清事件）时取消缓动并立即贴底。
 */
function scrollToBottom(force = false) {
  if (!force && showScrollToBottom.value) {
    // 用户上滑暂停吸底期间有新内容到达：标记红点，不打断阅读位置
    hasNewWhileAway.value = true
    return
  }
  const el = getScrollerEl()
  if (!el) return
  if (force) {
    showScrollToBottom.value = false
    hasNewWhileAway.value = false
    cancelScrollAnim()
    el.scrollTop = el.scrollHeight
    return
  }
  // 已有跟随动画在跑时直接返回，不重启缓动：
  // 动画每帧重读 scrollHeight 会自动追上持续增长的内容；
  // 若每个 token 都重启动画，缓动曲线反复从 0 开始，速度突变形成肉眼可见的"窗口抖动"。
  if (scrollAnim !== null) return
  smoothScrollTo(el, el.scrollHeight, SCROLL_EASE_MS)
}

/** easeOutCubic 平滑滚动；每帧重读 scrollHeight，自动追上新增内容高度。 */
function smoothScrollTo(el: HTMLElement, target: number, duration: number) {
  cancelScrollAnim()
  const start = el.scrollTop
  const delta = target - start
  if (delta <= 0) return // 已在底部或目标更小，无需移动
  const startTime = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - startTime) / duration)
    const eased = 1 - Math.pow(1 - t, 3)
    // 重读 scrollHeight：流式内容在动画期间仍在增长，目标随之上移，避免"跟不上"
    const currentTarget = el.scrollHeight - el.clientHeight
    el.scrollTop = start + (currentTarget - start) * eased
    if (t < 1) {
      scrollAnim = requestAnimationFrame(step)
    } else {
      scrollAnim = null
    }
  }
  scrollAnim = requestAnimationFrame(step)
}

function scrollToMessage(messageId: string) {
  const index = props.messages.findIndex((m) => m.id === messageId)
  if (index < 0) return
  scrollerRef.value?.scrollToItem?.(index)
}

/** 点击"回到底部"：平滑滚动回底部（scroll-behavior: smooth 由缓动动画实现），并恢复自动吸底。 */
function scrollBackToBottom() {
  const el = getScrollerEl()
  if (!el) return
  showScrollToBottom.value = false
  hasNewWhileAway.value = false
  smoothScrollTo(el, el.scrollHeight, 400)
}

function handleScroll() {
  const el = getScrollerEl()
  if (!el) return
  const { scrollTop, scrollHeight, clientHeight } = el
  const awayFromBottom = scrollHeight - scrollTop - clientHeight > NEAR_BOTTOM_THRESHOLD
  showScrollToBottom.value = awayFromBottom
  // 用户自行滚回底部附近：清除新内容提示，恢复自动跟随
  if (!awayFromBottom) hasNewWhileAway.value = false
}

defineExpose({ scrollToBottom, scrollToMessage })

watch(
  () => props.messages.length,
  () => {
    nextTick(() => scrollToBottom())
  },
)

watch(
  () => [props.streamingContent, props.streamingThought],
  () => {
    nextTick(() => scrollToBottom())
  },
)

watch(
  () => [props.targetMessageId, props.messages.length] as const,
  ([messageId]) => {
    if (!messageId) return
    nextTick(() => scrollToMessage(messageId))
  },
)

onMounted(() => {
  const el = scrollerRef.value?.$el as HTMLElement | undefined
  el?.addEventListener('scroll', handleScroll)
  scrollToBottom()
})

onUnmounted(() => {
  cancelScrollAnim()
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
            JSON.stringify(item.tokens),
            JSON.stringify(item.toolCalls),
            JSON.stringify(item.charts),
            JSON.stringify(item.routedAgent),
            JSON.stringify(item.collaborationRoute),
            streamingMessageId === item.id ? streamingContent : '',
            streamingMessageId === item.id ? streamingThought : '',
          ]"
          :data-index="index"
          :class="{ 'message-target': targetMessageId === item.id }"
        >
          <KimiMessageItem
            :message="item"
            :is-streaming="item.id === streamingMessageId"
            :streaming-content="streamingContent"
            :streaming-thought="streamingThought"
            :model-name="modelName"
            :user-name="userName"
            :user-avatar="userAvatar"
            :agent-name="agentName"
            :agent-avatar="agentAvatar"
            :agent-color="agentColor"
            :session-id="sessionId"
            @feedback="(id, type) => emit('feedback', id, type)"
            @copy="(mode) => emit('copy', mode)"
            @regenerate="(id) => emit('regenerate', id)"
            @retry-with-model="(id) => emit('retryWithModel', id)"
            @translate="(id) => emit('translate', id)"
            @delete="(id) => emit('delete', id)"
            @edit="(id) => emit('edit', id)"
            @confirm-tool="(toolName, args) => emit('confirmTool', toolName, args)"
            @open-tool-page="(route, args) => emit('openToolPage', route, args)"
            @create-case-from-consultation="(summary, consultationId) => emit('createCaseFromConsultation', summary, consultationId)"
            @correct-collaboration-route="(route) => emit('correctCollaborationRoute', route)"
          />
        </DynamicScrollerItem>
      </template>

    </DynamicScroller>

    <transition name="fade">
      <n-button
        v-if="showScrollToBottom"
        circle
        class="scroll-to-bottom"
        :title="hasNewWhileAway ? '有新消息，回到底部' : '回到底部'"
        @click="scrollBackToBottom"
      >
        <template #icon>
          <n-icon><ChevronDownOutline /></n-icon>
        </template>
        <span v-if="hasNewWhileAway" class="new-message-dot" aria-label="有新消息" />
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
    /* 预留滚动条位置：流式期间内容高度反复跨过"出现滚动条"临界值时，
       容器宽度不再变化，消除整列内容的水平抖动 */
    scrollbar-gutter: stable;
    scrollbar-width: thin;
    scrollbar-color: rgba(46, 91, 255, 0.2) transparent;
  }

  .message-scroller::-webkit-scrollbar {
    width: 6px;
  }

  .message-scroller::-webkit-scrollbar-track {
    background: transparent;
  }

  .message-scroller::-webkit-scrollbar-thumb {
    background: rgba(46, 91, 255, 0.2);
    border-radius: 999px;
  }

  .message-scroller::-webkit-scrollbar-thumb:hover {
    background: rgba(46, 91, 255, 0.35);
  }

  :deep(.vue-recycle-scroller__item-wrapper) {
    padding: 0 24px;
    max-width: var(--chat-content-max-width, 860px);
    margin: 0 auto;
  }

  :deep(.message-target) {
    animation: messagePulse 1.4s ease;
  }

  /* typing-indicator 跳动点已移除 */

  .scroll-to-bottom {
    position: absolute;
    bottom: 20px;
    right: 40px;
    width: 36px;
    height: 36px;
    background: var(--bg-card);
    border: 1px solid rgba(46, 91, 255, 0.08);
    box-shadow: 0 2px 8px rgba(30, 50, 100, 0.12);
    color: var(--stardust-blue);
    overflow: visible;
  }

  .scroll-to-bottom:hover {
    background: var(--stardust-bg-soft);
    color: var(--stardust-blue);
  }

  /* 暂停吸底期间有新内容到达的红点提示 */
  .new-message-dot {
    position: absolute;
    top: -2px;
    right: -2px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #f5222d;
    border: 2px solid var(--bg-card, #fff);
    box-shadow: 0 1px 3px rgba(245, 34, 45, 0.4);
    pointer-events: none;
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

@keyframes messagePulse {
  0%, 100% { background: transparent; }
  18%, 70% { background: color-mix(in srgb, var(--brand-primary-light, #EEF1FF) 70%, transparent); }
}
</style>
