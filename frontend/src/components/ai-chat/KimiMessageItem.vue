<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick, inject } from 'vue'
import DOMPurify from 'dompurify'
import { NButton, NIcon, NTag, NDataTable } from 'naive-ui'
import {
  DocumentOutline,
} from '@vicons/ionicons5'
import { Vue3Lottie } from 'vue3-lottie'
import { useRouter } from 'vue-router'
import md, { VChart } from './setup'
import { usePyodide } from '@/composables/usePyodide'
import UserAvatar from '@/components/UserAvatar.vue'
import MessageActionBar from './MessageActionBar.vue'
import AiLoading from './AiLoading.vue'
import TaskProgressCard from './TaskProgressCard.vue'
import PipelineTaskCard from './PipelineTaskCard.vue'
import type { PipelineType } from '@/types/pipeline'
import MasPlanPreviewCard from './MasPlanPreviewCard.vue'
import HandoffCard from './HandoffCard.vue'
import ExpertConsultationCard from './ExpertConsultationCard.vue'
import ChartPreviewModal from './ChartPreviewModal.vue'
import StudioCodeCard from '@/components/studio/StudioCodeCard.vue'
import ApprovalCard from './ApprovalCard.vue'
import McpToolCallCard from './McpToolCallCard.vue'
import { StudioContextKey, isStudioCodeTool } from '@/components/studio/context'
import { useAgentHubStore } from '@/stores/agentHub'
import { reportChatDiagnostic } from '@/utils/chatDiagnostics'
import type { MasPlan } from '@/api/mas'
import type { ChatMessage, CopyMode, ChartData, ToolCall } from './types'

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
  confirmTool: [toolName: string, args: Record<string, unknown>]
  openToolPage: [route: string, args: Record<string, unknown>]
}>()

const router = useRouter()

const hovered = ref(false)
const lottieRef = ref<InstanceType<typeof Vue3Lottie> | null>(null)
const thoughtExpanded = ref(false)
const plotlyContainers = ref<Record<string, HTMLDivElement | null>>({})
const plotlyRenderError = ref<string>('')

function extractPlotlyFigure(tool: ToolCall): Record<string, unknown> | undefined {
  // 1. 优先走专用 uiPayload 通道
  const fromUi = tool.uiPayload?.plotly_figure as Record<string, unknown> | undefined
  if (fromUi) return fromUi
  // 2. 兼容 result 里仍包着 ui_payload 的旧/异常封装
  const result = tool.result as Record<string, unknown> | undefined
  if (!result || typeof result !== 'object') return undefined
  const nestedUi = (result.ui_payload as Record<string, unknown> | undefined)
    || (result.uiPayload as Record<string, unknown> | undefined)
  if (nestedUi?.plotly_figure) return nestedUi.plotly_figure as Record<string, unknown>
  // 3. 兜底：result 直接就是 figure
  if (result.data && result.layout) return result
  return undefined
}

// 优先从工具结果的 uiPayload.plotly_figure 取图，fallback 到 message.charts
const plotlyCharts = computed(() => {
  const fromToolCalls: ChartData[] = []
  for (const tool of props.message.toolCalls || []) {
    const figure = extractPlotlyFigure(tool)
    if (figure) {
      fromToolCalls.push({
        id: `tool-plotly-${tool.id}`,
        type: 'plotly',
        option: figure,
      })
    }
  }
  const fromCharts = (props.message.charts || []).filter((c) => c.type === 'plotly')
  return [...fromToolCalls, ...fromCharts]
})

function setPlotlyContainer(chartId: string) {
  return (el: unknown) => {
    if (el) plotlyContainers.value[chartId] = el as HTMLDivElement
  }
}

async function renderPlotlyCharts() {
  if (!plotlyCharts.value.length) return
  plotlyRenderError.value = ''
  try {
    const Plotly = await import('plotly.js-dist-min')
    await nextTick()
    for (const chart of plotlyCharts.value) {
      const el = plotlyContainers.value[chart.id]
      if (!el) continue
      try {
        await Plotly.newPlot(
          el,
          (chart.option.data || []) as Plotly.Data[],
          (chart.option.layout || {}) as Partial<Plotly.Layout>,
          { responsive: true, displayModeBar: true, displaylogo: false },
        )
      } catch (e) {
        el.textContent = `Plotly 渲染失败: ${e instanceof Error ? e.message : String(e)}`
      }
    }
  } catch (e) {
    plotlyRenderError.value = `Plotly 加载失败: ${e instanceof Error ? e.message : String(e)}`
  }
}

