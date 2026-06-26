<script setup lang="ts">
import { CodeSlashOutline } from '@vicons/ionicons5'
import { NButton, NEmpty, NIcon, useMessage } from 'naive-ui'

const message = useMessage()

function handleNewSession() {
  message.info('代码沙盒功能正在建设中，敬请期待')
}
</script>

<template>
  <div class="page-container flex-col flex-center" style="gap: 16px; text-align: center;">
    <div class="placeholder-icon">
      <NIcon :size="64">
        <CodeSlashOutline />
      </NIcon>
    </div>
    <h2 class="page-title" style="margin-bottom: 8px;">代码沙盒</h2>
    <p class="page-subtitle">在线 Python / R 代码执行环境，页面建设中，敬请期待</p>
    <NButton type="primary" disabled @click="handleNewSession">
      <template #icon>
        <NIcon><CodeSlashOutline /></NIcon>
      </template>
      新建沙盒会话
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
