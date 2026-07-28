<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NSelect, NTag, NTooltip, useMessage, useDialog } from 'naive-ui'
import { ArrowBackOutline, BulbOutline, FlashOutline, CloseOutline, DesktopOutline } from '@vicons/ionicons5'
import KimiMessageList from '@/components/ai-chat/KimiMessageList.vue'
import KimiChatInput from '@/components/ai-chat/KimiChatInput.vue'
import AgentCapabilityDrawer from './AgentCapabilityDrawer.vue'
import ShaniaChatBackground from './ShaniaChatBackground.vue'
import { useAgentHubStore } from '@/stores/agentHub'
import { useAuthStore } from '@/stores/auth'
import { studioApi } from '@/api/studio'
import type { FileAttachment } from '@/components/ai-chat/types'

const store = useAgentHubStore()
const authStore = useAuthStore()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

// 助手要求用户提供数据时，弹窗提醒上传/指定数据文件
watch(
  () => store.dataRequestNotice,
  (notice) => {
    if (!notice) return
    store.dataRequestNotice = null
    dialog.warning({
      title: '需要提供数据',
      content: notice.text.length > 600 ? `${notice.text.slice(0, 600)}…` : notice.text,
      positiveText: '知道了',
    })
  },
)

// 工具调用轮次触顶时，弹窗询问是否以扩展上限（1000 轮）继续执行
watch(
  () => store.roundLimitPrompt,
  (prompt) => {
    if (!prompt) return
    store.roundLimitPrompt = null
    dialog.warning({
      title: '工具调用轮次已达上限',
      content: `本次任务已连续调用工具 ${prompt.maxRounds} 轮仍未完成，已暂停。是否以扩展上限（1000 轮）继续执行？`,
      positiveText: '继续（扩展到 1000 轮）',
      negativeText: '不继续',
      onPositiveClick: () => {
        void store.sendMessage('请继续完成刚才未完成的任务', { extendMaxRounds: true })
      },
    })
  },
)

// 上下文超窗触发历史压缩时，轻提示用户早期对话已被压缩为摘要
watch(
  () => store.contextCompressedNotice,
  (tokens) => {
    if (tokens == null) return
    store.contextCompressedNotice = null
    const approx = tokens >= 10000 ? `${Math.round(tokens / 10000)}万` : String(tokens)
    message.info(`对话历史较长（约 ${approx} tokens），已将早期内容压缩为摘要后继续`)
  },
)

// 路由/交接命中默认工作台的 Agent（如代码助手）时，本轮回答结束后自动进入其 AI 工作台
watch(
  () => store.studioRedirect,
  async (target) => {
    if (!target) return
    store.studioRedirect = null
    // 等当前流式回答结束再跳转，避免打断正在输出的内容
    while (store.isStreaming) {
      await new Promise((resolve) => setTimeout(resolve, 300))
    }
    try {
      // 优先把当前会话就地升级为工作台（历史消息完整保留）；
      // 会话尚未落库（sess- 临时 ID）或升级失败时，回退为新建工作台会话
      const sid = store.currentSessionId
      let sessionId = ''
      if (sid && !sid.startsWith('sess-')) {
        try {
          const promoted = await studioApi.promoteSession(sid, target.agentId)
          sessionId = promoted.session_id
        } catch {
          sessionId = ''
        }
      }
      if (!sessionId) {
        const created = await studioApi.createSession({ agent_id: target.agentId })
        sessionId = created.session_id
      }
      store.markStudioSession(sessionId)
      message.info(`已为「${target.agentName}」开启 AI 工作台，对话历史已带过去，可继续`)
      router.push({ name: 'studio', params: { sessionId } })
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '进入工作台失败')
    }
  },
)

defineProps<{ targetMessageId?: string }>()

const input = ref('')
const showCap = ref(false)
const modelSwitchNotice = ref('')
const showWelcomeCard = ref(true)
const creatingStudio = ref(false)
let noticeTimer: ReturnType<typeof setTimeout> | null = null