watch(() => [props.message.toolCalls, props.message.charts], renderPlotlyCharts, { deep: true })

// 表格数据（取第一个含 table_data 的 tool result）
const tableData = computed(() => {
  const tc = props.message.toolCalls?.find(
    (t) => t.uiPayload && (t.uiPayload.table_data || t.uiPayload.tableData),
  )
  const raw = tc?.uiPayload?.table_data || tc?.uiPayload?.tableData
  if (!raw || !Array.isArray(raw) || !raw.length) return null
  return (raw as Record<string, unknown>[]).map((row, index) => ({
    ...row,
    __omicHubRowKey: `${props.message.id}-${index}`,
  }))
})

const tableColumns = computed(() => {
  if (!tableData.value) return []
  return Object.keys(tableData.value[0])
    .filter((key) => key !== '__omicHubRowKey')
    .map((key) => ({
      title: key,
      key,
      ellipsis: { tooltip: true },
    }))
})

const displayContent = computed(() =>
  props.isStreaming ? props.streamingContent : props.message.content,
)

const displayThought = computed(() =>
  props.isStreaming ? props.streamingThought : props.message.thought || '',
)

const streamingHasContent = computed(() => displayContent.value.length > 0)

const hasThought = computed(() => displayThought.value.length > 0)

const isThinking = computed(() =>
  props.isStreaming && hasThought.value && !streamingHasContent.value,
)

const showStarAnimation = computed(() =>
  props.isStreaming && !streamingHasContent.value,
)

const showThinkingIndicator = computed(() =>
  props.isStreaming && isThinking.value,
)

const isError = computed(() =>
  props.message.status === 'error'
  || (props.message.content?.startsWith('生成失败') ?? false),
)

const hasOutputTokens = computed(() => (props.message.tokens?.output ?? 0) > 0)

const webSources = computed(() => {
  const sources: Array<{ title: string; url: string; snippet: string }> = [
    ...(props.message.webSources || []),
  ]
  for (const tool of props.message.toolCalls || []) {
    if (tool.name !== 'web_search' || !tool.result || typeof tool.result !== 'object') continue
    const result = tool.result as { results?: unknown; result?: { results?: unknown } }
    const resultRows = Array.isArray(result.results) ? result.results : result.result?.results
    if (!Array.isArray(resultRows)) continue
    for (const source of resultRows) {
      if (!source || typeof source !== 'object') continue
      const item = source as Record<string, unknown>
      if (typeof item.title === 'string' && typeof item.url === 'string') {
        sources.push({ title: item.title, url: item.url, snippet: typeof item.snippet === 'string' ? item.snippet : '' })
      }
    }
  }
  return sources.filter((source, index) => sources.findIndex((item) => item.url === source.url) === index)
})

function sourceDomain(url: string): string {
  try { return new URL(url).hostname } catch { return url }
}

function sourceHref(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : ''
  } catch {
    return ''
  }
}

