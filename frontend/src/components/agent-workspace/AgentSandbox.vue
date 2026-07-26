<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NSelect, NTag, NTooltip, useMessage } from 'naive-ui'
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
          <div class="id-avatar" :style="{ background: agent.color }">{{ agent.avatar }}</div>
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
            <div class="welcome-content">
              <div class="welcome-avatar" :style="{ background: agent.color }">{{ agent.avatar }}</div>
              <div class="welcome-text">
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
  display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0;
}
.id-meta { min-width: 0; }
.id-name { font-size: 15px; font-weight: 600; }
.id-sub { font-size: 12px; color: var(--chat-text-muted, #999); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
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
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin: 16px 24px 0;
  padding: 16px 18px;
  background: var(--brand-gradient-soft);
  border: 1px solid var(--chat-border, #f0f0f0);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}
.welcome-content {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
}
.welcome-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  flex-shrink: 0;
}
.welcome-text {
  min-width: 0;
}
.welcome-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--chat-text-primary, #1a1a1a);
  margin-bottom: 4px;
}
.welcome-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--chat-text-secondary, #666);
  word-break: break-word;
}
.welcome-close {
  flex-shrink: 0;
  color: var(--chat-text-muted, #999);
}
.welcome-close:hover {
  color: var(--chat-text-primary, #1a1a1a);
}
.quick-prompts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 12px 24px 0; }
.quick-prompts button { display: flex; align-items: center; gap: 9px; min-height: 64px; padding: 12px 14px; border: 1px solid var(--chat-border); border-radius: 8px; color: var(--chat-text-primary); background: var(--chat-surface); font-size: 12px; text-align: left; cursor: pointer; transition: border-color .16s ease, box-shadow .16s ease, transform .16s ease; }
.quick-prompts button { border-radius: 12px; box-shadow: var(--stardust-card-shadow); }
.quick-prompts button:hover { border-color: var(--stardust-blue); box-shadow: 0 6px 18px rgba(46, 91, 255, 0.12); transform: translateY(-2px); }
.prompt-icon { display: grid; place-items: center; width: 26px; height: 26px; flex: 0 0 26px; border-radius: 8px; color: var(--brand-primary); background: var(--icon-blue-bg); }
.prompt-2 .prompt-icon { color: #8B5CF6; background: var(--icon-purple-bg); }
.prompt-3 .prompt-icon { color: #0891B2; background: var(--icon-cyan-bg); }
.prompt-4 .prompt-icon { color: #059669; background: var(--icon-green-bg); }
.prompt-copy { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.prompt-title { font-size: 13px; font-weight: 600; }
.prompt-description { color: var(--stardust-text-secondary); font-size: 11px; line-height: 1.4; }

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
