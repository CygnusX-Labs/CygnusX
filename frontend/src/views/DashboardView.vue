<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NSpace, NIcon, NProgress, NTag, NTooltip, NDataTable, NEmpty, NSpin,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  RocketOutline, EyeOutline,
  RefreshOutline, TrashOutline,
  CloseOutline, SparklesOutline,
} from '@vicons/ionicons5'
import axios from 'axios'
import apiClient from '@/api/client'
import type { Task } from '@/types'
import type { StatsOverview } from '@/types/stats'
import { useAuthStore } from '@/stores/auth'
import { useAdminWelcome } from '@/composables/useAdminWelcome'
import TrendChart from '@/components/dashboard/TrendChart.vue'
import QuickStartSteps from '@/components/dashboard/QuickStartSteps.vue'
import AdminStatsPanel from '@/components/dashboard/AdminStatsPanel.vue'

const router = useRouter()
const authStore = useAuthStore()
// 管理员登录欢迎小彩蛋：内部判断角色 + 3s 超时兜底，一次会话只弹一次
const { triggerAdminWelcome } = useAdminWelcome()

const healthStatus = ref<string>('检测中...')
const healthOk = ref(false)
const flowCount = ref(0)
const runningTaskCount = ref(0)
const totalTaskCount = ref(0)
const sampleCount = ref(0)
const recentTasks = ref<Task[]>([])
const loadingOverview = ref(false)
const loadingTasks = ref(false)
const bannerClosed = ref(localStorage.getItem('omichub:dashboardBannerClosed') === 'true')

onMounted(async () => {
  // 管理员欢迎彩蛋：后台异步拉取文案，不阻塞主流程；失败自动回退默认文案
  triggerAdminWelcome()

  // 健康检查
  try {
    const res = await axios.get('/health')
    healthOk.value = res.data.status === 'ok'
    healthStatus.value = healthOk.value ? '系统运行正常' : '异常'
  } catch {
    healthStatus.value = '后端未连接'
  }

  // 分析流程数量
  try {
    const res = await apiClient.get<{ total: number }>('/flows')
    flowCount.value = res.data.total ?? 0
  } catch {
    flowCount.value = 0
  }

  // 状态概览（运行任务 / 总任务 / 样本数）— 真实聚合接口
  loadingOverview.value = true
  try {
    const res = await apiClient.get<StatsOverview>('/stats/overview')
    runningTaskCount.value = res.data.running ?? 0
    totalTaskCount.value = res.data.total ?? 0
    sampleCount.value = res.data.samples ?? 0
  } catch {
    runningTaskCount.value = 0
    totalTaskCount.value = 0
    sampleCount.value = 0
  } finally {
    loadingOverview.value = false
  }

  // 最近任务
  loadingTasks.value = true
  try {
    const res = await apiClient.get<{ total: number; items: Task[] }>('/tasks', {
      params: { limit: 5 },
    })
    totalTaskCount.value = res.data.total ?? 0
    recentTasks.value = res.data.items ?? []
  } catch {
    recentTasks.value = []
  } finally {
    loadingTasks.value = false
  }
})

