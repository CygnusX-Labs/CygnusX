<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NSpace, NIcon, NProgress, NTag, NTooltip, NDataTable, NEmpty, NSpin,
  NPopconfirm, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  RocketOutline, EyeOutline,
  RefreshOutline, TrashOutline,
} from '@vicons/ionicons5'
import axios from 'axios'
import apiClient from '@/api/client'
import { fetchBlastTasks } from '@/api/blast'
import type { Task } from '@/types'
import type { BlastTaskListItem } from '@/types/blast'
import type { StatsOverview } from '@/types/stats'
import { useAuthStore } from '@/stores/auth'
import TrendChart from '@/components/dashboard/TrendChart.vue'
import StudioUsagePanel from '@/components/dashboard/StudioUsagePanel.vue'
import QuickStartSteps from '@/components/dashboard/QuickStartSteps.vue'
import AdminStatsPanel from '@/components/dashboard/AdminStatsPanel.vue'
import AnnouncementBanner from '@/components/AnnouncementBanner.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const authStore = useAuthStore()

const healthStatus = ref<string>('检测中...')
const healthOk = ref(false)
const flowCount = ref(0)
const runningTaskCount = ref(0)
const totalTaskCount = ref(0)
const sampleCount = ref(0)
const recentTasks = ref<Task[]>([])
const blastTasks = ref<BlastTaskListItem[]>([])
const loadingOverview = ref(false)
const loadingTasks = ref(false)
const loadingBlastTasks = ref(false)

const message = useMessage()

// ===== 最近任务：管理员视角迭代期 mock 预览 =====
// 真实接口 GET /tasks 暂未返回 username 字段，先用 mock 预览多用户混合效果。
// 接口就绪后置 USE_MOCK_TASKS = false 即可切回真实数据。
const USE_MOCK_TASKS = true

const MOCK_TASKS: Task[] = [
  {
    id: 't-001', flow_id: 'rna-seq', user_id: 'u-1001', username: 'zhang_san',
    name: '番茄叶片 RNA-seq 重复', status: 'running', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0.62, logs: [], created_at: '2026-07-03T09:12:00',
    started_at: '2026-07-03T09:13:00', finished_at: null,
  },
  {
    id: 't-002', flow_id: 'ebi_download', user_id: 'u-1002', username: 'li_si',
    name: 'EBI PRJEB12345 原始数据下载', status: 'failed', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '远程连接超时',
    progress: 0.18, logs: [], created_at: '2026-07-03T08:40:00',
    started_at: '2026-07-03T08:41:00', finished_at: '2026-07-03T09:05:00',
  },
  {
    id: 't-003', flow_id: 'atac-seq', user_id: 'u-1003', username: 'wang_wu',
    name: '拟南芥根尖 ATAC-seq', status: 'success', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 1, logs: [], created_at: '2026-07-02T16:20:00',
    started_at: '2026-07-02T16:21:00', finished_at: '2026-07-02T18:02:00',
  },
  {
    id: 't-004', flow_id: 'rna-seq', user_id: 'u-1001', username: 'zhang_san',
    name: '黄瓜果实转录组分析', status: 'queued', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0, logs: [], created_at: '2026-07-03T09:30:00',
    started_at: null, finished_at: null,
  },
  {
    id: 't-005', flow_id: 'variant_calling', user_id: 'u-1004', username: 'zhao_liu',
    name: '水稻群体变异检测', status: 'pending', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0, logs: [], created_at: '2026-07-03T09:45:00',
    started_at: null, finished_at: null,
  },
]

// 操作列：功能接口对接中，先占位（console + Message）
function handleView(row: Task) {
  console.log('[dashboard] handleView', row.id)
  message.info('该功能接口对接中')
}
function handleRetry(row: Task) {
  console.log('[dashboard] handleRetry', row.id)
  message.info('该功能接口对接中')
}
function handleDelete(row: Task) {
  console.log('[dashboard] handleDelete', row.id)
  message.info('该功能接口对接中')
}

// 重试仅在非进行态可用：running / queued / pending 视为进行中，禁止重试
function canRetry(status: Task['status']): boolean {
  return !['running', 'queued', 'pending'].includes(status)
}

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

  // 最近任务：USE_MOCK_TASKS=true 用 mock 预览多用户混合；false 走真实接口
  if (USE_MOCK_TASKS) {
    recentTasks.value = MOCK_TASKS
    totalTaskCount.value = MOCK_TASKS.length
    loadingTasks.value = false
  } else {
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
  }

  // 最近 BLAST 任务
  loadingBlastTasks.value = true
  try {
    const res = await fetchBlastTasks(undefined, 1, 5)
    blastTasks.value = res.items ?? []
  } catch {
    blastTasks.value = []
  } finally {
    loadingBlastTasks.value = false
  }
})

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
  {
    title: '所属用户',
    key: 'user_id',
    width: 120,
    render: (row) => row.username || row.user_id,
  },
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
    width: 168,
    render: (row) => h(NSpace, { size: 4 }, {
      default: () => [
        // 查看任务详情
        h(NTooltip, null, {
          trigger: () => h(NButton, {
            size: 'tiny', quaternary: true, circle: true,
            onClick: () => handleView(row),
          }, { icon: () => h(NIcon, null, { default: () => h(EyeOutline) }) }),
          default: () => '查看任务详情',
        }),
        // 重新运行：进行中（running/queued/pending）禁用
        h(NTooltip, null, {
          trigger: () => h(NButton, {
            size: 'tiny', quaternary: true, circle: true,
            disabled: !canRetry(row.status),
            onClick: () => handleRetry(row),
          }, { icon: () => h(NIcon, null, { default: () => h(RefreshOutline) }) }),
          default: () => canRetry(row.status) ? '重新运行' : '任务进行中，无法重试',
        }),
        // 删除：Popconfirm 二次确认（提示会清理底层计算资源与文件目录）
        h(NPopconfirm, {
          positiveText: '确认删除',
          negativeText: '取消',
          onPositiveClick: () => handleDelete(row),
        }, {
          default: () => '此操作将同时清理该用户底层的计算资源与文件目录，是否继续？',
          trigger: () => h(NTooltip, null, {
            trigger: () => h(NButton, {
              size: 'tiny', quaternary: true, circle: true, type: 'error',
            }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
            default: () => '删除任务',
          }),
        }),
      ],
    }),
  },
]

