<script setup lang="ts">
import type { Task } from '@/types'
import { apiClient } from '@/api'
import { NButton, NCard, NDataTable, NEmpty, NSpin, NTag } from 'naive-ui'
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const tasks = ref<Task[]>([])
const loading = ref(false)

const statusType = (status: string) => {
  const map: Record<string, 'default' | 'success' | 'warning' | 'error'> = {
    pending: 'default',
    queued: 'warning',
    running: 'warning',
    success: 'success',
    failed: 'error',
    cancelled: 'default',
  }
  return map[status] || 'default'
}

const columns = [
  { title: '任务名称', key: 'name' },
  { title: '流程', key: 'flow_id' },
  {
    title: '状态',
    key: 'status',
    render: (row: Task) => h(NTag, { type: statusType(row.status) }, { default: () => row.status }),
  },
  {
    title: '进度',
    key: 'progress',
    render: (row: Task) => `${Math.round(row.progress * 100)}%`,
  },
  { title: '创建时间', key: 'created_at' },
  {
    title: '操作',
    key: 'actions',
    render: (row: Task) =>
      h(
        NButton,
        {
          text: true,
          type: 'primary',
          onClick: () => router.push({ name: 'task-detail', params: { taskId: row.id } }),
        },
        { default: () => '详情' },
      ),
  },
]

async function fetchTasks() {
  loading.value = true
  try {
    const res = await apiClient.get<{ items: Task[]; total: number }>('/tasks')
    tasks.value = res.data.items
  } finally {
    loading.value = false
  }
}

onMounted(fetchTasks)
</script>

<template>
  <div class="tasks-view">
    <h2>任务管理</h2>
    <NSpin :show="loading">
      <NCard>
        <NDataTable
          v-if="tasks.length"
          :columns="columns"
          :data="tasks"
          :row-key="(row: Task) => row.id"
        />
        <NEmpty v-else description="暂无任务" />
      </NCard>
    </NSpin>
  </div>
</template>

<style scoped>
.tasks-view {
  padding: 24px;
}
</style>
