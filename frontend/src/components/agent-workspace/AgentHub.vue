<script setup lang="ts">
import { computed } from 'vue'
import { NGrid, NGridItem } from 'naive-ui'
import AgentCard from './AgentCard.vue'
import { useAgentHubStore, CATEGORY_LABELS } from '@/stores/agentHub'
import type { AgentCategory, AgentTemplate } from '@/types/agent'

const store = useAgentHubStore()
defineEmits<{ select: [agentId: string] }>()

/** 按分类分组展示（分类顺序固定，未知分类归入末尾） */
const CATEGORY_ORDER: AgentCategory[] = ['general', 'analysis', 'code', 'visualization']

const groupedAgents = computed(() => {
  const groups: { key: string; label: string; agents: AgentTemplate[] }[] = []
  const buckets = new Map<string, AgentTemplate[]>()
  for (const agent of store.activeAgents) {
    const list = buckets.get(agent.category) || []
    list.push(agent)
    buckets.set(agent.category, list)
  }
  const ordered = [
    ...CATEGORY_ORDER.filter((c) => buckets.has(c)).map((c) => c as string),
    ...[...buckets.keys()].filter((k) => !CATEGORY_ORDER.includes(k as AgentCategory)),
  ]
  for (const key of ordered) {
    groups.push({
      key,
      label: CATEGORY_LABELS[key as AgentCategory] || key,
      agents: buckets.get(key) || [],
    })
  }
  return groups
})
</script>

<template>
  <div class="agent-hub">
    <div class="hub-inner">
      <h1 class="hub-title">今天需要哪位专家为您服务？</h1>
      <p class="hub-sub">选择一位搭载专属能力组合的智能体，进入按需隔离的对话沙盒</p>

      <section v-for="group in groupedAgents" :key="group.key" class="hub-section">
        <h2 class="section-label">{{ group.label }}</h2>
        <NGrid :cols="4" :x-gap="18" :y-gap="18" responsive="screen" item-responsive class="card-grid">
          <NGridItem v-for="agent in group.agents" :key="agent.id" span="4 s:2 m:2 l:1">
            <AgentCard :agent="agent" @select="$emit('select', agent.id)" />
          </NGridItem>
        </NGrid>
      </section>
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
.hub-section { margin-bottom: 28px; }
.section-label {
  font-size: 13px; font-weight: 600; margin: 0 0 12px 4px;
  color: var(--chat-text-muted, #999);
}
.card-grid { justify-content: center; }
</style>
