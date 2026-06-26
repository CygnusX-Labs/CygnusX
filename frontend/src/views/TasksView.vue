<script setup lang="ts">
import type { Task } from '@/types'
import apiClient from '@/api/client'
import { NButton, NDataTable, NEmpty, NSpin, NTag, useMessage } from 'naive-ui'
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const message = useMessage()
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

const statusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '待审核',
    queued: '排队中',
    running: '运行中',
    success: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

const columns = [
  { title: '任务名称', key: 'name' },
  { title: '流程', key: 'flow_id' },
  {
    title: '状态',
    key: 'status',
    render: (row: Task) => h(NTag, { type: statusType(row.status), size: 'small', round: true }, { default: () => statusText(row.status) }),
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
  } catch (error) {
    console.error('获取任务列表失败', error)
    message.error('获取任务列表失败，请稍后重试')
    tasks.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchTasks)
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">任务中心</h1>
    <NSpin :show="loading">
      <div class="arco-card">
        <NDataTable
          v-if="tasks.length"
          :columns="columns"
          :data="tasks"
          :row-key="(row: Task) => row.id"
          :bordered="false"
          size="small"
        />
        <NEmpty v-else description="暂无任务" />
      </div>
    </NSpin>
  </div>
</template>
