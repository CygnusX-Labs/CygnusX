<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NSpace, NIcon, NProgress, NTag, NTooltip,
  NDataTable, NEmpty,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  FlaskOutline, RocketOutline, CloudUploadOutline, EyeOutline,
  RefreshOutline, TrashOutline, CheckmarkOutline, ChevronForwardOutline,
  CloseOutline, CalendarOutline, SparklesOutline,
} from '@vicons/ionicons5'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, DatasetComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import axios from 'axios'
import apiClient from '@/api/client'
import type { Task } from '@/types'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
])

const router = useRouter()

const healthStatus = ref<string>('检测中...')
const healthOk = ref(false)
const flowCount = ref(0)
const runningTaskCount = ref(0)
const totalTaskCount = ref(0)
const sampleCount = ref(0)
const recentTasks = ref<Task[]>([])
const loadingTasks = ref(false)
const bannerClosed = ref(localStorage.getItem('omichub:dashboardBannerClosed') === 'true')

// 趋势图数据（后续可接入真实统计）
const trendData = [
  { date: '06/12', tasks: 5, samples: 10 },
  { date: '06/14', tasks: 15, samples: 35 },
  { date: '06/16', tasks: 40, samples: 180 },
  { date: '06/18', tasks: 25, samples: 120 },
  { date: '06/20', tasks: 8, samples: 40 },
  { date: '06/22', tasks: 2, samples: 15 },
  { date: '06/24', tasks: 0, samples: 5 },
]

const trendOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#FFFFFF',
    borderColor: '#E5E6EB',
    borderWidth: 1,
    textStyle: { color: '#1D2129', fontSize: 12 },
    extraCssText: 'box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-radius: 8px;',
  },
  legend: {
    data: ['分析任务数', '样本数量'],
    bottom: 0,
    textStyle: { color: '#4E5969', fontSize: 12 },
    itemWidth: 10,
    itemHeight: 10,
  },
  grid: {
    left: 12,
    right: 12,
    top: 24,
    bottom: 32,
    containLabel: true,
  },
  xAxis: {
    type: 'category',
    data: trendData.map((d) => d.date),
    axisLine: { lineStyle: { color: '#E5E6EB' } },
    axisTick: { show: false },
    axisLabel: { color: '#86909C', fontSize: 12 },
  },
  yAxis: [
    {
      type: 'value',
      name: '任务数',
      nameTextStyle: { color: '#86909C', fontSize: 11, align: 'left', padding: [0, 0, 0, -20] },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#E5E6EB', type: 'dashed' } },
      axisLabel: { color: '#86909C', fontSize: 12 },
    },
    {
      type: 'value',
      name: '样本数',
      nameTextStyle: { color: '#86909C', fontSize: 11, align: 'right', padding: [0, -20, 0, 0] },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { color: '#86909C', fontSize: 12 },
    },
  ],
  series: [
    {
      name: '分析任务数',
      type: 'bar',
      data: trendData.map((d) => d.tasks),
      itemStyle: { color: '#165DFF', borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 32,
    },
    {
      name: '样本数量',
      type: 'line',
      yAxisIndex: 1,
      data: trendData.map((d) => d.samples),
      itemStyle: { color: '#FF7D00' },
      lineStyle: { color: '#FF7D00', width: 2 },
      symbol: 'circle',
      symbolSize: 6,
      smooth: true,
    },
  ],
}))

