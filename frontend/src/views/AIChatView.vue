<script setup lang="ts">
import AgentWorkspace from '@/components/agent-workspace/AgentWorkspace.vue'
</script>

<template>
  <div class="ai-page">
    <AgentWorkspace />
  </div>
</template>

<style scoped>
.ai-page {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  height: 100%;
  display: flex;
  overflow: hidden;
}
</style>
