<script setup lang="ts">
import { ref, computed } from 'vue'
import { NButton, NIcon, NTag } from 'naive-ui'
import { ArrowBackOutline, BulbOutline } from '@vicons/ionicons5'
import KimiMessageList from '@/components/ai-chat/KimiMessageList.vue'
import KimiChatInput from '@/components/ai-chat/KimiChatInput.vue'
import AgentCapabilityDrawer from './AgentCapabilityDrawer.vue'
import { useAgentHubStore } from '@/stores/agentHub'
import type { FileAttachment } from '@/components/ai-chat/types'

const store = useAgentHubStore()

const input = ref('')
const showCap = ref(false)

const agent = computed(() => store.currentAgent)
const session = computed(() => store.currentSession)
const engineLabel = computed(() => agent.value?.model_engine || '')

function handleSend(content: string, options: { attachments?: FileAttachment[]; enableWebSearch?: boolean; enableCodeExecution?: boolean } = {}) {
  if (!content.trim() && !options.attachments?.length) return
  if (store.isStreaming) return
  // sendMessage 是 async；不 await，让 UI 立即清空输入框
  store.sendMessage(content, options)
  input.value = ''
}

function handleBack() {
  store.newChat()
}
</script>

<template>
  <div class="agent-sandbox" v-if="agent && session">
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
        <NTag size="small" round :bordered="false" type="info">{{ engineLabel }}</NTag>
        <NButton size="small" tertiary @click="showCap = true">
          <template #icon><NIcon><BulbOutline /></NIcon></template>
          查看该智能体能力
        </NButton>
      </div>
    </header>

    <div class="sandbox-body">
      <KimiMessageList
        :messages="session.messages"
        :is-typing="store.isStreaming"
        :streaming-content="store.streamingContent"
        :streaming-thought="store.streamingThought"
        :model-name="agent.name"
      />
    </div>

    <div class="sandbox-input">
      <KimiChatInput
        v-model="input"
        :disabled="store.isStreaming"
        :placeholder="`向 ${agent.name} 提问…`"
        @send="handleSend"
      />
    </div>

    <AgentCapabilityDrawer v-model:show="showCap" />
  </div>
</template>

<style scoped lang="scss">
.agent-sandbox { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

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

.sandbox-body { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.sandbox-input {
  flex-shrink: 0; padding: 14px 24px;
  border-top: 1px solid var(--chat-border);
  background: var(--chat-bg);
}

@media (max-width: 640px) {
  .id-sub { display: none; }
  .header-right .n-button__content { font-size: 12px; }
}
</style>
