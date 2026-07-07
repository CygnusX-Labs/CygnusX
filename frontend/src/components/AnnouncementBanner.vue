<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { announcementApi } from '@/api/announcements'
import {
  DEFAULT_ICON_BY_TYPE,
  type Announcement,
} from '@/types/announcement'

const router = useRouter()

const banner = ref<Announcement | null>(null)
const visible = ref(false)

const STORAGE_PREFIX = 'omichub_banner_dismissed_'

/** 今日日期字符串 YYYY-MM-DD，用于 daily 关闭判断 */
function todayStr(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 该通知是否已被当前用户关闭 */
function isDismissed(b: Announcement): boolean {
  if (b.dismiss_behavior === 'none') return false
  const val = localStorage.getItem(STORAGE_PREFIX + b.id)
  if (!val) return false
  if (b.dismiss_behavior === 'forever') return true
  if (b.dismiss_behavior === 'daily') return val === todayStr()
  return false
}

function dismiss() {
  if (!banner.value) return
  const b = banner.value
  if (b.dismiss_behavior !== 'none') {
    const val = b.dismiss_behavior === 'daily' ? todayStr() : 'forever'
    localStorage.setItem(STORAGE_PREFIX + b.id, val)
  }
  // 触发 Transition leave（height + opacity 收起）
  visible.value = false
}

function handleNavigate() {
  if (!banner.value?.link) return
  const link = banner.value.link
  if (/^https?:\/\//.test(link)) {
    window.open(link, '_blank', 'noopener')
  } else {
    router.push(link)
  }
}

const iconDisplay = computed(() => {
  if (!banner.value) return '📢'
  return banner.value.icon || DEFAULT_ICON_BY_TYPE[banner.value.type] || '📢'
})

const gradientClass = computed(() => `banner-${banner.value?.type || 'info'}`)

onMounted(async () => {
  try {
    const list = await announcementApi.getActive()
    // 后端已按优先级排序，取第一条未被当前用户关闭的
    const first = list.find((b) => !isDismissed(b)) || null
    banner.value = first
    if (first) visible.value = true
  } catch {
    // 拉取失败静默处理，不阻断首页渲染
  }
})
</script>

<template>
  <Transition name="banner-slide">
    <div
      v-if="banner && visible"
      class="announcement-banner"
      :class="gradientClass"
      @click="handleNavigate"
    >
      <div class="banner-icon">{{ iconDisplay }}</div>
      <div class="banner-content">
        <div class="banner-title">{{ banner.title }}</div>
        <div class="banner-desc">{{ banner.description }}</div>
      </div>
      <div class="banner-actions" @click.stop>
        <NButton
          v-if="banner.button_text"
          size="small"
          class="banner-btn"
          @click="handleNavigate"
        >
          {{ banner.button_text }}
        </NButton>
        <button
          v-if="banner.dismiss_behavior !== 'none'"
          class="banner-close"
          aria-label="关闭"
          @click.stop="dismiss"
        >
          <NIcon :size="14"><CloseOutline /></NIcon>
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.announcement-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
  padding: 12px 16px;
  border-radius: 12px;
  color: #fff;
  cursor: pointer;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transition: filter 0.2s ease;
}
.announcement-banner:hover {
  filter: brightness(1.05);
}

/* 4 种类型渐变（亮色，暗黑模式下保持明亮，文字恒白） */
.banner-info {
  background: linear-gradient(90deg, #3b82f6, #7c3aed, #a855f7);
}
.banner-success {
  background: linear-gradient(90deg, #34d399, #14b8a6);
}
.banner-warning {
  background: linear-gradient(90deg, #fbbf24, #f97316);
}
.banner-feature {
  background: linear-gradient(90deg, #e879f9, #a855f7);
}

.banner-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.banner-content {
  flex: 1;
  min-width: 0;
}
.banner-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 20px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.banner-desc {
  font-size: 13px;
  line-height: 18px;
  color: rgba(255, 255, 255, 0.85);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.banner-btn {
  background: #fff !important;
  color: #7c3aed !important;
  border: none !important;
  font-weight: 500;
}
.banner-btn:hover {
  background: rgba(255, 255, 255, 0.9) !important;
}

.banner-close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  border: none;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease;
}
.banner-close:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: rotate(90deg);
}

/* 入场：从上方滑入 */
.banner-slide-enter-active {
  transition: transform 0.4s ease-out, opacity 0.4s ease-out;
}
.banner-slide-enter-from {
  transform: translateY(-20px);
  opacity: 0;
}

/* 离场：高度 + 透明度收起 */
.banner-slide-leave-active {
  transition: transform 0.3s ease-out, opacity 0.3s ease-out,
    max-height 0.3s ease-out, margin 0.3s ease-out, padding 0.3s ease-out;
  max-height: 80px;
}
.banner-slide-leave-to {
  transform: translateY(-10px);
  opacity: 0;
  max-height: 0;
  margin: 0;
  padding: 0;
}

/* 移动端：文字换行，避免按钮/关闭溢出 */
@media (max-width: 768px) {
  .announcement-banner {
    flex-wrap: wrap;
    gap: 8px;
  }
  .banner-content {
    order: 3;
    flex-basis: 100%;
    min-width: 100%;
  }
  .banner-title,
  .banner-desc {
    white-space: normal;
  }
}
</style>