const agent = computed(() => store.currentAgent)
const session = computed(() => store.currentSession)
const engineLabel = computed(() => agent.value?.model_engine || '')
const agentDisplayName = computed(() => agent.value?.features?.router ? '星尘 AI' : agent.value?.name || '星尘 AI')
const quickPrompts = [
  { label: '看看工作区文件', description: '快速了解当前可用的数据资产', prompt: '帮我看看工作区里有哪些数据文件' },
  { label: '开始差异表达分析', description: '从 RNA-seq 结果找到关键变化', prompt: 'RNA-seq 差异表达分析怎么开始' },
  { label: '画一张相关性热图', description: '探索样本之间的整体关系', prompt: '画一个样本间相关性热图' },
  { label: '生成分析报告模板', description: '整理一份可复现的分析记录', prompt: '生成一份可复现的分析报告模板' },
]

const userDisplayName = computed(() =>
  authStore.user?.nickname || authStore.user?.username || '我',
)
const userAvatarUrl = computed(() => authStore.user?.avatar_url || '')

const welcomeStorageKey = computed(() => `agent-welcome-closed:${agent.value?.id || 'global'}`)

onMounted(() => {
  try {
    showWelcomeCard.value = localStorage.getItem(welcomeStorageKey.value) !== 'true'
  } catch {
    showWelcomeCard.value = true
  }
})

const modelOptions = computed(() =>
  store.availableModels.map((m) => ({
    label: m.name,
    value: m.id,
  })),
)

const currentModelId = computed(() => session.value?.model_id || agent.value?.model_id || '')

const isCurrentModelValid = computed(() =>
  !currentModelId.value || modelOptions.value.some((o) => o.value === currentModelId.value),
)

const selectOptions = computed(() => {
  const opts: Array<{ label: string; value: string; disabled?: boolean }> = [...modelOptions.value]
  if (!isCurrentModelValid.value && currentModelId.value) {
    opts.unshift({ label: '当前模型已失效', value: currentModelId.value, disabled: true })
  }
  return opts
})

const currentModelName = computed(() => {
  const id = currentModelId.value
  if (!id) return engineLabel.value
  const found = store.availableModels.find((m) => m.id === id)
  return found?.name || engineLabel.value || '默认模型'
})

const inputPlaceholder = computed(() => {
  return '输入需求，@ 引用文件、技能或智能体，/ 查看快捷命令'
})

function handleModelSwitch(modelId: string) {
  if (!session.value || modelId === currentModelId.value) return
  store.switchSessionModel(session.value.id, modelId)
  const name = store.availableModels.find((m) => m.id === modelId)?.name || modelId
  modelSwitchNotice.value = `已切换至 ${name}，后续回复将使用该模型`
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    modelSwitchNotice.value = ''
  }, 3000)
}

watch(
  () => agent.value?.id,
  () => {
    modelSwitchNotice.value = ''
    try {
      showWelcomeCard.value = localStorage.getItem(welcomeStorageKey.value) !== 'true'
    } catch {
      showWelcomeCard.value = true
    }
  },
)

function closeWelcomeCard() {
  showWelcomeCard.value = false
  try {
    localStorage.setItem(welcomeStorageKey.value, 'true')
  } catch {
    // ignore
  }
}

function handleSend(
  content: string,
  options: {
    attachments?: FileAttachment[]
    enableWebSearch?: boolean
    enableCodeExecution?: boolean
    explicitAgentId?: string
    skillNames?: string[]
  } = {},
) {
  if (!content.trim() && !options.attachments?.length) return
  if (store.isStreaming) return
  // sendMessage 是 async；不 await，让 UI 立即清空输入框
  store.sendMessage(content, options)
  input.value = ''
}

function handleConfirmTool(toolName: string, args: Record<string, unknown>) {
  // 发送确认消息，依赖 LLM 根据上下文再次调用同一工具并附加 _confirmed: true
  const content = `确认执行 ${toolName}`
  store.sendMessage(content, {})
}

function handleOpenToolPage(route: string, _args: Record<string, unknown>) {
  // open_page 工具直接跳转前端路由
  if (route.startsWith('/')) {
    // router.push(route)  // AgentSandbox 未引入 router，交由父层或 window 跳转
    window.location.href = route
  }
}

function handleBack() {
  store.newChat()
}

