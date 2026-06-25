<script setup lang="ts">
import { CloudUploadOutline, FolderOpenOutline } from '@vicons/ionicons5'
import { NButton, NEmpty, NIcon } from 'naive-ui'
</script>

<template>
  <div class="page-container flex-col flex-center" style="gap: 16px; text-align: center;">
    <div class="placeholder-icon">
      <NIcon :size="64">
        <FolderOpenOutline />
      </NIcon>
    </div>
    <h2 class="page-title" style="margin-bottom: 8px;">数据管理</h2>
    <p class="page-subtitle">页面建设中，敬请期待</p>
    <NButton type="primary">
      <template #icon>
        <NIcon><CloudUploadOutline /></NIcon>
      </template>
      上传样本数据
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
