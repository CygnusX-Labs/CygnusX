<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMagicKeys, whenever } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { NInput, NIcon, NButton, NTag, NAlert, useMessage } from 'naive-ui'
import { ShareOutline, SettingsOutline, CreateOutline } from '@vicons/ionicons5'
import KimiSidebar from './KimiSidebar.vue'
import KimiEmptyState from './KimiEmptyState.vue'
import KimiMessageList from './KimiMessageList.vue'
import KimiChatInput from './KimiChatInput.vue'
import apiClient from '@/api/client'
import { useAIStore } from '@/stores/ai'
import { useAIWebSocket } from '@/composables/useAIWebSocket'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import type { AIEvent, AIMessage } from '@/types'
import type { ChatMessage, ChatSession, SendOptions } from './types'

const aiStore = useAIStore()
const chatStore = useChatStore()
const authStore = useAuthStore()
const router = useRouter()
const message = useMessage()
const { connected, lastError, connect, sendChat } = useAIWebSocket()

const inputMessage = ref('')
const toolEvents = ref<Array<{ tool: string; args: Record<string, unknown>; result?: Record<string, unknown> }>>([])
const aiConfigured = ref(true)

const userInfo = computed(() => ({
  id: String(authStore.user?.id ?? ''),
  name: authStore.user?.username || '用户',
  avatar: '',
  role: authStore.user?.role === 'admin' ? '管理员' : '普通用户',
  roleTag: authStore.user?.role === 'admin' ? 'Admin' : 'User',
}))

// aiStore.conversations -> KimiSidebar 需要的 ChatSession[]
const sessions = computed<ChatSession[]>(() =>
  aiStore.conversations.map((c) => ({
    id: c.id,
    title: c.title,
    messages: [],
    createdAt: c.created_at,
    updatedAt: c.updated_at,
    model: c.model,
  }))
)

const currentSessionId = computed(() => aiStore.currentConversation?.id ?? '')

const titleModel = computed({
  get: () => aiStore.currentConversation?.title ?? '',
  set: (v: string) => {
    if (aiStore.currentConversation) aiStore.currentConversation.title = v
  },
})

// aiStore.messages -> KimiMessageList 需要的 ChatMessage[]
const messages = computed<ChatMessage[]>(() =>
  aiStore.messages.map((m) => ({
    id: m.id,
    role: (m.role === 'tool' ? 'system' : m.role) as ChatMessage['role'],
    content: m.content,
    createdAt: m.timestamp,
  }))
)

const isEmpty = computed(() => !aiStore.currentConversation || messages.value.length === 0)

const streamingContent = computed(() => {
  if (!aiStore.streaming) return ''
  const msgs = aiStore.messages
  const last = msgs[msgs.length - 1]
  return last?.role === 'assistant' ? last.content : ''
})

const showConnError = computed(() => !connected.value && !!lastError.value)
const showConfigWarning = computed(() => !aiConfigured.value)

const { Meta_K, Ctrl_K } = useMagicKeys()
whenever(Meta_K, () => newSession())
whenever(Ctrl_K, () => newSession())

// ===== WebSocket 事件处理（复用原 AIChat.vue 模式）=====
async function handleEvent(e: AIEvent) {
  switch (e.type) {
    case 'user_message':
      replaceLastUser(e.message)
      break
    case 'token':
      aiStore.appendAssistantToken(e.content)
      break
    case 'assistant_message':
      replaceLastAssistant(e.message)
      break
    case 'tool_call':
      toolEvents.value.push({ tool: e.tool, args: e.arguments })
      break
    case 'tool_result':
      if (toolEvents.value.length) {
        toolEvents.value[toolEvents.value.length - 1].result = e.result
      }
      break
    case 'done':
      aiStore.finishStreaming()
      break
    case 'error':
      aiStore.finishStreaming()
      message.error(e.detail)
      break
  }
}

function replaceLastUser(msg: AIMessage) {
  const msgs = aiStore.currentConversation?.messages
  if (!msgs) return
  const last = msgs[msgs.length - 1]
  if (last && last.role === 'user') {
    last.id = msg.id
    last.content = msg.content
    last.timestamp = msg.timestamp
  }
}

function replaceLastAssistant(msg: AIMessage) {
  const msgs = aiStore.currentConversation?.messages
  if (!msgs) return
  const last = msgs[msgs.length - 1]
  if (last && last.role === 'assistant') {
    last.id = msg.id
    last.content = msg.content
    last.timestamp = msg.timestamp
  }
}

// ===== 操作 =====
async function newSession() {
  try {
    const conv = await aiStore.createConversation('新对话')
    await aiStore.selectConversation(conv.id)
    inputMessage.value = ''
    toolEvents.value = []
  } catch {
    message.error('创建会话失败')
  }
}

async function selectSession(id: string) {
  try {
    await aiStore.selectConversation(id)
    inputMessage.value = ''
    toolEvents.value = []
  } catch {
    message.error('加载会话失败')
  }
}

function handleReconnect() {
  lastError.value = null
  connect(handleEvent)
}

async function deleteSession(id: string) {
  await aiStore.deleteConversation(id)
}

