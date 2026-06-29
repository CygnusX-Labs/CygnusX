<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMagicKeys, whenever } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { NInput, NIcon, NButton, NTag, NAlert, NSelect, useMessage } from 'naive-ui'
import { ShareOutline, SettingsOutline, CreateOutline } from '@vicons/ionicons5'
import KimiSidebar from './KimiSidebar.vue'
import KimiEmptyState from './KimiEmptyState.vue'
import KimiMessageList from './KimiMessageList.vue'
import KimiChatInput from './KimiChatInput.vue'
import apiClient from '@/api/client'
import { useChatSessionStore } from '@/stores/chatSession'
import { useChatAssistantStore } from '@/stores/chatAssistant'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import type { ChatMessage, ChatSession, SendOptions, ModelOption } from './types'

const chatSessionStore = useChatSessionStore()
const chatAssistantStore = useChatAssistantStore()
const chatStore = useChatStore()
const authStore = useAuthStore()
const router = useRouter()
const message = useMessage()

const inputMessage = ref('')
const aiConfigured = ref(true)

const userInfo = computed(() => ({
  id: String(authStore.user?.id ?? ''),
  name: authStore.user?.username || '用户',
  avatar: '',
  role: authStore.user?.role === 'admin' ? '管理员' : '普通用户',
  roleTag: authStore.user?.role === 'admin' ? 'Admin' : 'User',
}))

// chatSessionStore.sessions -> KimiSidebar 需要的 ChatSession[]
const sessions = computed<ChatSession[]>(() =>
  chatSessionStore.sessions.map((s) => ({
    id: s.session_id,
    title: s.title,
    messages: [],
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    model: s.model_id,
  }))
)

const currentSessionId = computed(() => chatSessionStore.currentSessionId)

const titleModel = computed({
  get: () => chatSessionStore.currentSession?.title ?? '',
  set: (v: string) => {
    const sid = chatSessionStore.currentSessionId
    if (sid) chatSessionStore.updateSessionTitle(sid, v)
  },
})

// chatSessionStore.messages -> KimiMessageList 需要的 ChatMessage[]
const messages = computed<ChatMessage[]>(() => {
  // 依赖流式内容，确保 SSE 推流时能实时触发重新渲染
  const _ = chatSessionStore.streamingContent + chatSessionStore.streamingReasoning
  return chatSessionStore.messages.map((m) => ({
    id: m.message_id,
    role: m.role as ChatMessage['role'],
    content: m.content,
    thought: m.reasoning,
    createdAt: m.created_at,
  }))
})

const isEmpty = computed(
  () => !chatSessionStore.currentSessionId || messages.value.length === 0,
)

const assistantOptions = computed(() =>
  chatAssistantStore.assistants.map((a) => ({
    label: `${a.icon} ${a.name}`,
    value: a.assistant_id,
  }))
)

// chatSessionStore.models -> KimiChatInput 需要的 ModelOption[]
const availableModelsForInput = computed<ModelOption[]>(() =>
  chatSessionStore.models.map((m) => ({
    id: m.id,
    name: m.name,
    description: `${m.provider_type} · ${m.model}`,
    provider: m.provider_type,
  }))
)

const streamingContent = computed(() => {
  // 依赖流式内容，确保 SSE 推流时 streamingContent 能实时更新
  const _ = chatSessionStore.streamingContent
  const msgs = chatSessionStore.messages
  const last = msgs[msgs.length - 1]
  return last?.role === 'assistant' && last.status === 'streaming' ? last.content : ''
})

const streamingReasoning = computed(() => {
  // 依赖流式思考内容，确保 reasoning 能实时更新
  const _ = chatSessionStore.streamingReasoning
  const msgs = chatSessionStore.messages
  const last = msgs[msgs.length - 1]
  return last?.role === 'assistant' && last.status === 'streaming' ? last.reasoning : ''
})

const showConfigWarning = computed(() => !aiConfigured.value)
const showStreamError = computed(() => !!chatSessionStore.streamError)

const { Meta_K, Ctrl_K } = useMagicKeys()
whenever(Meta_K, () => newSession())
whenever(Ctrl_K, () => newSession())

// ===== 操作 =====
async function newSession() {
  chatSessionStore.clearDisplayMessages()
  chatSessionStore.currentSessionId = ''
  inputMessage.value = ''
}