function closeBanner() {
  bannerClosed.value = true
  localStorage.setItem('omichub:dashboardBannerClosed', 'true')
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function statusConfig(status: string) {
  const map: Record<string, { type: 'success' | 'warning' | 'error' | 'info' | 'default'; text: string }> = {
    success: { type: 'success', text: '已完成' },
    failed: { type: 'error', text: '失败' },
    running: { type: 'info', text: '运行中' },
    queued: { type: 'warning', text: '排队中' },
    pending: { type: 'warning', text: '待审核' },
    cancelled: { type: 'default', text: '已取消' },
  }
  return map[status] || { type: 'default', text: status }
}

const columns: DataTableColumns<Task> = [
  { title: '任务名称', key: 'name', ellipsis: { tooltip: true } },
  { title: '分析流程', key: 'flow_id', width: 120 },
  {
    title: '提交时间',
    key: 'created_at',
    width: 150,
    render: (row) => formatTime(row.created_at),
  },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: (row) => {
      const cfg = statusConfig(row.status)
      return h(NTag, { type: cfg.type, size: 'small', round: true }, { default: () => cfg.text })
    },
  },
  {
    title: '进度',
    key: 'progress',
    width: 160,
    render: (row) => h(NProgress, {
      type: 'line',
      percentage: Math.round(row.progress * 100),
      height: 6,
      color: { stops: ['#165DFF', '#6B8DD6'] },
      railColor: '#E5E6EB',
      showIndicator: false,
    }),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: () => h(NSpace, { size: 4 }, {
      default: () => [
        h(NTooltip, null, { trigger: () => h(NButton, { size: 'tiny', quaternary: true, circle: true }, { icon: () => h(NIcon, null, { default: () => h(EyeOutline) }) }), default: () => '查看' }),
        h(NTooltip, null, { trigger: () => h(NButton, { size: 'tiny', quaternary: true, circle: true }, { icon: () => h(NIcon, null, { default: () => h(RefreshOutline) }) }), default: () => '重新运行' }),
        h(NTooltip, null, { trigger: () => h(NButton, { size: 'tiny', quaternary: true, circle: true }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }), default: () => '删除' }),
      ],
    }),
  },
]
</script>

<template>
  <div class="dashboard-page">
    <h1 class="page-title">仪表板</h1>

    <!-- 公告横幅 -->
    <div v-if="!bannerClosed" class="announcement-banner animate-fade-in">
      <div class="banner-content">
        <div class="banner-icon">
          <NIcon :size="20">
            <SparklesOutline />
          </NIcon>
        </div>
        <div class="banner-text">
          <h4 class="banner-title">RNA-seq / ATAC-seq 分析已就绪</h4>
          <p class="banner-desc">转录组与表观遗传分析流程均已上线，点击立即开始</p>
        </div>
        <NButton size="small" class="banner-btn" @click="router.push('/flows')">
          立即查看
        </NButton>
      </div>
      <button class="banner-close" @click="closeBanner">
        <NIcon :size="14">
          <CloseOutline />
        </NIcon>
      </button>
    </div>

    <!-- 快速开始（动态画像） -->
    <QuickStartSteps />

    <!-- 数据概览 - 左右分栏 -->
    <section class="overview-grid animate-fade-in-up delay-100">
      <!-- 左侧运行状态 -->
      <div class="arco-card status-card">
        <div class="arco-card-header">
          <span class="arco-card-title">运行状态</span>
          <NButton text size="small" class="refresh-btn" @click="$router.go(0)">
            <template #icon>
              <NIcon :size="16"><RefreshOutline /></NIcon>
            </template>
            刷新
          </NButton>
        </div>
        <div class="status-main">
          <span class="status-pulse">
            <span class="status-pulse-dot" />
          </span>
          <span class="status-value">{{ healthStatus }}</span>
        </div>
        <div class="status-divider" />
        <NSpin :show="loadingOverview">
          <div class="status-metrics">
            <div class="status-metric-row">
              <span class="status-metric-label">分析流程</span>
              <span class="status-metric-value">{{ flowCount }}</span>
            </div>
            <div class="status-metric-row">
              <span class="status-metric-label">运行任务</span>
              <span class="status-metric-value">{{ runningTaskCount }}</span>
            </div>
            <div class="status-metric-row">
              <span class="status-metric-label">数据样本</span>
              <span class="status-metric-value">{{ sampleCount }}</span>
            </div>
          </div>
        </NSpin>
      </div>

      <!-- 右侧趋势图（真实接口 + 7/30 天切换） -->
      <TrendChart />
    </section>

    <!-- 管理员全平台监控态势（仅管理员可见） -->
    <AdminStatsPanel v-if="authStore.isAdmin" />

    <!-- 最近任务 -->
    <section class="arco-card recent-tasks animate-fade-in-up delay-200">
      <div class="arco-card-header">
        <h3 class="arco-card-title">最近任务</h3>
        <NButton text size="small" class="view-all-btn" @click="router.push('/tasks')">
          查看全部 →
        </NButton>
      </div>
      <NSpin :show="loadingTasks">
        <NDataTable
          v-if="recentTasks.length > 0"
          :columns="columns"
          :data="recentTasks"
          :bordered="false"
          size="small"
          :single-line="false"
          class="recent-table"
        />
        <NEmpty v-else description="暂无任务">
          <template #extra>
            <div class="empty-extra">
              <p>点击上方按钮提交您的第一个分析任务</p>
              <NButton type="primary" @click="router.push('/flows')">
                <template #icon>
                  <NIcon><RocketOutline /></NIcon>
                </template>
                提交分析任务
              </NButton>
            </div>
          </template>
        </NEmpty>
      </NSpin>
    </section>
  </div>
