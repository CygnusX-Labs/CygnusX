<script setup lang="ts">
import { NTabs, NTabPane } from 'naive-ui'
import McpResourceTab from '@/components/admin/McpResourceTab.vue'
import SkillResourceTab from '@/components/admin/SkillResourceTab.vue'
import AgentResourceTab from '@/components/admin/AgentResourceTab.vue'
import PageHeader from '@/components/PageHeader.vue'
</script>

<template>
  <div class="ai-resource-center">
    <PageHeader title="AI 资源中心" subtitle="集中管理 MCP 服务、技能包与智能助手资源" />
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