/** 以当前智能体发起 Studio 工作台会话并跳转 /studio/:sessionId */
async function handleEnterStudio() {
  if (!agent.value || creatingStudio.value) return
  creatingStudio.value = true
  try {
    const created = await studioApi.createSession({ agent_id: agent.value.id })
    store.markStudioSession(created.session_id)
    router.push({ name: 'studio', params: { sessionId: created.session_id } })
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '创建工作台会话失败')
  } finally {
    creatingStudio.value = false
  }
}

onUnmounted(() => {
  if (noticeTimer) clearTimeout(noticeTimer)
})
</script>

<template>
  <div class="agent-sandbox" v-if="agent && session">
    <ShaniaChatBackground v-if="agent.id === 'shania'" />
    <header class="sandbox-header">
      <div class="header-left">
        <NButton text class="back-btn" @click="handleBack">
          <NIcon size="18"><ArrowBackOutline /></NIcon>
        </NButton>
        <div class="agent-identity">
          <div class="id-avatar">✦</div>
          <div class="id-meta">
            <div class="id-name">{{ agentDisplayName }}</div>
            <div class="id-sub">{{ agent.description }}</div>
          </div>
        </div>
      </div>
      <div class="header-right">
        <div class="model-selector">
          <n-select
            v-if="modelOptions.length"
            :value="currentModelId"
            :options="selectOptions"
            :consistent-menu-width="false"
            :disabled="store.isStreaming"
            size="small"
            style="width: 160px"
            @update:value="handleModelSwitch"
          >
            <template #arrow>
              <n-icon size="14"><FlashOutline /></n-icon>
            </template>
          </n-select>
          <n-tag v-else size="small" round :bordered="false" type="info">{{ engineLabel }}</n-tag>
          <transition name="fade">
            <span v-if="modelSwitchNotice" class="model-switch-notice">{{ modelSwitchNotice }}</span>
          </transition>
        </div>
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton class="studio-mode-btn" size="small" :loading="creatingStudio" @click="handleEnterStudio">
              <template #icon><NIcon><DesktopOutline /></NIcon></template>
              工作台模式
            </NButton>
          </template>
          在 AI 分析工作台中打开该智能体（代码可改可跑）
        </NTooltip>
        <NButton class="capability-btn" size="small" quaternary @click="showCap = true">
          <template #icon><NIcon><BulbOutline /></NIcon></template>
          查看该智能体能力
        </NButton>
      </div>
    </header>

    <div class="sandbox-body">
      <div class="chat-content-wrapper">
        <transition name="fade">
          <div v-if="showWelcomeCard && session.messages.length === 0" class="welcome-card">
            <div class="welcome-deco" aria-hidden="true">
              <span class="welcome-ring welcome-ring-1"></span>
              <span class="welcome-ring welcome-ring-2"></span>
              <span class="welcome-ring welcome-ring-3"></span>
              <span class="welcome-star" style="top: 22%; right: 34%; width: 4px; height: 4px; opacity: 0.9"></span>
              <span class="welcome-star" style="top: 60%; right: 22%; width: 3px; height: 3px; opacity: 0.6"></span>
              <span class="welcome-star" style="top: 35%; right: 12%; width: 5px; height: 5px; opacity: 0.8"></span>
              <span class="welcome-star" style="top: 72%; right: 42%; width: 3px; height: 3px; opacity: 0.5"></span>
              <span class="welcome-star" style="top: 15%; right: 52%; width: 4px; height: 4px; opacity: 0.7"></span>
              <span class="welcome-star" style="top: 50%; right: 60%; width: 3px; height: 3px; opacity: 0.4"></span>
            </div>
            <div class="welcome-content">
              <div class="welcome-avatar">✦</div>
              <div class="welcome-text">
                <div class="welcome-kicker">STARDUST AI ASSISTANT</div>
                <div class="welcome-title">{{ agentDisplayName }}</div>
                <div class="welcome-desc">{{ agent.welcome_message || agent.description }}</div>
              </div>
            </div>
            <NButton text class="welcome-close" @click="closeWelcomeCard">
              <NIcon size="16"><CloseOutline /></NIcon>
            </NButton>
          </div>
        </transition>

        <div v-if="session.messages.length === 0" class="quick-prompts">
          <button v-for="(item, index) in quickPrompts" :key="item.prompt" :class="`prompt-${index + 1}`" @click="handleSend(item.prompt)">
            <span class="prompt-icon">✦</span>
            <span class="prompt-copy">
              <span class="prompt-title">{{ item.label }}</span>
              <span class="prompt-description">{{ item.description }}</span>
            </span>
          </button>
        </div>

        <KimiMessageList
          :messages="session.messages"
          :is-typing="store.isStreaming"
          :streaming-content="store.streamingContent"
          :streaming-thought="store.streamingThought"
          :model-name="agentDisplayName"
          :user-name="userDisplayName"
          :user-avatar="userAvatarUrl"
          :target-message-id="targetMessageId"
          @confirm-tool="handleConfirmTool"
          @open-tool-page="handleOpenToolPage"
        />
      </div>
    </div>

    <div class="sandbox-input">
      <div class="chat-content-wrapper">
        <KimiChatInput
          v-model="input"
          :disabled="store.isStreaming"
          :placeholder="inputPlaceholder"
          @send="handleSend"
        />
      </div>
    </div>

    <AgentCapabilityDrawer v-model:show="showCap" />
  </div>
