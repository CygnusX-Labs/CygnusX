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
  (e: 'refresh'): void
  (e: 'delete', task: Task): void
}>()

const router = useRouter()
const deleteTarget = ref<Task | null>(null)

const statusMap: Record<string, { label: string; badge: string; dot: string; bar: string }> = {
  pending:   { label: '待审核', badge: 'bg-gray-100 text-gray-600',    dot: 'bg-gray-400',    bar: 'bg-gray-300' },
  queued:    { label: '排队中', badge: 'bg-amber-50 text-amber-600',   dot: 'bg-amber-400',   bar: 'bg-amber-400' },
  running:   { label: '运行中', badge: 'bg-blue-50 text-blue-600',     dot: 'bg-blue-500',    bar: 'bg-blue-500' },
  success:   { label: '已完成', badge: 'bg-emerald-50 text-emerald-600', dot: 'bg-emerald-500', bar: 'bg-emerald-500' },
  failed:    { label: '失败',   badge: 'bg-red-50 text-red-600',       dot: 'bg-red-500',     bar: 'bg-red-500' },
  cancelled: { label: '已取消', badge: 'bg-gray-100 text-gray-500',    dot: 'bg-gray-400',    bar: 'bg-gray-300' },
}

function cfg(status: string) {
  return statusMap[status] || statusMap.pending
}

function pct(task: Task): number {
  return Math.round(task.progress * 100)
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
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
    running: t.filter(x => x.status === 'running').length,
    success: t.filter(x => x.status === 'success').length,
    failed: t.filter(x => x.status === 'failed').length,
  }
})
</script>

<template>
  <div>
    <!-- 统计摘要条 -->
    <div class="flex items-center gap-5 mb-4 px-1">
      <div class="flex items-center gap-1.5 text-sm text-gray-500">
        <span class="w-2 h-2 rounded-full bg-gray-400"></span>
        共 <span class="font-medium text-gray-700">{{ stats.total }}</span> 个任务
      </div>
      <div v-if="stats.running" class="flex items-center gap-1.5 text-sm text-blue-600">
        <span class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
        {{ stats.running }} 运行中
      </div>
      <div v-if="stats.success" class="flex items-center gap-1.5 text-sm text-emerald-600">
        <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
        {{ stats.success }} 已完成
      </div>
      <div v-if="stats.failed" class="flex items-center gap-1.5 text-sm text-red-600">
        <span class="w-2 h-2 rounded-full bg-red-500"></span>
        {{ stats.failed }} 失败
      </div>
      <div class="ml-auto">
        <button
          class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
          title="刷新列表"
          @click="emit('refresh')"
        >
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          刷新
        </button>
      </div>
    </div>

    <!-- 表格卡片 -->
    <div class="bg-neutral-card rounded-xl border border-gray-200/60 shadow-sm overflow-hidden">
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
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[760px]">
          <thead>
            <tr class="border-b border-gray-100">
            <th v-if="showUser" class="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">用户</th>
            <th class="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">任务名称</th>
            <th class="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 w-[130px]">流程</th>
            <th class="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 w-[100px]">状态</th>
            <th class="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 w-[180px]">进度</th>
            <th class="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 w-[130px]">提交时间</th>
            <th class="text-right text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 w-[120px]">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in tasks"
            :key="task.id"
            class="border-b border-gray-50 last:border-b-0 hover:bg-gray-50/50 transition-colors group"
          >
            <!-- 用户 -->
            <td v-if="showUser" class="px-4 py-3">
              <span class="text-sm text-gray-600">{{ task.username || task.user_id }}</span>
            </td>

            <!-- 任务名称 -->
            <td class="px-4 py-3">
              <div class="flex items-center gap-2 min-w-0">
                <span
                  class="text-sm font-medium text-gray-800 truncate max-w-[280px]"
                  :title="task.name"
                >{{ task.name }}</span>
                <span
                  v-if="task.status === 'running'"
                  class="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"
                ></span>
              </div>
              <p v-if="task.error_message" class="text-xs text-red-400 mt-0.5 truncate max-w-[280px]" :title="task.error_message">
                {{ task.error_message }}
              </p>
            </td>

            <!-- 流程 -->
            <td class="px-4 py-3">
              <span class="inline-block font-mono text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded" :title="task.flow_id">
                {{ flowLabel(task.flow_id) }}
              </span>
            </td>

            <!-- 状态 Badge -->
            <td class="px-4 py-3">
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" :class="cfg(task.status).badge">
                <span class="w-1.5 h-1.5 rounded-full" :class="cfg(task.status).dot"></span>
                {{ cfg(task.status).label }}
              </span>
            </td>

            <!-- 进度条 -->
            <td class="px-4 py-3">
              <div class="flex items-center gap-2.5">
                <div class="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-500 ease-out"
                    :class="cfg(task.status).bar"
                    :style="{ width: `${pct(task)}%` }"
                  ></div>
                </div>
                <span class="text-xs font-medium tabular-nums w-8 text-right"
                  :class="task.status === 'failed' ? 'text-red-500' : 'text-gray-400'"
                >{{ pct(task) }}%</span>
              </div>
            </td>

            <!-- 时间 -->
            <td class="px-4 py-3">
              <span class="text-sm text-gray-400">{{ formatTime(task.created_at) }}</span>
            </td>

            <!-- 操作 -->
            <td class="px-4 py-3">
              <div class="flex items-center justify-end gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
                <!-- 查看详情 -->
                <button
                  class="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                  title="查看详情"
                  @click="router.push({ name: 'task-detail', params: { taskId: task.id } })"
                >
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>

                <!-- 查看报告 -->
                <button
                  v-if="task.status === 'success'"
                  class="p-1.5 rounded-lg text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                  title="查看报告"
                  @click="router.push({ path: '/reports', query: { taskId: task.id } })"
                >
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </button>

              <!-- 重新运行（暂无后端接口，禁用并提示） -->
                <NTooltip placement="top">
                  <template #trigger>
                    <button
                      v-if="isTerminal(task.status)"
                      disabled
                      class="p-1.5 rounded-lg text-gray-300 cursor-not-allowed"
                      title="重新运行"
                    >
                      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </button>
                  </template>
                  重新运行功能即将上线
                </NTooltip>

                <!-- 删除 -->
                <button
                  class="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                  title="删除任务"
                  @click="deleteTarget = task"
                >
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
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
  </div>
</template>