async function handleSend(content: string, _options: SendOptions) {
  const conv = aiStore.currentConversation
  if (!conv || !content.trim() || aiStore.streaming) return
  // 占位用户消息
  aiStore.appendMessage({
    id: crypto.randomUUID(),
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
  })
  aiStore.startStreamingAssistant()
  inputMessage.value = ''
  if (!connected.value) connect(handleEvent)
  sendChat(conv.id, content)
}

function handleSendPrompt(prompt: string) {
  if (!aiStore.currentConversation) {
    newSession().then(() => handleSend(prompt, { agentMode: chatStore.agentMode, model: chatStore.selectedModel, plugins: [] }))
    return
  }
  handleSend(prompt, { agentMode: chatStore.agentMode, model: chatStore.selectedModel, plugins: [] })
}

function handleSelectModel(modelId: string) {
  chatStore.selectModel(modelId)
}

function handleSelectPlugin(pluginId: string) {
  message.info(`已选择插件: ${pluginId}`)
}

function handleUploadFile(file: File) {
  message.info(`上传文件: ${file.name}`)
}

function handleNavigate(path: string) {
  router.push(path).catch(() => {
    /* 忽略重复导航 */
  })
}

function handleFeedback(_id: string, type: 'like' | 'dislike') {
  message.success(type === 'like' ? '感谢反馈' : '会继续改进')
}

function handleCopyMessage(content: string) {
  navigator.clipboard.writeText(content)
  message.success('已复制')
}

function handleRetry(_id: string) {
  message.info('重新生成中...')
}

// ===== 生命周期 =====
onMounted(() => {
  aiStore.fetchConversations()
  connect(handleEvent)
  apiClient.get<{ configured: boolean }>('/ai/status')
    .then((res) => {
      aiConfigured.value = res.data.configured
    })
    .catch(() => {
      aiConfigured.value = false
    })
})
</script>

<template>
  <div class="kimi-layout" :data-theme="chatStore.theme">
    <KimiSidebar
      :sessions="sessions"
      :current-session-id="currentSessionId"
      :user-info="userInfo"
      :collapsed="chatStore.sidebarCollapsed"
      @new-session="newSession"
      @select-session="selectSession"
      @delete-session="deleteSession"
      @toggle-collapse="chatStore.sidebarCollapsed = !chatStore.sidebarCollapsed"
      @navigate="handleNavigate"
    />

    <main class="kimi-main">
      <n-alert
        v-if="showConfigWarning"
        type="warning"
        :show-icon="true"
        class="config-alert"
      >
        AI 服务未配置：请在后端 .env 中设置 KIMI_API_KEY / OPENAI_API_KEY，或由管理员在"系统设置 → AI 模型配置"中添加 Provider。
      </n-alert>

      <KimiEmptyState
        v-if="isEmpty"
        logo-text="OMIC HUB"
        :quick-prompts="chatStore.quickPrompts"
        @send-prompt="handleSendPrompt"
        @upload-file="handleUploadFile"
      />

      <template v-else>
        <div class="session-header">
          <n-input v-model:value="titleModel" class="session-title-input" placeholder="会话标题">
            <template #prefix>
              <n-icon><CreateOutline /></n-icon>
            </template>
          </n-input>
          <div class="session-actions">
            <n-tag :type="connected ? 'success' : 'default'" size="small" round>
              {{ connected ? '已连接' : '未连接' }}
            </n-tag>
            <n-button text class="action-btn">
              <template #icon><n-icon><ShareOutline /></n-icon></template>
              分享
            </n-button>
            <n-button text class="action-btn">
              <template #icon><n-icon><SettingsOutline /></n-icon></template>
              设置
            </n-button>
          </div>
        </div>

        <KimiMessageList
          :messages="messages"
          :is-typing="aiStore.streaming"
          :streaming-content="streamingContent"
          @feedback="handleFeedback"
          @copy-message="handleCopyMessage"
          @retry="handleRetry"
        />

        <n-alert
          v-if="showConnError"
          type="error"
          :show-icon="true"
          closable
          class="conn-alert"
          @close="lastError = null"
        >
          <div class="conn-alert-content">
            <span>{{ lastError }}</span>
            <n-button size="tiny" type="error" secondary @click="handleReconnect">
              重连
            </n-button>
          </div>
        </n-alert>

        <div class="input-area-wrapper">
          <KimiChatInput
            v-model="inputMessage"
            :agent-mode="chatStore.agentMode"
            :selected-model="chatStore.selectedModel"
            :models="chatStore.availableModels"
            :plugins="chatStore.availablePlugins"
            :disabled="aiStore.streaming"
            @send="(content) => handleSend(content, { agentMode: chatStore.agentMode, model: chatStore.selectedModel, plugins: [] })"
            @toggle-agent="chatStore.agentMode = !chatStore.agentMode"
            @select-model="handleSelectModel"
            @select-plugin="handleSelectPlugin"
            @upload-file="handleUploadFile"
          />
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped lang="scss">
.kimi-layout {
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--chat-bg);
  color: var(--chat-text-primary);
  overflow: hidden;
}
.kimi-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.conn-hint {
  display: flex;
  justify-content: center;
  padding: 4px 24px 0;
}
.config-alert {
  border-radius: 0;
  flex-shrink: 0;
}
.conn-alert {
  border-radius: 0;
  flex-shrink: 0;
}
.conn-alert-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
