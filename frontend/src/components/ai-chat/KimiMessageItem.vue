<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick, inject } from 'vue'
import { NButton, NIcon, NTag, NDataTable } from 'naive-ui'
import {
  DocumentOutline,
  BuildOutline,
} from '@vicons/ionicons5'
import { Vue3Lottie } from 'vue3-lottie'
import { useRouter } from 'vue-router'
import md, { VChart } from './setup'
import { usePyodide } from '@/composables/usePyodide'
import UserAvatar from '@/components/UserAvatar.vue'
import MessageActionBar from './MessageActionBar.vue'
import TaskProgressCard from './TaskProgressCard.vue'
import MasPlanPreviewCard from './MasPlanPreviewCard.vue'
import ChartPreviewModal from './ChartPreviewModal.vue'
import StudioCodeCard from '@/components/studio/StudioCodeCard.vue'
import { StudioContextKey, isStudioCodeTool } from '@/components/studio/context'
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

const starPositions = computed(() => {
  const count = 22
  const positions: Array<{ x: string; y: string; delay: string; size: string; duration: string }> = []
  for (let i = 0; i < count; i++) {
    positions.push({
      x: `${Math.random() * 100}%`,
      y: `${Math.random() * 100}%`,
      delay: `${Math.random() * 3}s`,
      size: `${2 + Math.random() * 4}px`,
      duration: `${3 + Math.random() * 4}s`,
    })
  }
  return positions
})

const isError = computed(() =>
  props.message.status === 'error'
  || (props.message.content?.startsWith('生成失败') ?? false),
)

const isEmptyWithThought = computed(() =>
  !props.isStreaming
  && !props.message.content?.trim().length
  && !!(props.message.thought?.trim().length)
  && !props.message.toolCalls?.length
  && !props.message.charts?.length
  && !isError.value,
)

const isEmpty = computed(() =>
  !props.isStreaming
  && !props.message.content?.trim().length
  && !(props.message.thought?.trim().length)
  && !props.message.toolCalls?.length
  && !props.message.charts?.length
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
  renderedContent.value = source ? md.render(source) : ''
}

