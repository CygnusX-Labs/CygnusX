<script setup lang="ts">
import { ChatbubblesOutline, ConstructOutline } from '@vicons/ionicons5'
import { NButton, NIcon } from 'naive-ui'
</script>

<template>
  <div class="page-container flex-col flex-center" style="gap: 16px; text-align: center;">
    <div class="placeholder-icon">
      <NIcon :size="64">
        <ChatbubblesOutline />
      </NIcon>
    </div>
    <h2 class="page-title" style="margin-bottom: 8px;">AI 助手</h2>
    <p class="page-subtitle">智能分析助手即将上线，敬请期待</p>
    <NButton type="primary">
      <template #icon>
        <NIcon><ConstructOutline /></NIcon>
      </template>
      了解实验室知识库
    </NButton>
  </div>
</template>

<style scoped>
.placeholder-icon {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 8px;
}
</style>
