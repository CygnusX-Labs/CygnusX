<script setup lang="ts">
import AppLoading from '@/components/AppLoading.vue'
import { NTooltip } from 'naive-ui'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { Task } from '@/types'

const props = withDefaults(defineProps<{
  tasks: Task[]
  showUser?: boolean
  loading?: boolean
}>(), {
  showUser: false,
  loading: false,
})

const emit = defineEmits<{
  (e: 'delete', task: Task): void
}>()

const router = useRouter()
const deleteTarget = ref<Task | null>(null)

const statusMap: Record<string, { label: string; badge: string; dot: string; bar: string }> = {
  pending:   { label: '待审核', badge: 'bg-gray-100 text-gray-600',    dot: 'bg-gray-400',    bar: 'bg-gray-300' },
  queued:    { label: '排队中', badge: 'bg-amber-50 text-amber-600',   dot: 'bg-amber-400',   bar: 'bg-amber-400' },
  running:   { label: '运行中', badge: 'bg-blue-50 text-blue-600',     dot: 'bg-blue-500',    bar: 'bg-blue-500' },
  success:   { label: '已完成', badge: 'bg-emerald-50 text-emerald-600', dot: 'bg-emerald-500', bar: 'bg-emerald-500' },
  failed:    { label: '失败',   badge: 'bg-red-50 text-red-600',       dot: 'bg-red-500',     bar: 'bg-gray-300' },
  cancelled: { label: '已取消', badge: 'bg-gray-100 text-gray-500',    dot: 'bg-gray-400',    bar: 'bg-gray-300' },
}

function cfg(status: string) {
  return statusMap[status] || statusMap.pending
}