watch(
  () => displayContent.value,
  (source) => {
    if (props.isStreaming) {
      if (renderRafId) return
      renderRafId = requestAnimationFrame(() => {
        renderMarkdown(displayContent.value)
        renderRafId = null
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

// Studio 工作台上下文：仅在 /studio 页面被 provide；注入成功时 Studio 代码工具改渲染代码卡片，
// 普通 /ai 聊天无此上下文，渲染分支完全不变。
const studioCtx = inject(StudioContextKey, null)
function isStudioCodeToolCall(tool: ToolCall): boolean {
  return !!studioCtx && isStudioCodeTool(tool.name)
}

function isArtifactRegisterTool(tool: ToolCall): boolean {
  return tool.name === 'artifact_register' && tool.status === 'success' && !!tool.uiPayload?.report_id
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
        <div class="empty-title">思考完成，但未生成正式回复</div>
        <div class="empty-desc">模型完成了推理，但未输出正式回复内容，请重试或切换模型。</div>
        <details class="thought-details">
          <summary class="thought-summary">🔍 查看思考过程</summary>
          <div class="thought-text">{{ message.thought }}</div>
        </details>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">🔄 重新生成</n-button>
          <n-button size="small" @click="handleRetryWithModel">⚙️ 切换模型</n-button>
        </div>
      </div>

      <!-- 完全空内容 -->
      <div v-else-if="isEmpty" class="ai-empty-state">
        <div class="empty-icon">🌌</div>
        <div class="empty-title">这片星域暂时没有回应</div>
        <div class="empty-desc">
          当前模型响应为空，请重新发送或切换模型。<br>
          · 可能是网络连接出现波动<br>
          · 模型在当前上下文中无法生成回复
        </div>
        <div class="empty-actions">
          <n-button size="small" type="primary" @click="handleRegenerate">🔄 重新发送</n-button>
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

        <!-- 星辰动画（等待/思考期循环播放，内容到达后淡出） -->
        <transition name="star-fade">
          <div v-if="showStarAnimation" class="star-animation-bubble">
            <div class="starfield">
              <span
                v-for="i in 22"
                :key="i"
                class="star-particle"
                :style="{
                  '--star-x': starPositions[i - 1].x,
                  '--star-y': starPositions[i - 1].y,
                  '--star-delay': starPositions[i - 1].delay,
                  '--star-size': starPositions[i - 1].size,
                  '--star-duration': starPositions[i - 1].duration,
                }"
              />
            </div>
            <div class="shimmer-bars">
              <div class="shimmer-bar" style="width: 90%" />
              <div class="shimmer-bar" style="width: 75%" />
              <div class="shimmer-bar" style="width: 60%" />
            </div>
            <div class="star-loading-text">
              <span class="star-icon">🌌</span>
              {{ isThinking ? '星尘正在神经网络中推理...' : '星尘正在穿越神经网络...' }}
            </div>
          </div>
        </transition>

        <!-- 内容气泡 -->
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
              <!-- Studio 代码工具（仅工作台页面）：代码卡片，支持编辑/重跑/产物 -->
              <StudioCodeCard v-if="isStudioCodeToolCall(tool)" :tool="tool" />
              <MasPlanPreviewCard
                v-else-if="hasMasPlan(tool)"
                :plan="masPlanFromTool(tool)"
                :context-summary="contextSummaryFromTool(tool)"
                :session-id="stringPayloadValue(tool, 'session_id')"
                :workspace-id="stringPayloadValue(tool, 'workspace_id')"
              />
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
              <div v-else class="tool-card">
              <div class="tool-header">
                <n-icon size="16"><BuildOutline /></n-icon>
                <span>{{ tool.name }}</span>
                <n-tag v-if="tool.mcpServer" size="tiny" type="info" class="server-tag">
                  MCP: {{ tool.mcpServer }}
                </n-tag>
                <n-tag
                  v-if="tool.status"
                  size="tiny"
                  :type="tool.status === 'success' ? 'success' : tool.status === 'error' ? 'error' : 'warning'"
                  class="status-tag"
                >
                  {{ tool.status === 'running' ? '执行中' : tool.status === 'success' ? '成功' : tool.status === 'error' ? '失败' : tool.status }}
                </n-tag>
              </div>
              <div v-if="tool.arguments && Object.keys(tool.arguments).length" class="tool-args">
                <div class="tool-section-title">参数</div>
                <pre>{{ JSON.stringify(tool.arguments, null, 2) }}</pre>
              </div>
              <div class="tool-content">
                <div class="tool-section-title">结果</div>
                <pre>{{ JSON.stringify(tool.result, null, 2) }}</pre>
              </div>

              <!-- 二次确认卡 -->
              <div v-if="tool.uiPayload?.confirm_card" class="confirm-card">
                <div class="confirm-title">⚠️ 需要确认</div>
                <div class="confirm-desc">
                  该操作将执行 {{ tool.name }}，确认后继续？
                </div>
                <div v-if="tool.uiPayload?.args" class="confirm-preview">
                  <pre>{{ JSON.stringify(tool.uiPayload.args, null, 2) }}</pre>
                </div>
                <div class="confirm-actions">
                  <n-button size="small" type="primary" @click="handleConfirmTool(tool.name, tool.arguments)">
                    确认执行
                  </n-button>
                </div>
              </div>

              <!-- open_page 引导卡 -->
              <div v-if="tool.uiPayload?.route" class="open-page-card">
                <div class="open-page-title">🔗 前往工具页</div>
                <div class="open-page-desc">
                  {{ tool.uiPayload.message || `${tool.name} 需要在专用工具页完成` }}
                </div>
                <div class="open-page-actions">
                  <n-button size="small" type="info" @click="handleOpenToolPage(String(tool.uiPayload.route), tool.arguments)">
                    打开 {{ tool.uiPayload.route }}
                  </n-button>
                </div>
              </div>

              <!-- 异步任务进度卡 -->
              <TaskProgressCard
                v-if="tool.uiPayload?.task_id"
                :task-id="String(tool.uiPayload.task_id)"
                :progress-url="tool.uiPayload.progress_url ? String(tool.uiPayload.progress_url) : undefined"
                :result-url="tool.uiPayload.result_url ? String(tool.uiPayload.result_url) : undefined"
                :task-url="tool.uiPayload.task_url ? String(tool.uiPayload.task_url) : undefined"
              />
              </div>
            </template>
          </div>

          <!-- 流式光标 -->
          <span v-if="isStreaming && streamingHasContent" class="stream-cursor" />
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

/* 星辰动画气泡：等待/思考期的循环动画 */
.star-animation-bubble {
  position: relative;
  width: 90%;
  min-height: 140px;
  padding: 18px 22px 12px;
  background: var(--chat-ai-card, #ffffff);
  border: 1px solid var(--chat-border, #f0f0f0);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: star-bubble-enter 0.3s ease;
}
@keyframes star-bubble-enter {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.starfield {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}
.star-particle {
  position: absolute;
  left: var(--star-x);
  top: var(--star-y);
  width: var(--star-size);
  height: var(--star-size);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.8) 0%, rgba(99, 102, 241, 0.4) 50%, transparent 100%);
  box-shadow: 0 0 6px rgba(168, 85, 247, 0.5);
  animation: star-twinkle var(--star-duration) ease-in-out infinite;
  animation-delay: var(--star-delay);
}
@keyframes star-twinkle {
  0%, 100% {
    opacity: 0;
    transform: scale(0.5);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}
:root[data-theme="dark"] .star-particle {
  background: radial-gradient(circle, rgba(168, 85, 247, 0.9) 0%, rgba(99, 102, 241, 0.5) 50%, transparent 100%);
  box-shadow: 0 0 8px rgba(168, 85, 247, 0.7);
}

.shimmer-bars {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 8px;
}
.shimmer-bar {
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    rgba(99, 102, 241, 0.08) 0%,
    rgba(139, 92, 246, 0.18) 50%,
    rgba(99, 102, 241, 0.08) 100%
  );
  background-size: 200% 100%;
  animation: shimmer-flow 1.8s infinite ease-in-out;
}
@keyframes shimmer-flow {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
:root[data-theme="dark"] .shimmer-bar {
  background: linear-gradient(
    90deg,
    rgba(99, 102, 241, 0.14) 0%,
    rgba(139, 92, 246, 0.26) 50%,
    rgba(99, 102, 241, 0.14) 100%
  );
  background-size: 200% 100%;
}

.star-loading-text {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  margin-top: auto;
  padding-bottom: 4px;
  font-size: 12px;
  color: var(--chat-text-muted, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.star-icon {
  display: inline-block;
  margin-right: 6px;
  animation: gentle-pulse 2s infinite ease-in-out;
}
@keyframes gentle-pulse {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}

/* 星辰动画淡出过渡 */
.star-fade-enter-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.star-fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.star-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.star-fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
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

/* 二次确认卡 */
.confirm-card {
  margin-top: 12px;
  padding: 14px;
  background: var(--chat-surface, #fffbe6);
  border: 1px solid #ffe58f;
  border-radius: 8px;
}
.confirm-title {
  font-weight: 600;
  color: #d48806;
  margin-bottom: 6px;
}
.confirm-desc {
  font-size: 13px;
  color: var(--chat-text-secondary, #666);
  margin-bottom: 10px;
}
.confirm-preview {
  margin-bottom: 10px;
  max-height: 160px;
  overflow-y: auto;
}
.confirm-preview pre {
  margin: 0;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.03);
  padding: 8px;
  border-radius: 4px;
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
}

/* open_page 引导卡 */
.open-page-card {
  margin-top: 12px;
  padding: 14px;
  background: var(--chat-surface, #e6f7ff);
  border: 1px solid #91d5ff;
  border-radius: 8px;
}
.open-page-title {
  font-weight: 600;
  color: #096dd9;
  margin-bottom: 6px;
}
.open-page-desc {
  font-size: 13px;
  color: var(--chat-text-secondary, #666);
  margin-bottom: 10px;
}
.open-page-actions {
  display: flex;
  justify-content: flex-end;
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
.tool-card {
  padding: 12px;
  background: var(--chat-surface, #f8f9fa);
  border: 1px solid var(--chat-border, #e8e8e8);
  border-radius: 8px;
}
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--chat-text-primary, #1a1a1a);
}
.server-tag,
.status-tag {
  margin-left: auto;
}
.tool-section-title {
  font-size: 12px;
  color: var(--chat-text-muted, #999);
  margin: 10px 0 6px;
}
.tool-args pre,
.tool-content pre {
  margin: 0;
  padding: 8px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 4px;
  font-size: 12px;
  max-height: 200px;
  overflow-y: auto;
}

/* 响应式：窄屏下星辰动画高度缩减，宽度保持自适应 */
@media (max-width: 640px) {
  .star-animation-bubble {
    width: 100%;
    min-height: 90px;
    padding: 14px 16px 10px;
  }
  .thought-block {
    width: 100%;
  }
  .plotly-container {
    min-height: 280px;
  }
}
</style>
