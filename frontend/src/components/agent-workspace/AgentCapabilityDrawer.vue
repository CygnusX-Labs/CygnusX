<script setup lang="ts">
import { computed } from 'vue'
import {
  NDrawer, NDrawerContent, NTag, NSpace, NCollapse, NCollapseItem, NEmpty,
} from 'naive-ui'
import { useAgentHubStore, CATEGORY_LABELS } from '@/stores/agentHub'
import type { AgentTemplate } from '@/types/agent'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [v: boolean] }>()

const store = useAgentHubStore()
const agent = computed<AgentTemplate | null>(() => store.currentAgent ?? null)

const engineLabel = computed(() => agent.value?.model_engine || '')

const mountedMcps = computed(() => (agent.value ? store.mcpsByIds(agent.value.mcp_ids) : []))
const mountedSkills = computed(() => (agent.value ? store.skillsByIds(agent.value.skill_ids) : []))
</script>

<template>
  <NDrawer :show="props.show" :width="440" placement="right" @update:show="(v) => emit('update:show', v)">
    <NDrawerContent v-if="agent" :title="`${agent.avatar} ${agent.name} · 智能体能力`" closable>
      <div class="cap-drawer">
        <div class="meta-row">
          <span class="k">大模型引擎</span>
          <NSpace :size="4">
            <NTag size="small" round :bordered="false" type="info">{{ engineLabel }}</NTag>
            <NTag v-if="agent.model_name && agent.model_name !== engineLabel" size="small" round :bordered="false">
              {{ agent.model_name }}
            </NTag>
          </NSpace>
        </div>
        <div class="meta-row">
          <span class="k">分类</span>
          <NTag size="small" round :bordered="false">{{ CATEGORY_LABELS[agent.category] }}</NTag>
        </div>

        <NCollapse :default-expanded-names="['mcp', 'skill', 'prompt']" arrow-placement="right">
          <NCollapseItem name="mcp" title="挂载的 MCP 服务">
            <template #header-extra>{{ mountedMcps.length }} 个</template>
            <NEmpty v-if="!mountedMcps.length" description="未挂载 MCP" size="small" />
            <div v-else class="mcp-list">
              <div v-for="m in mountedMcps" :key="m.id" class="mcp-block">
                <div class="mcp-head">
                  <NTag size="tiny" round :bordered="false" :type="m.status === 'online' ? 'success' : 'default'">
                    {{ m.status === 'online' ? '🟢' : '🔴' }}
                  </NTag>
                  <span class="mcp-name">{{ m.name }}</span>
                </div>
                <div class="mcp-desc">{{ m.description }}</div>
                <NSpace size="small" style="margin-top: 6px;">
                  <NTag v-for="t in m.tools" :key="t.name" size="tiny" :bordered="false">{{ t.name }}</NTag>
                </NSpace>
              </div>
            </div>
          </NCollapseItem>

          <NCollapseItem name="skill" title="挂载的技能">
            <template #header-extra>{{ mountedSkills.length }} 个</template>
            <NEmpty v-if="!mountedSkills.length" description="未挂载技能" size="small" />
            <NSpace v-else size="small">
              <NTag v-for="s in mountedSkills" :key="s.id" size="small" round type="success">
                {{ s.icon }} {{ s.name }}
              </NTag>
            </NSpace>
          </NCollapseItem>

          <NCollapseItem name="prompt" title="系统设定 (System Prompt)">
            <div class="prompt-box">{{ agent.system_prompt }}</div>
          </NCollapseItem>
        </NCollapse>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.cap-drawer { display: flex; flex-direction: column; gap: 12px; }
.meta-row { display: flex; align-items: center; justify-content: space-between; }
.meta-row .k { font-size: 13px; color: #888; }
.mcp-list { display: flex; flex-direction: column; gap: 12px; }
.mcp-block { background: rgba(0,0,0,.03); border-radius: 8px; padding: 10px 12px; }
.mcp-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.mcp-name { font-weight: 600; font-size: 13px; }
.mcp-desc { font-size: 12px; color: #888; }
.prompt-box { font-size: 12px; color: #555; white-space: pre-wrap; line-height: 1.6; background: rgba(0,0,0,.03); padding: 10px 12px; border-radius: 8px; }
</style>