function sourceFavicon(url: string): string {
  const domain = sourceDomain(url)
  return domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32` : ''
}

function hideSourceFavicon(event: Event) {
  ;(event.currentTarget as HTMLImageElement).style.display = 'none'
}

const isEmptyWithThought = computed(() =>
  !props.isStreaming
  && !props.message.content?.trim().length
  && !!(props.message.thought?.trim().length)
  && !props.message.toolCalls?.length
  && !props.message.charts?.length
  && !props.message.askRequest
  && !isError.value,
)

const isEmpty = computed(() =>
  !props.isStreaming
  && !props.message.content?.trim().length
  && !(props.message.thought?.trim().length)
  && !props.message.toolCalls?.length
  && !props.message.charts?.length
  && !props.message.askRequest
  && !isError.value,
)

const formattedTime = computed(() => {
  const d = new Date(props.message.createdAt)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

const lottieUrl = `${import.meta.env.BASE_URL}lottie/ai-avatar.json`

watch(
  () => props.isStreaming,
  (streaming) => {
    lottieRef.value?.setSpeed(streaming ? 2 : 1)
    if (!streaming) {
      thoughtExpanded.value = false
    }
  },
)

const tokenText = computed(() => {
  if (props.message.role !== 'assistant') return ''
  const t = props.message.tokens
  if (!t) return ''
  const input = t.input ?? 0
  const output = t.output ?? 0
  const total = t.total ?? input + output
  if (total <= 0 && input <= 0 && output <= 0) return ''
  return `Tokens: ${total} ↑${input} ↓${output}`
})

const aiIdentityName = computed(() => {
  if (props.message.modelName) return props.message.modelName
  return props.agentName
})

const renderedContent = ref('')
let renderRafId: number | null = null

function renderMarkdown(source: string) {
  if (!source) {
    renderedContent.value = ''
    return
  }
  try {
    const container = document.createElement('div')
    container.innerHTML = DOMPurify.sanitize(md.render(source))
    const sources = webSources.value
    if (sources.length) {
      const nodes: Text[] = []
      const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
      let node = walker.nextNode()
      while (node) {
        const parent = node.parentElement
        if (!parent?.closest('a, code, pre') && /\[(\d+)\]/.test(node.textContent || '')) {
          nodes.push(node as Text)
        }
        node = walker.nextNode()
      }
      for (const textNode of nodes) {
        const fragment = document.createDocumentFragment()
        const value = textNode.textContent || ''
        let cursor = 0
        for (const match of value.matchAll(/\[(\d+)\]/g)) {
          const index = Number(match[1]) - 1
          const sourceItem = sources[index]
          if (!sourceItem || match.index === undefined) continue
          fragment.append(value.slice(cursor, match.index))
          const href = sourceHref(sourceItem.url)
          if (href) {
            const anchor = document.createElement('a')
            anchor.className = 'web-citation'
            anchor.href = href
            anchor.target = '_blank'
            anchor.rel = 'noopener noreferrer'
            anchor.title = sourceItem.snippet || sourceItem.title
            anchor.setAttribute('aria-label', `来源 ${index + 1}：${sourceItem.title}`)
            anchor.textContent = match[0]
            fragment.append(anchor)
          } else {
            fragment.append(match[0])
          }
          cursor = match.index + match[0].length
        }
        fragment.append(value.slice(cursor))
        textNode.replaceWith(fragment)
      }
    }
    renderedContent.value = DOMPurify.sanitize(container.innerHTML)
  } catch (e) {
    reportChatDiagnostic({
      phase: 'markdown-render',
      messageId: props.message.id,
      contentPreview: source.slice(0, 500),
      error: e,
    })
    renderedContent.value = `<p>${escapeHtml(source)}</p>`
  }
}

watch(
  () => [displayContent.value, webSources.value] as const,
  ([source]) => {
    if (props.isStreaming) {
      if (renderRafId) return
      renderRafId = requestAnimationFrame(() => {
        // 先复位句柄再渲染：渲染抛异常时 rAF 不会重排，
        // 不复位会导致后续所有正文更新被 `if (renderRafId) return` 永久吞掉
        renderRafId = null
        renderMarkdown(displayContent.value)
      })
    } else {
      renderMarkdown(source || '')
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }
  if (copyBtnTimer) clearTimeout(copyBtnTimer)
})

const { execute } = usePyodide()

const previewChart = ref<ChartData | null>(null)
const showChartPreview = ref(false)

function openChartPreview(chart: ChartData) {
  previewChart.value = chart
  showChartPreview.value = true
}

function handleConfirmTool(toolName: string, args: Record<string, unknown>) {
  emit('confirmTool', toolName, { ...args, _confirmed: true })
}

function handleOpenToolPage(route: string, args: Record<string, unknown>) {
  if (route.startsWith('/')) {
    router.push(route)
  } else {
    emit('openToolPage', route, args)
  }
}

const confirmToolCalls = computed(() =>
  (props.message.toolCalls || []).filter(
    (t) => t.uiPayload?.confirm_card === true,
  ),
)

const openPageToolCalls = computed(() =>
  (props.message.toolCalls || []).filter(
    (t) => t.uiPayload?.route,
  ),
)

const taskToolCalls = computed(() =>
  (props.message.toolCalls || []).filter(
    (t) => t.uiPayload?.task_id,
  ),
)

function isPipelineTask(tool: ToolCall): boolean {
  return ['rna_seq', 'atac_seq'].includes(String(tool.uiPayload?.pipeline_type || ''))
}

function pipelineType(tool: ToolCall): PipelineType {
  return String(tool.uiPayload?.pipeline_type) as PipelineType
}

function handlePipelineVisualization(taskId: string, type: PipelineType): void {
  void agentHubStore.sendMessage(
    `请读取 ${type} 任务 ${taskId} 的结果，并为关键质量指标和差异分析结果生成可视化。`,
  )
}

function handleAdjustPipeline(type: PipelineType): void {
  void agentHubStore.sendMessage(`请帮我检查并调整这次 ${type} 分析的参数，然后重新预检。`)
}

// Studio 工作台上下文：仅在 /studio 页面被 provide；注入成功时 Studio 代码工具改渲染代码卡片，
// 普通 /ai 聊天无此上下文，渲染分支完全不变。
const studioCtx = inject(StudioContextKey, null)
const agentHubStore = useAgentHubStore()

/** Studio ask_user 快捷回复：点击即把选项文本作为下一条消息发送 */
const answeringAsk = ref(false)
async function handleAskOption(text: string) {
  if (answeringAsk.value) return
  answeringAsk.value = true
  try {
    await agentHubStore.answerAskRequest(text)
  } finally {
    answeringAsk.value = false
  }
}
function isStudioCodeToolCall(tool: ToolCall): boolean {
  return !!studioCtx && isStudioCodeTool(tool.name)
}

function isArtifactRegisterTool(tool: ToolCall): boolean {
  return tool.name === 'artifact_register' && tool.status === 'success' && !!tool.uiPayload?.report_id
}

function isHandoffTool(tool: ToolCall): boolean {
  return tool.name === 'transfer_to_agent' && tool.status === 'success'
}

function hasMasPlan(tool: ToolCall): boolean {
  const plan = tool.uiPayload?.mas_plan
  return !!plan && typeof plan === 'object' && Array.isArray((plan as MasPlan).nodes)
}

function masPlanFromTool(tool: ToolCall): MasPlan {
  return tool.uiPayload?.mas_plan as MasPlan
}

function contextSummaryFromTool(tool: ToolCall): Record<string, unknown> | undefined {
  const summary = tool.uiPayload?.context_summary
  return summary && typeof summary === 'object' ? summary as Record<string, unknown> : undefined
}

function stringPayloadValue(tool: ToolCall, key: string): string | undefined {
  const value = tool.uiPayload?.[key]
  return value === undefined || value === null ? undefined : String(value)
}

let copyBtnTimer: ReturnType<typeof setTimeout> | null = null

function handleBodyClick(e: MouseEvent) {
  const t = (e.target as HTMLElement).closest('.copy-btn') as HTMLElement | null
  if (t) {
    navigator.clipboard.writeText(decodeURIComponent(t.dataset.code || ''))
    t.textContent = '已复制!'
    if (copyBtnTimer) clearTimeout(copyBtnTimer)
    copyBtnTimer = setTimeout(() => {
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
          <UserAvatar
            :nickname="userName"
            :src="userAvatar"
            :size="28"
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
          <span
            v-if="message.routedAgent"
            class="routed-agent-badge"
            :style="{ borderColor: message.routedAgent.color || undefined }"
            :title="message.routedAgent.reason || '由该专家回答'"
          >
            <span class="routed-agent-avatar">{{ message.routedAgent.avatar }}</span>
            <span class="routed-agent-name">{{ message.routedAgent.name }}</span>
          </span>
          <transition name="fade">
            <span v-if="showThinkingIndicator" class="thinking-badge">✨ 思考中...</span>
          </transition>
        </div>
        <div class="message-meta">
          <span v-if="tokenText" class="meta-item tokens">{{ tokenText }}</span>
          <span v-if="tokenText && formattedTime" class="meta-separator">|</span>
          <span v-if="formattedTime" class="meta-item">{{ formattedTime }}</span>
        </div>
      </div>

      <!-- 错误态 -->
      <div v-if="isError" class="ai-empty-state error">
        <div class="empty-icon">💫</div>
        <div class="empty-title">星尘信号受到了干扰</div>
        <div class="empty-desc">{{ message.content || '生成失败，请稍后重试或切换模型' }}</div>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">🔄 重试</n-button>
          <n-button size="small" @click="handleRetryWithModel">⚙️ 切换模型</n-button>
        </div>
      </div>

      <!-- 空内容但有思考过程 -->
      <div v-else-if="isEmptyWithThought" class="ai-empty-state">
        <div class="empty-icon">💭</div>
        <div class="empty-title">
          {{ hasOutputTokens ? '回复内容加载异常' : '思考完成，但未生成正式回复' }}
        </div>
        <div v-if="message.finishReason === 'length'" class="empty-desc">
          模型的思考过程已耗尽 max_tokens 输出预算（finish_reason=length），未能输出正文。<br>
          请在「系统设置 → AI 模型配置」中调大该模型的 max_tokens 后重新发送。
        </div>
        <div v-else-if="hasOutputTokens" class="empty-desc">
          已收到模型的 Token 用量，但正文未能正确加载。问题已记录，请点击重试。
        </div>
        <div v-else class="empty-desc">模型完成了推理，但未输出正式回复内容，请重试或切换模型。</div>
        <details class="thought-details">
          <summary class="thought-summary">🔍 查看思考过程</summary>
          <div class="thought-text">{{ message.thought }}</div>
        </details>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">
            🔄 {{ hasOutputTokens ? '点击重试' : '重新生成' }}
          </n-button>
          <n-button size="small" @click="handleRetryWithModel">⚙️ 切换模型</n-button>
        </div>
      </div>

      <!-- 完全空内容 -->
      <div v-else-if="isEmpty" class="ai-empty-state">
        <div class="empty-icon">🌌</div>
        <div class="empty-title">{{ hasOutputTokens ? '回复内容加载异常' : '这片星域暂时没有回应' }}</div>
        <div v-if="hasOutputTokens" class="empty-desc">
          已收到模型的 Token 用量，但正文未能正确加载。问题已记录，请点击重试。
        </div>
        <div v-else class="empty-desc">
          当前模型响应为空，请重新发送或切换模型。<br>
          · 可能是网络连接出现波动<br>
          · 模型在当前上下文中无法生成回复
        </div>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">
            🔄 {{ hasOutputTokens ? '点击重试' : '重新发送' }}
          </n-button>
          <n-button size="small" @click="handleRetryWithModel">⚙️ 切换模型</n-button>
        </div>
      </div>

      <!-- 正常内容区 -->
      <template v-else>
        <!-- 可折叠的思考过程 -->
        <div v-if="hasThought" class="thought-block">
          <button class="thought-toggle" @click="thoughtExpanded = !thoughtExpanded">
            <span v-if="showThinkingIndicator" class="thinking-label">✨ 思考中...</span>
            <span v-else class="thinking-label">🔍 思考过程</span>
            <span class="thought-arrow" :class="{ rotated: thoughtExpanded }">▾</span>
          </button>
          <transition name="thought-expand">
            <div v-show="thoughtExpanded" class="thought-content">
              {{ displayThought }}
            </div>
          </transition>
        </div>

        <div
          v-if="isStreaming && message.webSearchStatus && message.webSearchStatus.status !== 'complete'"
          class="web-search-status"
          role="status"
          aria-live="polite"
        >
          <span aria-hidden="true">🔍</span>
          <span>{{ message.webSearchStatus?.message || (message.webSearchStatus?.status === 'searching' ? `正在联网搜索：${message.webSearchStatus?.query || ''}` : message.webSearchStatus?.status === 'empty' ? '未找到相关网页，继续基于模型知识回答' : '联网搜索失败，继续基于模型知识回答') }}</span>
        </div>

        <!-- 首 Token 前加载态；按等待时长轮换动画与文案。
             不套外层 transition：AiLoading 内部已有 out-in 过渡，外层 leave 过渡
             会在其内部过渡进行时移除节点，触发 Vue parentNode null 崩溃。 -->
        <AiLoading
          v-if="showStarAnimation"
          type="auto"
          :stage="isThinking ? '正在梳理思考过程…' : ''"
        />

        <!-- 内容气泡（常驻元素，不套外层 transition：流式→done 切换时与相邻加载态
             同帧 enter/leave 曾触发 Vue parentNode null 补丁崩溃，导致正文/tokens
             刷新前不渲染）。 -->
        <div v-if="streamingHasContent || !isStreaming" class="message-content ai-card" :class="{ 'streaming-active': isStreaming }">
          <div class="message-body markdown-body" v-html="renderedContent" @click="handleBodyClick" />

          <div v-if="plotlyCharts.length" class="chart-results">
            <div
              v-for="chart in plotlyCharts"
              :key="chart.id"
              class="chart-wrapper"
            >
              <div class="chart-actions">
                <n-button size="tiny" @click="openChartPreview(chart)">🔍 预览</n-button>
              </div>
              <div
                :ref="setPlotlyContainer(chart.id)"
                class="plotly-container"
              />
            </div>
            <div v-if="plotlyRenderError" class="plotly-render-error">{{ plotlyRenderError }}</div>
          </div>

          <div v-if="message.charts?.some((c) => c.type === 'echarts')" class="chart-results">
            <div
              v-for="(chart, idx) in message.charts.filter((c) => c.type === 'echarts')"
              :key="idx"
              class="chart-wrapper"
            >
              <div class="chart-actions">
                <n-button size="tiny" @click="openChartPreview(chart)">🔍 预览</n-button>
              </div>
              <VChart :option="chart.option" autoresize style="height: 300px" />
            </div>
          </div>

          <div v-if="tableData" class="table-results">
            <n-data-table
              :data="tableData"
              :columns="tableColumns"
              :row-key="(row) => String(row.__omicHubRowKey)"
              :max-height="300"
              size="small"
            />
          </div>

          <div v-if="message.toolCalls?.length" class="tool-results">
            <template v-for="(tool, idx) in message.toolCalls" :key="idx">
              <!-- Studio HITL 审批卡片（有 approval 数据时出现，决议后保留终态徽标） -->
              <ApprovalCard v-if="tool.approval" :tool="tool" />
              <!-- Studio 代码工具（仅工作台页面）：代码卡片，支持编辑/重跑/产物 -->
              <StudioCodeCard v-if="isStudioCodeToolCall(tool)" :tool="tool" />
              <MasPlanPreviewCard
                v-else-if="hasMasPlan(tool)"
                :plan="masPlanFromTool(tool)"
                :context-summary="contextSummaryFromTool(tool)"
                :session-id="stringPayloadValue(tool, 'session_id')"
                :workspace-id="stringPayloadValue(tool, 'workspace_id')"
              />
              <HandoffCard v-else-if="isHandoffTool(tool)" :tool="tool" />
              <div v-else-if="isArtifactRegisterTool(tool)" class="artifact-register-card">
                <div class="artifact-register-icon">✓</div>
                <div>
                  <div class="artifact-register-title">
                    已登记为《{{ tool.uiPayload?.title }}》v{{ tool.uiPayload?.version }}
                  </div>
                  <div v-if="tool.uiPayload?.parent_id" class="artifact-register-sub">
                    已挂到原报告版本树
                  </div>
                </div>
              </div>
              <McpToolCallCard
                v-else
                :tool="tool"
                @confirm-tool="handleConfirmTool"
                @open-tool-page="handleOpenToolPage"
                @generate-visualization="handlePipelineVisualization"
                @adjust-parameters="handleAdjustPipeline"
              />
            </template>
          </div>

          <ExpertConsultationCard
            v-if="message.consultation?.experts.length"
            :experts="message.consultation.experts"
          />

          <details v-if="webSources.length" class="web-sources">
            <summary class="web-sources-title">来源（{{ webSources.length }}）</summary>
            <div class="web-source-list">
              <a
                v-for="(source, index) in webSources"
                :key="source.url"
                class="web-source"
                :href="sourceHref(source.url) || undefined"
                target="_blank"
                rel="noopener noreferrer"
                :title="source.snippet"
              >
                <span class="source-index">[{{ index + 1 }}]</span>
                <img
                  v-if="sourceFavicon(source.url)"
                  class="source-favicon"
                  :src="sourceFavicon(source.url)"
                  :alt="`${sourceDomain(source.url)} favicon`"
                  loading="lazy"
                  @error="hideSourceFavicon"
                >
                <span class="source-title">{{ source.title }}</span>
                <span class="source-domain">{{ sourceDomain(source.url) }}</span>
              </a>
            </div>
          </details>

          <!-- 流式光标 -->
          <span v-if="isStreaming && streamingHasContent" class="stream-cursor" />
        </div>

        <!-- Studio ask_user 澄清卡片：问题 + 选项快捷回复（回答后标记已回答） -->
        <div v-if="message.askRequest" class="ask-card" :class="{ answered: message.askRequest.answered }">
          <div class="ask-header">
            <span class="ask-icon">💬</span>
            <span class="ask-title">AI 想确认一下</span>
            <n-tag v-if="message.askRequest.answered" size="tiny" round :bordered="false" type="success">
              已回答
            </n-tag>
          </div>
          <div class="ask-question">{{ message.askRequest.question }}</div>
          <div v-if="!message.askRequest.answered && message.askRequest.options?.length" class="ask-options">
            <n-button
              v-for="opt in message.askRequest.options"
              :key="opt"
              size="small"
              secondary
              type="primary"
              :loading="answeringAsk"
              @click="handleAskOption(opt)"
            >
              {{ opt }}
            </n-button>
          </div>
          <div v-else-if="!message.askRequest.answered" class="ask-hint">请在下方输入框回答</div>
        </div>
      </template>

      <!-- 错误/空内容态下直接显示操作栏 -->
      <MessageActionBar
        v-if="(isError || isEmpty || isEmptyWithThought)"
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

    <ChartPreviewModal v-model:show="showChartPreview" :chart="previewChart" />
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

.thinking-badge {
  font-size: 12px;
  color: var(--chat-accent, #4f8ef7);
  opacity: 0.7;
  animation: thinking-pulse 2s ease-in-out infinite;
  white-space: nowrap;
}

/* 智能路由：当前由哪位专家回答的徽标 */
.routed-agent-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  font-size: 11px;
  line-height: 18px;
  border: 1px solid var(--chat-border, #ddd);
  border-radius: 999px;
  background: var(--chat-bg-soft, rgba(127, 127, 127, 0.08));
  color: var(--chat-text-muted, #666);
  white-space: nowrap;
  cursor: default;
}
.routed-agent-avatar {
  font-size: 12px;
}
.routed-agent-name {
  font-weight: 500;
}
@keyframes thinking-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.9; }
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--chat-text-muted, #999);
}
.web-search-status { display:flex; align-items:center; gap:6px; margin:0 0 12px; color:var(--neutral-text-2); font-size:13px; }
.web-sources { margin-top:16px; padding-top:12px; border-top:1px solid var(--neutral-border); }
.web-sources-title { cursor:pointer; font-size:12px; font-weight:600; color:var(--neutral-text-2); }
.web-source-list { display:flex; flex-direction:column; gap:7px; margin-top:9px; }
.web-source { display:flex; align-items:center; gap:7px; min-width:0; font-size:12px; text-decoration:none; color:var(--neutral-text-2); }
.web-source:hover .source-title, .web-citation:hover { color:var(--arco-primary); text-decoration:underline; }
.source-index { flex:0 0 auto; color:var(--arco-primary); }
.source-favicon { width:14px; height:14px; flex:0 0 auto; border-radius:3px; }
.source-title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.source-domain { margin-left:auto; flex:0 0 auto; color:var(--neutral-text-3); font-size:11px; }
:deep(.web-citation) { color:var(--arco-primary); font-weight:600; text-decoration:none; }
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
  max-width: 70%;
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
  width: 100%;
  box-sizing: border-box;
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

/* Markdown 表格和代码块横向滚动 */
.kimi-message-item.assistant :deep(.markdown-body table),
.kimi-message-item.assistant :deep(.markdown-body pre) {
  overflow-x: auto;
  min-width: 320px;
  max-width: 100%;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.content-swap-enter-active,
.content-swap-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.content-swap-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.content-swap-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (prefers-reduced-motion: reduce) {
  .content-swap-enter-active,
  .content-swap-leave-active,
  .stream-cursor,
  .kimi-message-item.assistant .message-content.ai-card.streaming-active {
    animation: none;
    transition: none;
  }
}

/* 思考过程折叠块 */
.thought-block {
  width: 90%;
  margin-bottom: 8px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--chat-border, #f0f0f0);
  background: var(--chat-surface, #f8f9fa);
}
.thought-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--chat-text-secondary, #666);
  transition: background 0.2s ease;
}
.thought-toggle:hover {
  background: var(--chat-surface-hover, rgba(0, 0, 0, 0.03));
}
.thinking-label {
  color: var(--chat-accent, #4f8ef7);
  opacity: 0.8;
}
.thought-arrow {
  margin-left: auto;
  font-size: 10px;
  transition: transform 0.2s ease;
}
.thought-arrow.rotated {
  transform: rotate(180deg);
}
.thought-content {
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--chat-text-secondary, #666);
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  border-top: 1px solid var(--chat-border, #f0f0f0);
  background: var(--chat-surface, #f8f9fa);
}
:root[data-theme="dark"] .thought-content {
  background: rgba(255, 255, 255, 0.03);
}
.thought-expand-enter-active,
.thought-expand-leave-active {
  transition: opacity 0.2s ease, max-height 0.3s ease;
}
.thought-expand-enter-from,
.thought-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

/* 空内容态中的思考过程详情 */
.thought-details {
  width: 100%;
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--chat-border, #e0e0e0);
}
.thought-summary {
  padding: 8px 14px;
  font-size: 12px;
  cursor: pointer;
  color: var(--chat-text-secondary, #666);
  background: var(--chat-surface, #f8f9fa);
}
.thought-text {
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--chat-text-secondary, #666);
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 250px;
  overflow-y: auto;
}

/* thinking-badge fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
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

/* 图表结果 */
.chart-results {
  width: 100%;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chart-wrapper {
  position: relative;
  border: 1px solid var(--chat-border, #f0f0f0);
  border-radius: 8px;
  overflow: hidden;
  background: var(--chat-ai-card, #ffffff);
}
.chart-actions {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.chart-wrapper:hover .chart-actions {
  opacity: 1;
}

/* Plotly 图表容器 */
.plotly-container {
  width: 100%;
  min-height: 400px;
}
.plotly-render-error {
  color: var(--chat-error, #d03050);
  font-size: 13px;
  padding: 8px 12px;
  background: var(--chat-surface, #fff8f9);
  border: 1px solid rgba(208, 48, 80, 0.15);
  border-radius: 6px;
}

/* 表格结果 */
.table-results {
  width: 100%;
  margin-top: 12px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--chat-border, #f0f0f0);
}

/* 工具调用结果卡 */
.tool-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}
.artifact-register-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(24, 160, 88, 0.25);
  border-radius: 10px;
  background: rgba(24, 160, 88, 0.08);
}
.artifact-register-icon {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: #18a058;
  font-weight: 700;
}
.artifact-register-title {
  font-size: 13px;
  font-weight: 600;
}
.artifact-register-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--chat-text-muted, #888);
}
/* Studio ask_user 澄清卡片 */
.ask-card {
  width: 90%;
  margin-top: 10px;
  padding: 12px 16px;
  background: var(--chat-ai-card, #ffffff);
  border: 1px solid rgba(99, 102, 241, 0.35);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.ask-card.answered {
  opacity: 0.75;
  border-color: var(--chat-border, #e5e7eb);
}
.ask-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.ask-icon { font-size: 14px; }
.ask-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--chat-accent, #4f8ef7);
}
.ask-question {
  font-size: 14px;
  line-height: 1.7;
  color: var(--chat-text-primary, #1a1a1a);
  white-space: pre-wrap;
  word-break: break-word;
}
.ask-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.ask-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--chat-text-muted, #999);
}

@media (max-width: 640px) {
  .thought-block {
    width: 100%;
  }
  .plotly-container {
    min-height: 280px;
  }
}

.kimi-message-item {
  padding-block: 24px;
}

.kimi-message-item.assistant .message-name,
.kimi-message-item.assistant .ai-name {
  color: var(--stardust-blue);
  font-weight: 600;
}

.kimi-message-item.assistant .message-content.ai-card {
  border: 1px solid rgba(46, 91, 255, 0.06);
  border-radius: var(--radius-card, 12px);
  box-shadow: var(--stardust-card-shadow);
  line-height: 1.75;
}

.kimi-message-item.user .message-content.user-bubble {
  background: var(--stardust-gradient);
  box-shadow: 0 4px 12px rgba(46, 91, 255, 0.2);
}

.kimi-message-item.assistant .thought-block,
.kimi-message-item.assistant .thought-details {
  border-color: rgba(46, 91, 255, 0.08);
  border-radius: 8px;
  background: var(--stardust-bg-soft);
}

.kimi-message-item.assistant .thought-toggle,
.kimi-message-item.assistant .thought-summary {
  background: var(--stardust-bg-soft);
  color: var(--stardust-blue);
}

.kimi-message-item.assistant :deep(.markdown-body table) {
  overflow: hidden;
  border: 1px solid rgba(46, 91, 255, 0.08);
  border-radius: 8px;
  border-collapse: separate;
  border-spacing: 0;
}

.kimi-message-item.assistant :deep(.markdown-body th) {
  background: var(--stardust-bg-soft);
  color: #3b4262;
  font-weight: 600;
}

.kimi-message-item.assistant :deep(.markdown-body th),
.kimi-message-item.assistant :deep(.markdown-body td) {
  padding: 12px 16px;
  min-height: 48px;
}

.kimi-message-item.assistant :deep(.markdown-body tbody tr:hover) {
  background: #f8f9ff;
}

:root[data-theme="dark"] .kimi-message-item.assistant :deep(.markdown-body th) {
  color: var(--text-primary);
}
:root[data-theme="dark"] .kimi-message-item.assistant :deep(.markdown-body tbody tr:hover) {
  background: rgba(118, 145, 255, 0.08);
}
</style>