function pct(task: Task): number {
  const progress = Number(task.progress)
  if (!Number.isFinite(progress)) return 0
  const percentage = progress > 1 ? progress : progress * 100
  return Math.round(Math.min(100, Math.max(0, percentage)))
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// 失败任务的 error_message 可能极长（如整段 docker socket 报错），
// 在格子里只展示前 N 个字符 + 省略号，完整内容交给 title 悬浮查看；
// 从源头保证名称列内容为短文本，绝不撑宽固定列（§33.2 ③ / §5.4 长文本省略）。
function truncError(msg: string | null | undefined, max = 28): string {
  if (!msg) return ''
  const t = msg.replace(/\s+/g, ' ').trim()
  return t.length > max ? `${t.slice(0, max).trimEnd()}…` : t
}

function flowLabel(flowId: string): string {
  const labels: Record<string, string> = {
    'rna-seq': 'RNA-seq',
    'atac-seq': 'ATAC-seq',
    'rna_seq': 'RNA-seq',
    'atac_seq': 'ATAC-seq',
    'ebi_download': 'Data Download',
    'variant_calling': 'Variant Calling',
    'spatial-transcriptomics': 'Spatial TX',
    'scrna-seq': 'scRNA-seq',
    studio_sandbox: 'AI 工作台',
    mas: 'MAS 多智能体',
  }
  return labels[flowId] || flowId
}

function isTerminal(status: string): boolean {
  return ['success', 'failed', 'cancelled'].includes(status)
}

function confirmDelete() {
  if (deleteTarget.value) {
    emit('delete', deleteTarget.value)
    deleteTarget.value = null
  }
}

const stats = computed(() => {
  const t = props.tasks
  return {
    total: t.length,
    success: t.filter(x => x.status === 'success').length,
    failed: t.filter(x => x.status === 'failed').length,
  }
})
</script>

<template>
  <section class="task-list">
    <!-- 统计摘要条 -->
    <div class="task-stats" aria-label="任务统计">
      <div class="task-stat-chip task-stat-chip--total">
        <span class="task-stat-chip__dot"></span>
        共 <strong>{{ stats.total }}</strong> 个任务
      </div>
      <div class="task-stat-chip task-stat-chip--success">
        <span class="task-stat-chip__dot"></span>
        <strong>{{ stats.success }}</strong> 已完成
      </div>
      <div class="task-stat-chip task-stat-chip--failed">
        <span class="task-stat-chip__dot"></span>
        <strong>{{ stats.failed }}</strong> 失败
      </div>
    </div>

    <!-- 表格卡片 -->
    <div class="task-table-card omichub-card">
      <!-- 空状态 -->
      <div v-if="!loading && tasks.length === 0" class="flex flex-col items-center py-16 px-6">
        <svg class="w-16 h-16 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <p class="text-sm font-medium text-gray-500 mb-1">暂无分析任务</p>
        <p class="text-xs text-gray-400 mb-4">前往分析流程中心提交你的第一个生信分析任务</p>
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
          @click="router.push('/flows')"
        >
          去提交任务
        </button>
      </div>

      <!-- 表格容器 -->
      <div v-else class="task-table-wrapper">
        <table class="task-table">
          <colgroup>
            <col v-if="showUser" class="task-user-column">
            <col class="task-name-column">
            <col class="task-flow-column">
            <col class="task-status-column">
            <col class="task-progress-column">
            <col class="task-time-column">
            <col class="task-actions-column">
          </colgroup>
          <thead>
            <tr>
            <th v-if="showUser" class="task-user-column">用户</th>
            <th class="task-name-column">任务名称</th>
            <th class="task-flow-column">流程</th>
            <th class="task-status-column">状态</th>
            <th class="task-progress-column">进度</th>
            <th class="task-time-column">提交时间</th>
            <th class="task-actions-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in tasks"
            :key="task.id"
            class="task-table__row"
          >
            <!-- 用户 -->
            <td v-if="showUser" class="task-user-column">
              <span class="task-user-name">{{ task.username || task.user_id }}</span>
            </td>

            <!-- 任务名称 -->
            <td class="task-name-column">
              <div class="task-name">
                <span class="task-name__text" :title="task.name">{{ task.name }}</span>
                <span
                  v-if="task.status === 'running'"
                  class="task-name__running-dot"
                ></span>
              </div>
              <p v-if="task.error_message" class="task-name__error" :title="task.error_message">
                {{ truncError(task.error_message) }}
              </p>
            </td>

            <!-- 流程 -->
            <td class="task-flow-column">
              <span class="task-flow-name" :title="task.flow_id">
                {{ flowLabel(task.flow_id) }}
              </span>
            </td>

            <!-- 状态 Badge -->
            <td class="task-status-column">
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" :class="cfg(task.status).badge">
                <span class="w-1.5 h-1.5 rounded-full" :class="cfg(task.status).dot"></span>
                {{ cfg(task.status).label }}
              </span>
            </td>

            <!-- 进度条 -->
            <td class="task-progress-column">
              <div class="task-progress">
                <div class="task-progress__track">
                  <div
                    class="task-progress__bar"
                    :class="cfg(task.status).bar"
                    :style="{ width: `${pct(task)}%` }"
                  ></div>
                </div>
                <span class="task-progress__value">{{ pct(task) }}%</span>
              </div>
            </td>

            <!-- 时间 -->
            <td class="task-time-column">
              <span class="task-time">{{ formatTime(task.created_at) }}</span>
            </td>

            <!-- 操作 -->
            <td class="task-actions-column">
              <div class="task-actions">
                <!-- 查看详情 -->
                <NTooltip placement="top">
                  <template #trigger>
                    <button class="task-action" aria-label="查看详情" @click="router.push({ name: 'task-detail', params: { taskId: task.id } })">
                      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                    </button>
                  </template>
                  查看详情
                </NTooltip>

                <!-- 查看报告 -->
                <NTooltip v-if="task.status === 'success'" placement="top">
                  <template #trigger>
                    <button class="task-action" aria-label="查看报告" @click="router.push({ path: '/reports', query: { taskId: task.id } })">
                      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                      </svg>
                    </button>
                  </template>
                  查看报告
                </NTooltip>

              <!-- 重新运行（暂无后端接口，禁用并提示） -->
                <NTooltip v-if="isTerminal(task.status)" placement="top">
                  <template #trigger>
                    <span class="task-action-wrapper">
                      <button disabled class="task-action" aria-label="重新运行">
                      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      </button>
                    </span>
                  </template>
                  重新运行功能即将上线
                </NTooltip>

                <!-- 删除 -->
                <NTooltip v-if="task.execution_mode !== 'mas'" placement="top">
                  <template #trigger>
                    <button class="task-action task-action--delete" aria-label="删除任务" @click="deleteTarget = task">
                      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </template>
                  删除任务
                </NTooltip>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      </div>

      <!-- 加载态 -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <AppLoading text="加载中..." size="small" />
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div
        v-if="deleteTarget"
        class="fixed inset-0 z-[9999] flex items-center justify-center"
      >
        <div class="absolute inset-0 bg-black/30 backdrop-blur-sm" @click="deleteTarget = null"></div>
        <div class="relative bg-neutral-card rounded-2xl shadow-xl border border-gray-200 p-6 w-[400px] mx-4">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
              <svg class="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>
            <div>
              <h3 class="text-base font-semibold text-gray-900">确认删除任务</h3>
              <p class="text-sm text-gray-500 mt-0.5">此操作不可恢复，将同时清理关联的计算资源</p>
            </div>
          </div>
          <div class="bg-gray-50 rounded-lg px-3 py-2 mb-5">
            <p class="text-sm font-medium text-gray-700 truncate">{{ deleteTarget.name }}</p>
            <p class="text-xs text-gray-400 font-mono mt-0.5">{{ deleteTarget.flow_id }}</p>
          </div>
          <div class="flex justify-end gap-2">
            <button
              class="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
              @click="deleteTarget = null"
            >
              取消
            </button>
            <button
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
              @click="confirmDelete"
            >
              确认删除
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.task-list {
  min-width: 0;
}

.task-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px;
}

