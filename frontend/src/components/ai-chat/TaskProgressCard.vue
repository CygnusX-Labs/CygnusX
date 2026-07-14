<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { NProgress } from 'naive-ui'

interface Props {
  taskId: string
  progressUrl?: string
  resultUrl?: string
}

const props = withDefaults(defineProps<Props>(), {
  progressUrl: '',
  resultUrl: '',
})

interface ProgressEvent {
  task_id: string
  phase: string
  progress: number
  message: string
}

const phase = ref('PENDING')
const progress = ref(0)
const message = ref('等待进度...')
const status = ref<'pending' | 'running' | 'success' | 'error'>('pending')
const error = ref('')
let eventSource: EventSource | null = null

const displayPhase = computed(() => {
  const map: Record<string, string> = {
    PENDING: '等待中',
    ALIGNING: '多序列比对',
    BUILDING: '构建进化树',
    BOOTSTRAPPING: 'Bootstrap 评估',
    FORMATTING: '格式化结果',
    COMPLETED: '已完成',
    FAILED: '失败',
  }
  return map[phase.value] || phase.value
})

const nprogressStatus = computed(() => {
  if (status.value === 'success') return 'success'
  if (status.value === 'error') return 'error'
  return 'default'
})

function connect() {
  if (eventSource) return
  const url = props.progressUrl || `/api/v1/tasks/${props.taskId}/progress`
  eventSource = new EventSource(url)

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as ProgressEvent
      phase.value = data.phase || phase.value
      progress.value = Math.min(Math.max(data.progress || 0, 0), 1)
      message.value = data.message || message.value
      if (data.phase === 'COMPLETED') {
        status.value = 'success'
      } else if (data.phase === 'FAILED') {
        status.value = 'error'
      } else {
        status.value = 'running'
      }
    } catch {
      // 忽略解析失败的非 JSON 事件
    }
  }

  eventSource.onerror = () => {
    // 连接出错时关闭，避免无限重连拖死页面
    eventSource?.close()
    eventSource = null
  }
}

onMounted(connect)
onUnmounted(() => {
  eventSource?.close()
  eventSource = null
})
</script>

<template>
  <div class="task-progress-card" :class="status">
    <div class="task-header">
      <span class="task-icon">{{ status === 'success' ? '✅' : status === 'error' ? '❌' : '⏳' }}</span>
      <span class="task-title">异步任务 {{ taskId.slice(0, 8) }}</span>
      <span class="task-phase">{{ displayPhase }}</span>
    </div>
    <n-progress
      type="line"
      :percentage="Math.round(progress * 100)"
      :status="nprogressStatus"
      :show-indicator="true"
    />
    <div class="task-message">{{ message }}</div>
    <div v-if="resultUrl && status === 'success'" class="task-actions">
      <a :href="resultUrl" target="_blank">查看结果</a>
    </div>
    <div v-if="error" class="task-error">{{ error }}</div>
  </div>
</template>

<style scoped lang="scss">
.task-progress-card {
  margin-top: 12px;
  padding: 14px;
  background: var(--chat-surface, #f8f9fa);
  border: 1px solid var(--chat-border, #e8e8e8);
  border-radius: 8px;
}
.task-progress-card.success {
  border-color: #b7eb8f;
  background: #f6ffed;
}
.task-progress-card.error {
  border-color: #ffccc7;
  background: #fff2f0;
}
.task-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;
}
.task-icon {
  font-size: 16px;
}
.task-title {
  font-weight: 600;
  color: var(--chat-text-primary, #1a1a1a);
}
.task-phase {
  margin-left: auto;
  color: var(--chat-text-muted, #999);
}
.task-message {
  margin-top: 8px;
  font-size: 12px;
  color: var(--chat-text-secondary, #666);
}
.task-actions {
  margin-top: 10px;
  text-align: right;
}
.task-actions a {
  font-size: 12px;
  color: var(--chat-accent, #4f8ef7);
  text-decoration: none;
}
.task-actions a:hover {
  text-decoration: underline;
}
.task-error {
  margin-top: 8px;
  font-size: 12px;
  color: #d03050;
}
</style>
