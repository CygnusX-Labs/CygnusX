<script setup lang="ts">
import { NTabPane, NTabs } from 'naive-ui'
import AnnouncementManager from '@/components/admin/AnnouncementManager.vue'
import NotificationManager from '@/components/admin/NotificationManager.vue'
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">通知公告管理</h1>
    <NTabs type="line" animated>
      <NTabPane name="announcement" tab="首页条幅">
        <AnnouncementManager />
      </NTabPane>
      <NTabPane name="notification" tab="通知提醒">
        <NotificationManager />
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  min-height: 100%;
  background: var(--neutral-bg);
}
.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 0 0 16px;
}
</style>
