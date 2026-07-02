<script setup lang="ts">
import { NGrid, NGridItem } from 'naive-ui'
import AgentCard from './AgentCard.vue'
import { useAgentHubStore } from '@/stores/agentHub'

const store = useAgentHubStore()
defineEmits<{ select: [agentId: string] }>()
</script>

<template>
  <div class="agent-hub">
    <div class="hub-inner">
      <h1 class="hub-title">今天需要哪位专家为您服务？</h1>
      <p class="hub-sub">选择一位搭载专属能力组合的智能体，进入按需隔离的对话沙盒</p>

      <NGrid :cols="4" :x-gap="18" :y-gap="18" responsive="screen" item-responsive class="card-grid">
        <NGridItem v-for="agent in store.activeAgents" :key="agent.id" span="4 s:2 m:2 l:1">
          <AgentCard :agent="agent" @select="$emit('select', agent.id)" />
        </NGridItem>
      </NGrid>
    </div>
  </div>
</template>

<style scoped lang="scss">
.agent-hub {
  flex: 1;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px 80px;
}
.hub-inner { width: 100%; max-width: 1100px; }
.hub-title {
  font-size: 30px; font-weight: 700; margin: 0 0 8px;
  text-align: center; color: var(--chat-text-primary, inherit);
}
.hub-sub {
  font-size: 14px; text-align: center; margin: 0 0 36px;
  color: var(--chat-text-muted, #999);
}
.card-grid { justify-content: center; }
</style>
