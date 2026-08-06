<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AgentSidebar from './AgentSidebar.vue'
import AgentHub from './AgentHub.vue'
import AgentSandbox from './AgentSandbox.vue'
import SessionHistoryDrawer from './SessionHistoryDrawer.vue'
import AppLoading from '@/components/AppLoading.vue'
import { useAgentHubStore, type AgentSession } from '@/stores/agentHub'
import { ArrowForwardOutline, CompassOutline } from '@vicons/ionicons5'
import { NButton, NIcon, NModal } from 'naive-ui'

const store = useAgentHubStore()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const historyOpen = ref(false)
const agentPickerOpen = ref(false)
const targetMessageId = ref('')

/** 统一入口 Agent：星尘 AI 负责理解任务并分派给可用专家。 */
const ROUTER_AGENT_ID = 'agent-router'

/** 首次进入默认开启星尘 AI 调度会话；“新建对话”也可直接选择专家。 */
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
  agentPickerOpen.value = true
}

function handleSelectAgent(agentId: string) {
  agentPickerOpen.value = false
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
    <NModal
      v-model:show="agentPickerOpen"
      class="agent-picker-modal"
      preset="card"
      style="width: min(1240px, calc(100vw - 32px)); max-height: calc(100dvh - 32px)"
      :bordered="false"
      :segmented="false"
    >
      <div class="agent-picker-content">
        <header class="agent-picker-header">
          <div>
            <span class="agent-picker-kicker">新建对话</span>
            <h2>选择处理方式</h2>
          </div>
          <p>默认由星尘 AI 识别任务并分派；熟悉任务时可直接指定专家。</p>
        </header>
        <button
          class="stardust-route-card omichub-selectable-card is-selected"
          type="button"
          aria-label="交给星尘 AI 自动分派"
          @click="handleSelectAgent(ROUTER_AGENT_ID)"
        >
          <span class="route-icon" aria-hidden="true"><NIcon :component="CompassOutline" /></span>
          <span class="route-copy">
            <strong>交给星尘 AI 自动分派</strong>
            <span>描述目标、数据或当前问题，由星尘决定接下来由哪位 Agent 继续处理。</span>
          </span>
          <NIcon class="route-action" :component="ArrowForwardOutline" aria-hidden="true" />
        </button>
        <div class="agent-picker-section-heading">
          <strong>直接选择专家</strong>
          <span>按领域切换查看</span>
        </div>
        <AgentHub compact :exclude-agent-ids="[ROUTER_AGENT_ID]" @select="handleSelectAgent" />
      </div>
    </NModal>
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
:deep(.agent-picker-modal.n-card),
:deep(.agent-picker-modal .n-card) {
  max-height: calc(100dvh - 32px);
  overflow: hidden;
  border: 1px solid var(--chat-border, var(--neutral-border));
  border-radius: var(--radius-xl, 20px);
  background: var(--chat-surface, var(--neutral-card));
  box-shadow: var(--shadow-dropdown);
}

:deep(.agent-picker-modal .n-card__content),
:deep(.agent-picker-modal.n-card .n-card__content) {
  max-height: calc(100dvh - 32px);
  padding: var(--space-xl, 24px) var(--space-2xl, 32px);
  overflow: hidden;
}

.agent-picker-content { min-height: 0; }
.agent-picker-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: var(--space-xl, 24px);
  margin-bottom: var(--space-xl, 24px);
}
.agent-picker-kicker {
  display: block;
  margin-bottom: var(--space-xs, 6px);
  font-size: 12px;
  font-weight: 650;
  letter-spacing: .08em;
  color: var(--chat-text-muted, var(--neutral-text-3));
}
.agent-picker-header h2 {
  margin: 0;
  font-size: 22px;
  line-height: 1.3;
  letter-spacing: -.02em;
  color: var(--chat-text-primary, var(--neutral-text-1));
}
.agent-picker-header p {
  max-width: 420px;
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--chat-text-secondary, var(--neutral-text-2));
}
.stardust-route-card {
  display: flex;
  width: 100%;
  align-items: center;
  gap: var(--space-md, 12px);
  padding: 16px 18px;
  border: 1px solid var(--chat-border, var(--neutral-border));
  border-radius: var(--radius-lg, 14px);
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--chat-surface, var(--neutral-card));
  transition: border-color .16s ease, background-color .16s ease, box-shadow .16s ease;
}
.stardust-route-card:hover {
  box-shadow: var(--shadow-card);
}
.stardust-route-card:focus-visible { outline: 2px solid var(--chat-primary, var(--primary-color)); outline-offset: 3px; }
.route-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: var(--radius-md, 10px);
  color: var(--text-on-primary);
  background: var(--arco-primary);
}
.route-copy { display: grid; min-width: 0; gap: 4px; }
.route-copy strong { font-size: 14px; font-weight: 650; color: var(--chat-text-primary, var(--neutral-text-1)); }
.route-copy span { font-size: 12px; line-height: 1.55; color: var(--chat-text-secondary, var(--neutral-text-2)); }
.route-action { margin-left: auto; flex: 0 0 auto; color: var(--arco-primary); font-size: 19px; }
.agent-picker-section-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: var(--space-xl, 24px) 0 var(--space-md, 12px);
}
.agent-picker-section-heading strong { font-size: 14px; font-weight: 650; color: var(--chat-text-primary, var(--neutral-text-1)); }
.agent-picker-section-heading span { font-size: 12px; color: var(--chat-text-muted, var(--neutral-text-3)); }

@media (max-width: 640px) {
  :deep(.agent-picker-modal .n-card__content),
  :deep(.agent-picker-modal.n-card .n-card__content) { padding: var(--space-lg, 16px); overflow-y: auto; }
  .agent-picker-header { display: block; margin-bottom: var(--space-lg, 16px); }
  .agent-picker-header h2 { font-size: 20px; }
  .agent-picker-header p { margin-top: var(--space-xs, 6px); }
  .route-action { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .stardust-route-card { transition: none; }
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