async function selectSession(id: string) {
  await chatSessionStore.selectSession(id)
  inputMessage.value = ''
}

async function deleteSession(id: string) {
  await chatSessionStore.deleteSession(id)
}

async function handleSend(content: string, _options: SendOptions) {
  if (!content.trim() || chatSessionStore.isStreaming) return

  // 确保有选中的模型
  if (!chatSessionStore.selectedModelId) {
    await chatSessionStore.fetchModels()
  }
  if (!chatSessionStore.selectedModelId) {
    message.error('请先在模型配置中选择一个可用的 AI 模型')
    return
  }

  // 如果没有会话，先创建一个
  if (!chatSessionStore.currentSessionId) {
    const sid = await chatSessionStore.createSession(
      chatSessionStore.selectedModelId,
      chatAssistantStore.currentAssistantId || undefined,
    )
    if (!sid) {
      message.error('创建会话失败')
      return
    }
  }

  inputMessage.value = ''
  await chatSessionStore.sendMessage(content, {
    assistantId: chatAssistantStore.currentAssistantId || undefined,
    // [极简测试] 临时禁用助手系统提示词
    // systemPrompt: chatAssistantStore.currentAssistant?.system_prompt,
  })

  if (chatSessionStore.streamError) {
    message.error(chatSessionStore.streamError)
  }
}

function handleSendPrompt(prompt: string) {
  handleSend(prompt, { agentMode: chatStore.agentMode, model: chatSessionStore.selectedModelId, plugins: [] })
}

function handleSelectModel(modelId: string) {
  chatSessionStore.selectedModelId = modelId
}

function handleSelectPlugin(_pluginId: string) {
  message.info('插件功能开发中，敬请期待')
}

function handleUploadFile(_file: File) {
  message.info('文件上传功能开发中，敬请期待')
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
onMounted(async () => {
  await Promise.all([
    chatSessionStore.fetchModels(),
    chatSessionStore.fetchSessions(),
    chatAssistantStore.fetchAssistants(),
  ])
  apiClient
    .get<{ configured: boolean }>('/ai/status')
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

      <div class="main-content-area">
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
              <n-select
                v-if="assistantOptions.length > 0"
                v-model:value="chatAssistantStore.currentAssistantId"
                :options="assistantOptions"
                size="tiny"
                style="width: 160px"
                placeholder="选择助手"
              />
              <n-tag :type="chatSessionStore.isStreaming ? 'warning' : 'success'" size="small" round>
                {{ chatSessionStore.isStreaming ? '生成中' : '就绪' }}
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
            :is-typing="chatSessionStore.isStreaming"
            :streaming-content="streamingContent"
            :streaming-thought="streamingReasoning"
            @feedback="handleFeedback"
            @copy-message="handleCopyMessage"
            @retry="handleRetry"
          />

          <n-alert
            v-if="showStreamError"
            type="error"
            :show-icon="true"
            closable
            class="conn-alert"
            @close="chatSessionStore.streamError = ''"
          >
            {{ chatSessionStore.streamError }}
          </n-alert>
        </template>
      </div>

      <div class="input-area-wrapper">
        <KimiChatInput
          v-model="inputMessage"
          :agent-mode="chatStore.agentMode"
          :selected-model="chatSessionStore.selectedModelId"
          :models="availableModelsForInput"
          :plugins="chatStore.availablePlugins"
          :disabled="chatSessionStore.isStreaming"
          @send="(content) => handleSend(content, { agentMode: chatStore.agentMode, model: chatSessionStore.selectedModelId, plugins: [] })"
          @toggle-agent="chatStore.agentMode = !chatStore.agentMode"
          @select-model="handleSelectModel"
          @select-plugin="handleSelectPlugin"
          @upload-file="handleUploadFile"
        />
      </div>
    </main>
  </div>
</template>

<style scoped lang="scss">
.kimi-layout {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
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

.config-alert {
  border-radius: 0;
  flex-shrink: 0;
}

.conn-alert {
  border-radius: 0;
  flex-shrink: 0;
}

.main-content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.session-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--chat-border);
}

.input-area-wrapper {
  flex-shrink: 0;
  padding: 16px 24px;
  border-top: 1px solid var(--chat-border);
  background: var(--chat-bg);
}
</style>