</template>

<style scoped>
.dashboard-page {
  padding: 24px;
  min-height: 100%;
  background: var(--neutral-bg);
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  line-height: 32px;
  color: var(--neutral-text-1);
  margin: 0 0 24px;
}

/* 公告横幅 */
.announcement-banner {
  position: relative;
  background: linear-gradient(135deg, #165DFF 0%, #6B8DD6 50%, #8E54E9 100%);
  border-radius: 12px;
  padding: 16px 48px 16px 16px;
  margin-bottom: 24px;
  color: #fff;
}

.banner-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.banner-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.banner-text {
  flex: 1;
  min-width: 0;
}

.banner-title {
  font-size: 14px;
  font-weight: 500;
  margin: 0 0 4px;
}

.banner-desc {
  font-size: 12px;
  opacity: 0.85;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.banner-btn {
  background: rgba(255, 255, 255, 0.2) !important;
  color: #fff !important;
  border: none !important;
}
.banner-btn:hover {
  background: rgba(255, 255, 255, 0.3) !important;
}

.banner-close {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s ease;
}
.banner-close:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* 数据概览 */
.overview-grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  margin-bottom: 24px;
}

.status-card {
  display: flex;
  flex-direction: column;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0 24px;
}

.status-pulse {
  position: relative;
  display: inline-flex;
  width: 12px;
  height: 12px;
}

.status-pulse-dot {
  position: relative;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--arco-success);
}

.status-pulse-dot::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--arco-success);
  animation: pulse-ring 1.5s ease-out infinite;
  opacity: 0.6;
}

@keyframes pulse-ring {
  0% { transform: scale(1); opacity: 0.6; }
  100% { transform: scale(2.5); opacity: 0; }
}

.status-value {
  font-size: 32px;
  font-weight: 600;
  line-height: 40px;
  color: var(--neutral-text-1);
  font-variant-numeric: tabular-nums;
}

.status-divider {
  height: 1px;
  background: var(--neutral-border);
  margin-bottom: 16px;
}

.status-metrics {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.status-metric-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-metric-label {
  font-size: 14px;
  color: var(--neutral-text-3);
}

.status-metric-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-1);
}

.refresh-btn,
.view-all-btn {
  color: var(--arco-primary) !important;
}

/* 最近任务 */
.recent-tasks {
  overflow: hidden;
}

.recent-table :deep(th) {
  font-size: 12px;
  color: var(--neutral-text-3);
  font-weight: 500;
  background: transparent !important;
  border-bottom: 1px solid var(--neutral-border);
}

.recent-table :deep(td) {
  font-size: 13px;
  color: var(--neutral-text-1);
  border-bottom: 1px solid rgba(229, 230, 235, 0.5);
}

.recent-table :deep(tr:hover td) {
  background: var(--neutral-hover) !important;
}

.empty-extra {
  text-align: center;
}
.empty-extra p {
  font-size: 13px;
  color: var(--neutral-text-3);
  margin: 0 0 12px;
}

/* 响应式 */
@media (max-width: 1024px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    padding: 16px;
  }

  .banner-content {
    flex-wrap: wrap;
  }

  .banner-btn {
    margin-left: auto;
  }
}
</style>