</template>

<style scoped lang="scss">
.agent-sandbox {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at 12% 0%, rgba(46, 91, 255, 0.08), transparent 32%),
    radial-gradient(circle at 88% 8%, rgba(123, 77, 255, 0.07), transparent 30%),
    linear-gradient(180deg, #f4f6ff 0%, #fafbff 40%, #fff 100%);
}

.agent-sandbox::before {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  content: '';
  opacity: 0.32;
  background-image: radial-gradient(rgba(46, 91, 255, 0.16) 0.7px, transparent 0.7px);
  background-size: 18px 18px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent 55%);
}

.sandbox-header {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 12px 20px;
  border-bottom: 1px solid var(--stardust-border-soft);
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(12px);
}
.header-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.back-btn { flex-shrink: 0; color: var(--stardust-text-secondary); }
.back-btn:hover { color: var(--stardust-blue); background: var(--stardust-bg-soft); }
.agent-identity { display: flex; align-items: center; gap: 12px; min-width: 0; }
.id-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0;
  color: #fff;
  background: linear-gradient(120deg, #1E6FFF 0%, #4F6DF5 45%, #8B5CF6 100%);
  box-shadow: 0 2px 8px rgba(79, 109, 245, 0.35);
}
.id-meta { min-width: 0; }
.id-name { font-size: 15px; font-weight: 600; color: #1A1D33; }
.id-sub { font-size: 12px; color: #8A8FA3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
.header-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.studio-mode-btn {
  color: #fff;
  border-radius: 8px;
  background: var(--stardust-gradient);
  box-shadow: 0 2px 8px rgba(46, 91, 255, 0.2);
}
.studio-mode-btn:hover { opacity: 0.9; box-shadow: 0 4px 12px rgba(46, 91, 255, 0.35); }
.capability-btn {
  color: var(--stardust-blue);
  border: 1px solid #d4dbf5;
  border-radius: 8px;
}
.capability-btn:hover { color: var(--stardust-blue); border-color: var(--stardust-blue); background: var(--stardust-bg-soft); }
.model-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-selector :deep(.n-base-selection) {
  border: none;
  border-radius: 16px;
  background: #f2f3f8;
  box-shadow: none;
}
.model-selector :deep(.n-base-selection:hover) { box-shadow: 0 4px 12px rgba(30, 50, 100, 0.1); }
.model-switch-notice {
  font-size: 12px;
  color: var(--chat-accent, #4f8ef7);
  white-space: nowrap;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 内容层显式提升，确保位于点阵 ::before 与 ShaniaChatBackground 装饰层之上。
   注意：不能用 `.agent-sandbox > *` 通配提升，否则会把绝对定位的装饰背景
   一并改成 position: relative 拉进文档流，撑出顶部空白并顶高 header。 */
.sandbox-body { position: relative; z-index: 1; flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.sandbox-body > .chat-content-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.welcome-card {
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin: 16px 24px 0;
  padding: 24px 32px;
  background: linear-gradient(120deg, #1E6FFF 0%, #4F6DF5 45%, #8B5CF6 100%);
  border: none;
  border-radius: 16px;
  box-shadow: var(--shadow-card);
}
.welcome-deco {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.welcome-ring {
  position: absolute;
  border: 2px solid rgba(255, 255, 255, 0.18);
  border-radius: 50%;
}
.welcome-ring-1 { width: 240px; height: 240px; top: -80px; right: -60px; }
.welcome-ring-2 { width: 160px; height: 160px; top: 30%; right: 80px; border-width: 1px; }
.welcome-ring-3 { width: 120px; height: 120px; bottom: -50px; right: 34%; border-width: 1px; }
.welcome-star {
  position: absolute;
  background: #fff;
  border-radius: 50%;
}
.welcome-content {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 16px;
  min-width: 0;
}
.welcome-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #fff;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.35);
}
.welcome-text {
  min-width: 0;
}
.welcome-kicker {
  font-size: 12px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.75);
  margin-bottom: 8px;
}
.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 8px;
}
.welcome-desc {
  font-size: 15px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.85);
  word-break: break-word;
}
.welcome-close {
  position: relative;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: #fff;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.25);
  transition: background-color 200ms ease;
}
.welcome-close:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.22);
}
.quick-prompts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 12px 24px 0; }
.quick-prompts button { display: flex; align-items: center; gap: 9px; min-height: 64px; padding: 12px 14px; border: 1px solid #E8EAF6; border-radius: 12px; color: var(--chat-text-primary); background: var(--chat-surface); font-size: 12px; text-align: left; cursor: pointer; box-shadow: var(--stardust-card-shadow); transition: box-shadow 250ms ease, transform 250ms ease; }
.quick-prompts button:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(30, 111, 255, 0.10); }
.prompt-icon { display: grid; place-items: center; width: 40px; height: 40px; flex: 0 0 40px; border-radius: 10px; color: #fff; background: linear-gradient(135deg, #6366F1, #3B82F6); }
.prompt-2 .prompt-icon { background: linear-gradient(135deg, #8B5CF6, #6366F1); }
.prompt-3 .prompt-icon { background: linear-gradient(135deg, #06B6D4, #3B82F6); }
.prompt-4 .prompt-icon { background: linear-gradient(135deg, #14B8A6, #06B6D4); }
.prompt-copy { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.prompt-title { font-size: 15px; font-weight: 600; color: #1A1D33; }
.prompt-description { color: #8A8FA3; font-size: 13px; line-height: 1.4; }

.sandbox-input {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  padding: 14px 24px;
  border-top: 1px solid var(--stardust-border-soft);
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: blur(10px);
}
.chat-content-wrapper {
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

@media (max-width: 640px) {
  .id-sub { display: none; }
  .header-right .n-button__content { font-size: 12px; }
  .model-switch-notice { display: none; }
  .quick-prompts { grid-template-columns: 1fr; margin-inline: 14px; }
  .welcome-card { padding: 24px; }
  .welcome-title { font-size: 24px; }
  .welcome-avatar { width: 44px; height: 44px; font-size: 20px; }
  .welcome-ring-2, .welcome-ring-3 { display: none; }
  .welcome-ring-1 { width: 140px; height: 140px; top: -50px; right: -40px; }
}

@media (prefers-reduced-transparency: reduce) {
  .sandbox-header, .sandbox-input { background: var(--bg-card); backdrop-filter: none; }
}

:root[data-theme="dark"] .agent-sandbox {
  background: radial-gradient(circle at 12% 0%, rgba(118, 145, 255, 0.12), transparent 32%), var(--chat-bg);
}
:root[data-theme="dark"] .sandbox-header,
:root[data-theme="dark"] .sandbox-input { background: rgba(15, 20, 32, 0.82); }
:root[data-theme="dark"] .model-selector :deep(.n-base-selection) { background: rgba(255, 255, 255, 0.08); }
:root[data-theme="dark"] .capability-btn { border-color: rgba(118, 145, 255, 0.35); }
</style>
