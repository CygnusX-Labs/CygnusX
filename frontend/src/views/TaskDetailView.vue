<script setup lang="ts">
import type { Task, TaskLog } from '@/types'
import apiClient from '@/api/client'
import {
  NAlert,
  NBreadcrumb,
  NBreadcrumbItem,
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NProgress,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const taskId = computed(() => route.params.taskId as string)

const task = ref<Task | null>(null)
const logs = ref<TaskLog[]>([])
const loading = ref(false)
const error = ref('')
const socket = ref<WebSocket | null>(null)

const dag = ref<{ status: string; format?: string; content?: string; error?: string } | null>(null)
const dagLoading = ref(false)

const statusType = computed(() => {
  const map: Record<string, 'default' | 'success' | 'warning' | 'error'> = {
    pending: 'default',
    queued: 'warning',
    running: 'warning',
    success: 'success',
    failed: 'error',
    cancelled: 'default',
  }
  return map[task.value?.status || 'pending'] || 'default'
})

const statusText = computed(() => {
  const map: Record<string, string> = {
    pending: '待审核',
    queued: '排队中',
    running: '运行中',
    success: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[task.value?.status || 'pending'] || task.value?.status || '未知'
})

const TERMINAL_STATUSES = ['success', 'failed', 'cancelled']
let pollTimer: ReturnType<typeof setInterval> | null = null

function isTerminalStatus(status?: string): boolean {
  return TERMINAL_STATUSES.includes(status || '')
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => fetchTask(true), 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function fetchTask(silent = false) {
  if (!silent) loading.value = true
  if (!silent) error.value = ''
  try {
    const res = await apiClient.get<Task>(`/tasks/${taskId.value}`)
    task.value = res.data
    // 仅首次（非静默）拉取历史日志；运行中由 WebSocket 维护 logs，
    // 轮询只更新 task（status/progress），不覆盖 logs 以防日志面板跳动/丢失在途行
    if (!silent) logs.value = res.data.logs || []
    if (isTerminalStatus(res.data.status)) stopPolling()
  } catch (e: any) {
    if (!silent) error.value = e.response?.data?.detail || '获取任务详情失败'
  } finally {
    if (!silent) loading.value = false
  }
}

async function fetchDag() {
  dagLoading.value = true
  try {
    const res = await apiClient.get(`/tasks/${taskId.value}/dag`)
    dag.value = res.data
  } catch (e: any) {
    dag.value = { status: 'failed', error: e.response?.data?.detail || '生成 DAG 失败' }
  } finally {
    dagLoading.value = false
  }
}

function connectWebSocket() {
  const token = localStorage.getItem('access_token')
  if (!token) return

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/v1/tasks/${taskId.value}/ws?token=${token}`

  const ws = new WebSocket(wsUrl)
  socket.value = ws

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as TaskLog
      logs.value.push(data)
    } catch {
      logs.value.push({
        timestamp: new Date().toISOString(),
        level: 'info',
        message: event.data,
        source: 'websocket',
      })
    }
  }

  ws.onerror = () => {
    error.value = 'WebSocket 连接失败'
  }

  ws.onclose = () => {
    socket.value = null
  }
}

function disconnectWebSocket() {
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
}

onMounted(async () => {
  await fetchTask()
  connectWebSocket()
  if (!isTerminalStatus(task.value?.status)) startPolling()
})

onUnmounted(() => {
  stopPolling()
  disconnectWebSocket()
})

watch(taskId, async () => {
  stopPolling()
  disconnectWebSocket()
  await fetchTask()
  connectWebSocket()
  if (!isTerminalStatus(task.value?.status)) startPolling()
})
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">任务详情</h1>
    <NBreadcrumb class="task-breadcrumb">
      <NBreadcrumbItem>任务中心</NBreadcrumbItem>
      <NBreadcrumbItem>任务详情</NBreadcrumbItem>
    </NBreadcrumb>

    <NAlert v-if="error" type="error" :title="error" />

    <NCard v-if="task" title="任务概览" :bordered="false" class="arco-card overview-card">
      <NSpace vertical>
        <NDescriptions :columns="3" bordered>
          <NDescriptionsItem label="任务名称">{{ task.name }}</NDescriptionsItem>
          <NDescriptionsItem label="流程">{{ task.flow_id }}</NDescriptionsItem>
          <NDescriptionsItem label="状态">
            <NTag :type="statusType" round>{{ statusText }}</NTag>
          </NDescriptionsItem>
          <NDescriptionsItem label="执行模式">{{ task.execution_mode }}</NDescriptionsItem>
          <NDescriptionsItem label="工作目录">{{ task.work_dir }}</NDescriptionsItem>
          <NDescriptionsItem label="创建时间">{{ task.created_at }}</NDescriptionsItem>
        </NDescriptions>
        <NProgress
          :percentage="Math.round(task.progress * 100)"
          :status="task.status === 'failed' ? 'error' : 'success'"
          :indicator-text-color="task.status === 'failed' ? 'var(--arco-danger)' : 'var(--arco-success)'"
        />
      </NSpace>
    </NCard>

    <NTabs type="line" animated>
      <NTabPane name="logs" tab="实时日志">
        <NCard :bordered="false" class="arco-card logs-card">
          <div class="log-container">
            <div
              v-for="(log, index) in logs"
              :key="index"
              class="log-line"
              :class="`level-${log.level}`"
            >
              <span class="log-time">{{ log.timestamp }}</span>
              <span class="log-level">{{ log.level.toUpperCase() }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
            <div v-if="logs.length === 0" class="empty-logs">暂无日志</div>
          </div>
        </NCard>
      </NTabPane>

      <NTabPane name="dag" tab="DAG 可视化">
        <NCard :bordered="false" class="arco-card dag-card">
          <NSpace vertical>
            <NButton type="primary" :loading="dagLoading" @click="fetchDag">
              生成 DAG
            </NButton>
            <NAlert v-if="dag?.status === 'failed'" type="error" :title="dag.error || '生成失败'" />
            <div v-else-if="dag?.format === 'svg'" class="dag-svg" v-html="dag.content" />
            <pre v-else-if="dag?.format === 'dot'" class="dag-dot">{{ dag.content }}</pre>
            <div v-else-if="dag === null" class="empty-dag">点击上方按钮生成 DAG</div>
          </NSpace>
        </NCard>
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
.task-breadcrumb {
  margin-bottom: 16px;
}

.overview-card {
  margin-bottom: 24px;
}

.logs-card {
  margin-top: 16px;
}

.log-container {
  max-height: 600px;
  overflow-y: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  background-color: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 8px;
}

.log-line {
  display: flex;
  gap: 12px;
  padding: 2px 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-time {
  color: #858585;
  min-width: 180px;
}

.log-level {
  min-width: 60px;
  font-weight: bold;
}

.level-error .log-level {
  color: #f14c4c;
}

.level-warning .log-level {
  color: #f5a623;
}

.level-info .log-level {
  color: #4ec9b0;
}

.level-debug .log-level {
  color: #9cdcfe;
}

.empty-logs {
  color: #858585;
  text-align: center;
  padding: 24px;
}

.dag-card {
  min-height: 400px;
  margin-top: 16px;
}

.dag-svg {
  overflow-x: auto;
}

.dag-svg svg {
  max-width: 100%;
  height: auto;
}

.dag-dot {
  background-color: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  white-space: pre;
}

.empty-dag {
  color: var(--neutral-text-3);
  text-align: center;
  padding: 48px;
}
</style>
