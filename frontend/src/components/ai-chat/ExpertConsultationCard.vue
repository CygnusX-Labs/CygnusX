<script setup lang="ts">
defineProps<{
  experts: Array<{ agent_id: string; name: string; opinion: string }>
}>()
</script>

<template>
  <details v-if="experts.length" class="expert-consultation-card">
    <summary>👥 已征询 {{ experts.length }} 位专家意见</summary>
    <div v-for="expert in experts" :key="expert.agent_id" class="expert-opinion">
      <strong>{{ expert.name }}</strong>
      <p>{{ expert.opinion }}</p>
    </div>
  </details>
</template>

<style scoped>
.expert-consultation-card { margin: 10px 0; padding: 10px 12px; border: 1px solid #b9d8ff; border-radius: 8px; background: #f5faff; color: #36516e; font-size: 13px; }
summary { cursor: pointer; font-weight: 600; }
.expert-opinion { padding-top: 8px; }
.expert-opinion p { margin: 4px 0 0; white-space: pre-wrap; }
</style>