// ===== 最近 BLAST 任务 =====
function blastStatusConfig(status: string) {
  const map: Record<string, { type: 'success' | 'warning' | 'error' | 'info' | 'default'; text: string }> = {
    completed: { type: 'success', text: '已完成' },
    failed: { type: 'error', text: '失败' },
    running: { type: 'info', text: '运行中' },
    queued: { type: 'warning', text: '排队中' },
    cancelled: { type: 'default', text: '已取消' },
  }
  return map[status] || { type: 'default', text: status }
}

const blastColumns: DataTableColumns<BlastTaskListItem> = [
  {
    title: '任务 ID',
    key: 'task_id',
    width: 160,
    ellipsis: { tooltip: true },
    render: (row) => row.task_id.slice(0, 12),
  },
  { title: '查询标题', key: 'query_title', ellipsis: { tooltip: true } },
  { title: '数据库', key: 'db_name', width: 140, ellipsis: { tooltip: true } },
  { title: 'Program', key: 'program', width: 90 },
  {
    title: '提交时间',
    key: 'submitted_at',
    width: 150,
    render: (row) => formatTime(row.submitted_at || null),
  },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: (row) => {
      const cfg = blastStatusConfig(row.status)
      return h(NTag, { type: cfg.type, size: 'small', round: true }, { default: () => cfg.text })
    },
  },
  {
    title: '进度',
    key: 'progress',
    width: 160,
    render: (row) => h(NProgress, {
      type: 'line',
      percentage: row.progress,
      height: 6,
      color: { stops: ['#165DFF', '#6B8DD6'] },
      railColor: '#E5E6EB',
      showIndicator: false,
    }),
  },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (row) => h(NTooltip, null, {
      trigger: () => h(NButton, {
        size: 'tiny', quaternary: true, circle: true,
        onClick: () => router.push(`/tools/blast?task=${row.task_id}`),
      }, { icon: () => h(NIcon, null, { default: () => h(EyeOutline) }) }),
      default: () => '查看 BLAST 结果',
    }),
  },
]
</script>

<template>
  <div class="dashboard-page">
    <PageHeader title="仪表板" subtitle="掌握当前分析任务、平台运行状态与数据趋势" />

    <AnnouncementBanner
      title="RNA-seq / ATAC-seq 分析已就绪"
      description="转录组与表观遗传分析流程均已上线，点击立即开始"
      action-text="立即查看"
      to="/flows"
      dismiss-key="dashboard-analysis-ready"
    />

    <!-- 快速开始（动态画像） -->
    <QuickStartSteps />

    <!-- 数据概览 - 左右分栏 -->
    <section class="overview-grid animate-fade-in-up delay-100">
      <!-- 左侧运行状态 -->
      <div class="arco-card status-card card-hover-lift">
        <div class="arco-card-header">
          <span class="arco-card-title">运行状态</span>
          <div class="header-right">
            <span class="trend-badge trend-up">+12%</span>
            <NButton text size="small" class="refresh-btn" @click="$router.go(0)">
              <template #icon>
                <NIcon :size="16"><RefreshOutline /></NIcon>
              </template>
              刷新
            </NButton>
          </div>
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

    <StudioUsagePanel />

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

    <!-- 最近 BLAST 任务 -->
    <section class="arco-card recent-tasks animate-fade-in-up delay-300">
      <div class="arco-card-header">
        <h3 class="arco-card-title">最近 BLAST 任务</h3>
        <NButton text size="small" class="view-all-btn" @click="router.push('/tools/blast/tasks')">
          查看全部 →
        </NButton>
      </div>
      <NSpin :show="loadingBlastTasks">
        <NDataTable
          v-if="blastTasks.length > 0"
          :columns="blastColumns"
          :data="blastTasks"
          :bordered="false"
          size="small"
          :single-line="false"
          class="recent-table"
        />
        <NEmpty v-else description="暂无 BLAST 任务">
          <template #extra>
            <div class="empty-extra">
              <p>点击上方按钮提交您的第一个 BLAST 查询</p>
              <NButton type="primary" @click="router.push('/tools/blast')">
                <template #icon>
                  <NIcon><SearchOutline /></NIcon>
                </template>
                提交 BLAST 查询
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

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trend-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
}

.trend-up {
  background: var(--arco-success-light, #E8FFEA);
  color: var(--arco-success, #00B42A);
}

:root[data-theme="dark"] .trend-up {
  background: rgba(34, 197, 94, 0.15);
  color: #22C55E;
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
