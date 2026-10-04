<script setup lang="ts">
/**
 * 顶部数据大盘 —— Samples / Files / Folders / Storage 四卡
 *
 * 口径说明（A5 治理，与 FilesView 数据来源一一对应）：
 * - Samples：当前用户注册样本数（纯个人，不含团队）
 * - Files：可见文件总数（个人 + 所属团队）
 * - Folders：用户自建的顶层目录数（非系统目录，与「项目」模块无关）
 * - Storage：个人存储配额用量
 * loaded=false 时显示骨架占位，避免首屏闪零。
 */
import { NIcon, NProgress, NSkeleton, NTooltip } from 'naive-ui'
import type { Component } from 'vue'
import {
  FlaskOutline, FolderOpenOutline, FolderOutline, CloudUploadOutline,
} from '@vicons/ionicons5'
import type { QuotaInfo } from '@/types'

defineProps<{
  samples: number
  files: number
  projects: number
  quota: QuotaInfo
  /** 首次加载是否完成：false 时卡片数值区显示骨架，避免闪零 */
  loaded?: boolean
}>()

function formatSize(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(2)} ${sizes[i]}`
}

interface CardDef {
  key: string
  label: string
  icon: Component
  /** 卡片口径说明（tooltip 副标题用） */
  hint: string
}
const cards: CardDef[] = [
  { key: 'samples', label: 'Samples 样本', icon: FlaskOutline, hint: '已注册样本（个人）' },
  { key: 'files', label: 'Files 文件', icon: FolderOpenOutline, hint: '可见文件（个人 + 团队）' },
  { key: 'folders', label: 'Folders 目录', icon: FolderOutline, hint: '自建顶层目录（非系统目录）' },
  { key: 'storage', label: 'Storage 存储', icon: CloudUploadOutline, hint: '个人存储配额用量' },
]
</script>

<template>
  <div class="overview-stats">
    <div v-for="c in cards" :key="c.key" class="stat-card">
      <div class="stat-icon">
        <NIcon :size="20"><component :is="c.icon" /></NIcon>
      </div>
      <div class="stat-body">
        <NTooltip trigger="hover">
          <template #trigger>
            <span class="stat-label">{{ c.label }}</span>
          </template>
          {{ c.hint }}
        </NTooltip>
        <template v-if="c.key === 'storage'">
          <template v-if="loaded">
            <span class="stat-value">{{ formatSize(quota.used) }} <span class="stat-total">/ {{ formatSize(quota.total) }}</span></span>
            <NProgress
              :percentage="Math.min(100, quota.percent)"
              :height="4"
              :show-indicator="false"
              :color="quota.percent >= 91 ? '#F53F3F' : quota.percent >= 71 ? '#FF7D00' : '#165DFF'"
              rail-color="rgba(22,93,255,0.08)"
              class="stat-bar"
            />
            <span class="stat-sub">{{ quota.percent }}% 已用</span>
          </template>
          <NSkeleton v-else text :width="120" />
        </template>
        <template v-else>
          <span v-if="loaded" class="stat-value">{{ c.key === 'samples' ? samples : c.key === 'files' ? files : projects }}</span>
          <NSkeleton v-else text :width="64" />
          <span v-if="loaded" class="stat-sub">{{ c.hint }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overview-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.stat-card {
  height: 88px;
  background: var(--neutral-card, #fff);
  border-radius: var(--radius-lg, 16px);
  box-shadow: var(--shadow-soft, 0 4px 12px rgba(0, 0, 0, 0.05));
  padding: 16px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-sizing: border-box;
  border: 1px solid var(--neutral-border);
}
.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md, 12px);
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}
.stat-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--neutral-text-3, #86909c);
}
.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--neutral-text-1, #1d2129);
  font-variant-numeric: tabular-nums;
  line-height: 1.25;
}
.stat-total {
  font-size: 12px;
  font-weight: 500;
  color: var(--neutral-text-3, #86909c);
}
.stat-sub {
  font-size: 11px;
  color: var(--neutral-text-3, #86909c);
}
.stat-bar {
  margin-top: 2px;
}
@media (max-width: 1100px) {
  .overview-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 600px) {
  .overview-stats {
    grid-template-columns: 1fr;
  }
}
</style>
