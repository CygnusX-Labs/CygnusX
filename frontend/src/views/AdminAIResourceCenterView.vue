<script setup lang="ts">
import { NTabs, NTabPane } from 'naive-ui'
import McpResourceTab from '@/components/admin/McpResourceTab.vue'
import SkillResourceTab from '@/components/admin/SkillResourceTab.vue'
import AgentResourceTab from '@/components/admin/AgentResourceTab.vue'
</script>

<template>
  <div class="ai-resource-center">
    <NTabs type="line" animated>
      <NTabPane name="mcp" tab="MCP 服务">
        <McpResourceTab />
      </NTabPane>
      <NTabPane name="skill" tab="技能">
        <SkillResourceTab />
      </NTabPane>
      <NTabPane name="agent" tab="助手">
        <AgentResourceTab />
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
.ai-resource-center {
  max-width: 1280px;
  margin: 0 auto;
}
</style>
