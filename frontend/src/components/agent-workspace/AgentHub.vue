<script setup lang="ts">
import { computed } from 'vue'
import { NEmpty, NGrid, NGridItem } from 'naive-ui'
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
      <header class="hub-header">
        <h1 class="hub-title">今天需要哪位专家为您服务？</h1>
        <p class="hub-sub">选择一位搭载专属能力组合的智能体，进入按需隔离的对话沙盒</p>
      </header>

      <NEmpty
        v-if="!groupedAgents.length"
        description="暂无可用智能体"
        class="hub-empty"
      />

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
/* 布局要点：容器为 flex，内容用 margin:auto 居中——内容少时垂直居中；
   内容超出时从顶部自然起始并可滚动，不会像 align-items:center 那样把页头裁出可视区 */
.agent-hub {
  flex: 1;
  overflow-y: auto;
  display: flex;
  padding: 40px var(--page-padding, 32px) 80px;
}
.hub-inner {
  width: 100%;
  max-width: 1100px;
  margin: auto;
}
.hub-header {
  text-align: center;
  margin-bottom: 40px;
}
.hub-title {
  font-size: 28px; line-height: 36px; font-weight: 600;
  letter-spacing: -0.02em; margin: 0 0 8px;
  color: var(--chat-text-primary, var(--neutral-text-1));
}
.hub-sub {
  font-size: 14px; line-height: 22px; margin: 0;
  color: var(--chat-text-muted, var(--neutral-text-3));
}
.hub-empty { padding: 48px 0; }
.hub-section { margin-bottom: 32px; }
.hub-section:last-child { margin-bottom: 0; }
.section-label {
  font-size: 13px; line-height: 20px; font-weight: 600; margin: 0 0 12px 4px;
  color: var(--chat-text-muted, var(--neutral-text-3));
}
.card-grid { justify-content: center; }

@media (max-width: 768px) {
  .agent-hub { padding: 24px 16px 64px; }
  .hub-header { margin-bottom: 24px; }
}
</style>