onMounted(async () => {
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

  // 任务统计
  try {
    const running = await apiClient.get<{ total: number }>('/tasks', { params: { status: 'running' } })
    runningTaskCount.value = running.data.total ?? 0

    const all = await apiClient.get<{ total: number; items: Task[] }>('/tasks', { params: { limit: 5 } })
    totalTaskCount.value = all.data.total ?? 0
    recentTasks.value = all.data.items ?? []
  } catch {
    runningTaskCount.value = 0
    totalTaskCount.value = 0
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

const quickSteps = [
  { number: 1, title: '上传样本数据', status: 'completed' as const },
  { number: 2, title: '选择分析流程', status: 'current' as const },
  { number: 3, title: '查看分析结果', status: 'pending' as const },
]

function statusClass(status: string) {
  return `step-circle step-circle--${status}`
}

function statusTextClass(status: string) {
  return `step-title step-title--${status}`
}
</script>

<template>
  <div class="dashboard-page">
    <h1 class="page-title">控制台</h1>

    <!-- 公告横幅 -->
    <div v-if="!bannerClosed" class="announcement-banner animate-fade-in">
      <div class="banner-content">
        <div class="banner-icon">
          <NIcon :size="20">
            <SparklesOutline />
          </NIcon>
        </div>
        <div class="banner-text">
          <h4 class="banner-title">单细胞分析模块即将上线</h4>
          <p class="banner-desc">全新支持 10x Genomics 数据，敬请期待</p>
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

    <!-- 快速开始 -->
    <section class="quick-start animate-fade-in-up">
      <h2 class="section-title">快速开始</h2>
      <div class="steps-row">
        <div
          v-for="(step, index) in quickSteps"
          :key="step.number"
          class="step-item"
        >
          <span :class="statusClass(step.status)">
            <NIcon v-if="step.status === 'completed'" :size="14">
              <CheckmarkOutline />
            </NIcon>
            <span v-else>{{ step.number }}</span>
          </span>
          <span :class="statusTextClass(step.status)">{{ step.title }}</span>
          <NIcon
            v-if="index < quickSteps.length - 1"
            :size="16"
            class="step-arrow"
          >
            <ChevronForwardOutline />
          </NIcon>
        </div>
      </div>
    </section>

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
      </div>

      <!-- 右侧趋势图 -->
      <div class="arco-card trend-card">
        <div class="arco-card-header">
          <span class="arco-card-title">任务提交趋势</span>
          <NButton size="small" class="date-picker-btn">
            <template #icon>
              <NIcon :size="14"><CalendarOutline /></NIcon>
            </template>
            近 7 天
          </NButton>
        </div>
        <div class="trend-chart-wrap">
          <VChart :option="trendOption" autoresize style="width: 100%; height: 260px;" />
        </div>
      </div>
    </section>

    <!-- 最近任务 -->
    <section class="arco-card recent-tasks animate-fade-in-up delay-200">
      <div class="arco-card-header">
        <h3 class="arco-card-title">最近任务</h3>
        <NButton text size="small" class="view-all-btn" @click="router.push('/tasks')">
          查看全部 →
        </NButton>
      </div>
      <NDataTable
        v-if="recentTasks.length > 0"
        :columns="columns"
        :data="recentTasks"
        :loading="loadingTasks"
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

/* 快速开始 */
.quick-start {
  margin-bottom: 24px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  line-height: 26px;
  color: var(--neutral-text-1);
  margin: 0 0 16px;
}

.steps-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-circle {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.step-circle--completed {
  background: var(--arco-primary);
  color: #fff;
}

.step-circle--current {
  background: var(--arco-primary);
  color: #fff;
  box-shadow: 0 0 0 4px rgba(22, 93, 255, 0.15);
}

.step-circle--pending {
  background: var(--neutral-border);
  color: var(--neutral-text-3);
}

.step-title {
  font-size: 14px;
  line-height: 22px;
}

.step-title--completed,
.step-title--current {
  color: var(--arco-primary);
  font-weight: 500;
}

.step-title--pending {
  color: var(--neutral-text-3);
}

.step-arrow {
  color: var(--neutral-text-4);
  margin: 0 4px;
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

.trend-card {
  min-width: 0;
}

.trend-chart-wrap {
  width: 100%;
}

.refresh-btn,
.view-all-btn {
  color: var(--arco-primary) !important;
}

.date-picker-btn {
  color: var(--neutral-text-2) !important;
  border-color: var(--neutral-border) !important;
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

  .steps-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .step-arrow {
    display: none;
  }

  .banner-content {
    flex-wrap: wrap;
  }

  .banner-btn {
    margin-left: auto;
  }
}
</style>
