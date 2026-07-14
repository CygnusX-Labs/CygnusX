<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { NButton, NIcon, NSelect, NTag } from 'naive-ui'
import { ArrowBackOutline, BulbOutline, FlashOutline, CloseOutline } from '@vicons/ionicons5'
import KimiMessageList from '@/components/ai-chat/KimiMessageList.vue'
import KimiChatInput from '@/components/ai-chat/KimiChatInput.vue'
import AgentCapabilityDrawer from './AgentCapabilityDrawer.vue'
import ShaniaChatBackground from './ShaniaChatBackground.vue'
import { useAgentHubStore } from '@/stores/agentHub'
import { useAuthStore } from '@/stores/auth'
import type { FileAttachment } from '@/components/ai-chat/types'

const store = useAgentHubStore()
const authStore = useAuthStore()

const input = ref('')
const showCap = ref(false)
const modelSwitchNotice = ref('')
const showWelcomeCard = ref(true)
let noticeTimer: ReturnType<typeof setTimeout> | null = null

const agent = computed(() => store.currentAgent)
const session = computed(() => store.currentSession)
const engineLabel = computed(() => agent.value?.model_engine || '')

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
  const hint = agent.value?.welcome_message || agent.value?.description || `向 ${agent.value?.name || 'AI 助手'} 提问`
  return hint
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

function handleSend(content: string, options: { attachments?: FileAttachment[]; enableWebSearch?: boolean; enableCodeExecution?: boolean } = {}) {
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
            <div class="id-name">{{ agent.name }}</div>
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
        <NButton size="small" tertiary @click="showCap = true">
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
                <div class="welcome-title">{{ agent.name }}</div>
                <div class="welcome-desc">{{ agent.welcome_message || agent.description }}</div>
              </div>
            </div>
            <NButton text class="welcome-close" @click="closeWelcomeCard">
              <NIcon size="16"><CloseOutline /></NIcon>
            </NButton>
          </div>
        </transition>

        <KimiMessageList
          :messages="session.messages"
          :is-typing="store.isStreaming"
          :streaming-content="store.streamingContent"
          :streaming-thought="store.streamingThought"
          :model-name="agent.name"
          :user-name="userDisplayName"
          :user-avatar="userAvatarUrl"
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
.agent-sandbox { position: relative; display: flex; flex-direction: column; height: 100%; overflow: hidden; }

.sandbox-header {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-bottom: 1px solid var(--chat-border);
  background: var(--chat-nav-bg, var(--chat-bg));
}
.header-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.back-btn { flex-shrink: 0; }
.agent-identity { display: flex; align-items: center; gap: 12px; min-width: 0; }
.id-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0;
}
.id-meta { min-width: 0; }
.id-name { font-size: 15px; font-weight: 600; }
.id-sub { font-size: 12px; color: var(--chat-text-muted, #999); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
.header-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.model-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}
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

.sandbox-body { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
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
  background: var(--chat-surface, #ffffff);
  border: 1px solid var(--chat-border, #f0f0f0);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.welcome-content {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
}
.welcome-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
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

.sandbox-input {
  flex-shrink: 0;
  padding: 14px 24px;
  border-top: 1px solid var(--chat-border);
  background: var(--chat-bg);
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
}
</style>