.task-stat-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 0 11px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--neutral-text-2);
  font-size: 13px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.task-stat-chip strong {
  color: var(--neutral-text-1);
  font-weight: 650;
}

.task-stat-chip__dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: #9ca3af;
}

.task-stat-chip--success .task-stat-chip__dot { background: #10b981; }
.task-stat-chip--failed .task-stat-chip__dot { background: #ef4444; }

.task-table-card {
  overflow: hidden;
  border: 1px solid var(--neutral-border);
  border-radius: var(--radius-card);
  background: var(--neutral-card);
  box-shadow: var(--shadow-card);
}

/* 宽屏表格铺满整行；列宽之和大于容器时退化为横向滚动，保证「操作」列永不被裁切（§33.2 / §7.1） */
.task-table-wrapper {
  width: 100%;
  overflow-x: auto;
}

/* 列宽策略：每列都给固定 width（无 auto 列），表格 width:100% 按比例铺满卡片，
   杜绝最初「名称列独吞余量 ballooning」的根因（CSS2 §17.5.2.1：余量只灌进 auto 列）。
   max-width 封顶读宽（与 §4.3 配置中心 1440 同惯例）：普通屏铺满零空白、名称列温和；
   超宽屏表格不再无限拉宽，名称列封顶 ~377px、右侧空白封顶不刺眼。
   窄屏列宽之和 > 容器时由 .task-table-wrapper 横向滚动兜底（§33.2 / §7.1）。 */
.task-table {
  width: 100%;
  max-width: 1440px;
  table-layout: fixed;
  border-collapse: collapse;
}

/* 全部列固定宽，禁止弹性列吞宽度；长文本「任务名称」给克制固定宽 + 省略（§33.2 ③） */
.task-user-column { width: 120px; }
.task-name-column { width: 260px; }
.task-flow-column { width: 140px; }
.task-status-column { width: 104px; }
.task-progress-column { width: 190px; }
.task-time-column { width: 132px; }
.task-actions-column { width: 144px; }

.task-table th {
  height: 42px;
  padding: 0 16px;
  border-bottom: 1px solid var(--neutral-border);
  background: var(--neutral-bg);
  color: var(--neutral-text-3);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-align: left;
}

/* 短值/离散列表头居中，与表体一致（贴合仪表盘任务表样板，§33.2 ③） */
.task-table th.task-user-column,
.task-table th.task-flow-column,
.task-table th.task-status-column,
.task-table th.task-actions-column {
  text-align: center;
}

.task-table td {
  height: 60px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--neutral-border);
  color: var(--neutral-text-1);
  font-size: 13px;
  vertical-align: middle;
}

.task-table__row {
  transition: background-color var(--motion-quick, 160ms) ease-out;
}

.task-table__row:hover { background: var(--neutral-hover); }
.task-table__row:last-child td { border-bottom: 0; }
.task-table td.task-user-column,
.task-table td.task-flow-column,
.task-table td.task-status-column,
.task-table td.task-actions-column { text-align: center; }

.task-user-name,
.task-time {
  display: block;
  overflow: hidden;
  color: var(--neutral-text-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-name {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.task-name__text,
.task-name__error,
.task-flow-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-name__text {
  color: var(--neutral-text-1);
  font-size: 14px;
  font-weight: 600;
}

.task-name__running-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border-radius: 50%;
  background: var(--arco-primary);
  animation: task-running-pulse 1.8s ease-in-out infinite;
}

.task-name__error {
  margin: 3px 0 0;
  color: #ef4444;
  font-size: 12px;
}

.task-flow-name {
  display: block;
  color: var(--neutral-text-2);
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 12px;
  text-align: center;
}

.task-progress {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.task-progress__track {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  border-radius: 999px;
  background: var(--neutral-border);
  height: 6px;
}

.task-progress__bar {
  height: 100%;
  border-radius: inherit;
  transition: width 300ms ease-out;
}

.task-progress__value {
  flex: 0 0 48px;
  color: var(--neutral-text-2);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  text-align: right;
  white-space: nowrap;
}

.task-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.task-action,
.task-action-wrapper {
  display: inline-flex;
}

.task-action {
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  transition: background-color var(--motion-quick, 160ms) ease-out, color var(--motion-quick, 160ms) ease-out;
}

.task-action svg {
  width: 18px;
  height: 18px;
}

.task-action:hover:not(:disabled),
.task-action:focus-visible:not(:disabled) {
  background: color-mix(in srgb, var(--arco-primary) 10%, transparent);
  color: var(--arco-primary);
  outline: none;
}

.task-action--delete:hover:not(:disabled),
.task-action--delete:focus-visible:not(:disabled) {
  background: #fef2f2;
  color: #ef4444;
}

.task-action:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

@keyframes task-running-pulse {
  50% { opacity: 0.35; transform: scale(0.8); }
}

@media (max-width: 960px) {
  .task-name-column { width: 220px; }
  .task-time-column { display: none; }
  .task-actions-column { width: 132px; }
}

@media (max-width: 720px) {
  .task-name-column { width: 188px; }
  .task-flow-column { display: none; }
  .task-table th,
  .task-table td { padding-right: 12px; padding-left: 12px; }
  .task-progress-column { width: 152px; }
  .task-actions-column { width: 120px; }
  .task-actions { gap: 4px; }
}

@media (max-width: 560px) {
  .task-name-column { width: 160px; }
  .task-status-column { display: none; }
  .task-progress-column { width: 136px; }
  .task-actions-column { width: 112px; }
}

@media (prefers-reduced-motion: reduce) {
  .task-name__running-dot { animation: none; }
  .task-progress__bar,
  .task-table__row,
  .task-action { transition: none; }
}

/* 表格表面/分隔线/行悬停/进度轨道全部消费 --neutral-* 语义令牌（自带明暗成对值），
   无需再写 :global([data-theme='dark']) 硬编码补丁（§3.1 / §33.2 ⑦）。
   统计胶囊在深色下回退页面底色，避免与卡片表面混色。 */
:global(:root[data-theme='dark']) .task-stat-chip { background: var(--neutral-bg); }
</style>
