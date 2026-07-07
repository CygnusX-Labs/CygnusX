<script setup lang="ts">
import { computed } from 'vue'
import { NTag, NPopover } from 'naive-ui'
import { useAgentHubStore } from '@/stores/agentHub'
import { CATEGORY_LABELS } from '@/stores/agentHub'
import type { AgentTemplate } from '@/types/agent'

const props = defineProps<{ agent: AgentTemplate }>()
defineEmits<{ select: [] }>()

const store = useAgentHubStore()

const mountedMcps = computed(() => store.mcpsByIds(props.agent.mcp_ids))
const mountedSkills = computed(() => store.skillsByIds(props.agent.skill_ids))
const caps = computed(() => [
  ...mountedMcps.value.map((m) => `搭载 ${m.name}`),
  ...mountedSkills.value.map((s) => s.name),
])
</script>

<template>
  <NPopover trigger="hover" placement="top" :width="240">
    <template #trigger>
      <div class="agent-card" :style="{ '--agent-color': agent.color }" @click="$emit('select')">
        <div class="avatar" :style="{ background: agent.color }">{{ agent.avatar }}</div>
        <div class="name">{{ agent.name }}</div>
        <div class="desc">{{ agent.description }}</div>
        <div class="badges">
          <NTag size="tiny" round :bordered="false" :color="{ color: agent.color, textColor: '#fff' }">
            {{ CATEGORY_LABELS[agent.category] }}
          </NTag>
          <NTag v-if="agent.model_engine" size="tiny" round :bordered="false" type="warning">
            {{ agent.model_engine }}
          </NTag>
          <NTag v-if="mountedMcps.length" size="tiny" round :bordered="false" type="info">
            MCP×{{ mountedMcps.length }}
          </NTag>
          <NTag v-if="mountedSkills.length" size="tiny" round :bordered="false" type="success">
            技能×{{ mountedSkills.length }}
          </NTag>
        </div>
      </div>
    </template>
    <div class="cap-pop">
      <div class="cap-title">{{ agent.avatar }} {{ agent.name }} 搭载的能力</div>
      <div v-if="caps.length" class="cap-list">
        <div v-for="c in caps" :key="c" class="cap-item">· {{ c }}</div>
      </div>
      <div v-else class="cap-empty">通用助手，未挂载额外能力</div>
    </div>
  </NPopover>
</template>

<style scoped lang="scss">
.agent-card {
  position: relative;
  display: flex; flex-direction: column; align-items: center;
  padding: 24px 18px;
  background: var(--chat-surface, #fff);
  border: 1px solid var(--chat-border, #eee);
  border-radius: var(--chat-radius-lg, 14px);
  cursor: pointer;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
  height: 100%;
}
.agent-card:hover {
  transform: translateY(-4px);
  border-color: var(--agent-color);
  box-shadow: 0 8px 28px rgba(0,0,0,.08);
}
.avatar {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 30px; margin-bottom: 12px;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--agent-color) 35%, transparent);
}
.name { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
.desc { font-size: 12px; color: var(--chat-text-muted, #888); text-align: center; line-height: 1.5; margin-bottom: 12px; min-height: 36px; }
.badges { display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; }

.cap-pop { font-size: 13px; }
.cap-title { font-weight: 600; margin-bottom: 8px; }
.cap-list { display: flex; flex-direction: column; gap: 4px; }
.cap-item { font-size: 12px; color: var(--neutral-text-2, #666); }
.cap-empty { font-size: 12px; color: var(--neutral-text-3, #aaa); }
</style>
