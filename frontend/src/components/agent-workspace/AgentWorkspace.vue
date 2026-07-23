<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AgentSidebar from './AgentSidebar.vue'
import AgentHub from './AgentHub.vue'
import AgentSandbox from './AgentSandbox.vue'
import SessionHistoryDrawer from './SessionHistoryDrawer.vue'
import AppLoading from '@/components/AppLoading.vue'
import { useAgentHubStore, type AgentSession } from '@/stores/agentHub'
import { NButton } from 'naive-ui'

const store = useAgentHubStore()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const historyOpen = ref(false)
const targetMessageId = ref('')

/** 统一入口 Agent：智能助手（router），落地页与新建对话默认直接进入它 */
const ROUTER_AGENT_ID = 'agent-router'

/** 无当前会话时自动开启一个「智能助手」会话（单一入口，不再让用户逐个挑专家） */
function ensureDefaultSession() {
  if (store.currentSession) return
  const routerAgent =
    store.activeAgents.find((a) => a.id === ROUTER_AGENT_ID) ||
    store.activeAgents.find((a) => a.features?.router) ||
    store.activeAgents.find((a) => a.is_default) ||
    store.activeAgents[0]
  if (routerAgent) store.startSessionFromAgent(routerAgent.id)
}

async function initAssets() {
  loading.value = true
  error.value = ''
  try {
    await store.initAssets()
    ensureDefaultSession()
  } catch (e: any) {
    error.value = e?.message || '加载 Agent 数据失败'
  } finally {
    loading.value = false
  }
}

onMounted(initAssets)

function handleNewChat() {
  store.newChat()
  ensureDefaultSession()
}

function handleSelectAgent(agentId: string) {
  store.startSessionFromAgent(agentId)
}

function handleHistorySelect(session: AgentSession, messageId?: string) {
  if (session.mode === 'studio' || store.studioSessionIds.has(session.id)) {
    router.push({ name: 'studio', params: { sessionId: session.id }, query: messageId ? { message: messageId } : {} })
    return
  }
  if (!store.sessions.some((item) => item.id === session.id)) store.sessions.unshift(session)
  targetMessageId.value = messageId || ''
  store.selectSession(session.id)
}
</script>

<template>
  <div class="agent-workspace">
    <AgentSidebar
      @new-chat="handleNewChat"
      @open-history="historyOpen = true"
    />
    <main class="workspace-main">
      <div v-if="loading" class="workspace-center">
        <AppLoading text="加载 AI 助手..." />
      </div>
      <div v-else-if="error" class="workspace-center">
        <p class="text-sm text-gray-500 mb-3">{{ error }}</p>
        <NButton size="small" @click="initAssets">重试</NButton>
      </div>
      <template v-else>
        <AgentSandbox v-if="store.currentSession" :target-message-id="targetMessageId" />
        <AgentHub v-else @select="handleSelectAgent" />
      </template>
    </main>
    <SessionHistoryDrawer v-model:show="historyOpen" mode="all" @select="handleHistorySelect" />
  </div>
</template>

<style scoped lang="scss">
.agent-workspace {
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--chat-bg);
  color: var(--chat-text-primary, inherit);
  overflow: hidden;
}

.workspace-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workspace-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
</style>
