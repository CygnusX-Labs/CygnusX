<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import type { Task } from '@/types'
import TaskTable from '@/components/task/TaskTable.vue'
import AppLoading from '@/components/AppLoading.vue'
import EmptyState from '@/components/EmptyState.vue'
import apiClient from '@/api/client'
import { useApi } from '@/composables/useApi'
import { NInput, NSelect, NButton, NIcon, useMessage } from 'naive-ui'
import { RefreshOutline, SearchOutline } from '@vicons/ionicons5'

const message = useMessage()

const statusFilter = ref<Task['status'] | 'all'>('all')
const searchQuery = ref('')
const knownCompletedTaskIds = ref(new Set<string>())
const hasInitializedTaskSnapshot = ref(false)

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '待审核', value: 'pending' },
  { label: '排队中', value: 'queued' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]

const {
  data: tasks,
  loading,
  execute: fetchTasks,
} = useApi<Task[]>(
  async () => {
    const res = await apiClient.get<{ items: Task[]; total: number }>('/tasks', {
      params: statusFilter.value === 'all' ? {} : { status: statusFilter.value },
    })
    return res.data.items
  },
  { initialData: [] },
)

const filteredTasks = computed(() => {
  let list = tasks.value || []
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.flow_id.toLowerCase().includes(q) ||
        (t.error_message || '').toLowerCase().includes(q),
    )
  }
  return list
})

watch(tasks, (nextTasks) => {
  const taskList = nextTasks ?? []
  const completedIds = new Set(
    taskList.filter((task) => task.status === 'success').map((task) => task.id),
  )

  if (hasInitializedTaskSnapshot.value) {
    const newlyCompleted = taskList.filter(
      (task) => task.status === 'success' && !knownCompletedTaskIds.value.has(task.id),
    )
    if (newlyCompleted.length) {
      const name = newlyCompleted[0].name
      const suffix = newlyCompleted.length > 1 ? `，另有 ${newlyCompleted.length - 1} 项已完成` : ''
      message.success(`⭐ 「${name}」分析已完成${suffix}`)
    }
  }

  knownCompletedTaskIds.value = completedIds
  hasInitializedTaskSnapshot.value = true
})

async function handleDelete(task: Task) {
  try {
    await apiClient.delete(`/tasks/${task.id}`)
    message.success(`已删除「${task.name}」`)
    await fetchTasks()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败，请稍后重试')
  }
}

onMounted(fetchTasks)
</script>

<template>
  <div class="page-container tasks-page">
    <div class="tasks-header">
      <div class="tasks-header__title">
        <h1 class="page-title">任务中心</h1>
        <p class="text-sm text-gray-400 mt-1">管理和监控所有生信分析任务的执行状态</p>
      </div>
      <div class="tasks-header__actions">
        <NInput
          v-model:value="searchQuery"
          placeholder="搜索任务名称、流程、错误信息..."
          clearable
          style="width: 260px"
        >
          <template #prefix>
            <NIcon :size="14"><SearchOutline /></NIcon>
          </template>
        </NInput>
        <NSelect
          v-model:value="statusFilter"
          :options="statusOptions"
          style="width: 140px"
          @update:value="fetchTasks"
        />
        <NButton @click="fetchTasks">
          <template #icon>
            <NIcon><RefreshOutline /></NIcon>
          </template>
          刷新
        </NButton>
      </div>
    </div>

    <div v-if="loading && !filteredTasks.length" class="tasks-loading">
      <AppLoading text="加载任务列表..." />
    </div>
    <EmptyState
      v-else-if="!filteredTasks.length"
      icon="🧪"
      :title="searchQuery || statusFilter !== 'all' ? '没有匹配的任务' : '暂时没有分析任务'"
      :description="searchQuery || statusFilter !== 'all' ? '请调整搜索关键词或筛选条件后重试。' : '前往分析中心提交第一个任务后，执行进度会显示在这里。'"
    />
    <TaskTable
      v-else
      :tasks="filteredTasks"
      :loading="loading"
      @refresh="fetchTasks"
      @delete="handleDelete"
    />
  </div>
</template>

<style scoped>
.tasks-page {
  min-height: 100%;
  background: var(--neutral-bg);
}

.tasks-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.tasks-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.tasks-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}

@media (max-width: 768px) {
  .tasks-header {
    flex-direction: column;
  }
  .tasks-header__actions {
    width: 100%;
    justify-content: flex-start;
  }
  .tasks-header__actions :deep(.n-input),
  .tasks-header__actions :deep(.n-select) {
    width: 100% !important;
  }
}
</style>
