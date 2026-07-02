<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AgentSidebar from './AgentSidebar.vue'
import AgentHub from './AgentHub.vue'
import AgentSandbox from './AgentSandbox.vue'
import { useAgentHubStore } from '@/stores/agentHub'

const store = useAgentHubStore()
const collapsed = ref(false)

onMounted(() => {
  store.initAssets()
})

function handleNewChat() {
  store.newChat()
}

function handleSelectAgent(agentId: string) {
  store.startSessionFromAgent(agentId)
}
</script>

<template>
  <div class="agent-workspace">
    <AgentSidebar
      :collapsed="collapsed"
      @toggle-collapse="collapsed = !collapsed"
      @new-chat="handleNewChat"
      @select-session="store.selectSession"
      @delete-session="store.deleteSession"
    />
    <main class="workspace-main">
      <AgentSandbox v-if="store.currentSession" />
      <AgentHub v-else @select="handleSelectAgent" />
    </main>
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
</style>
