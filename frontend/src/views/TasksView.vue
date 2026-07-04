<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { Task } from '@/types'
import TaskTable from '@/components/task/TaskTable.vue'
import { useMessage } from 'naive-ui'

const message = useMessage()
const tasks = ref<Task[]>([])
const loading = ref(false)

const MOCK_TASKS: Task[] = [
  {
    id: 't-001', flow_id: 'rna-seq', user_id: 'u-1001', username: 'zhang_san',
    name: '番茄叶片 RNA-seq 差异表达分析', status: 'running', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0.62, logs: [], created_at: '2026-07-03T09:12:00',
    started_at: '2026-07-03T09:13:00', finished_at: null,
  },
  {
    id: 't-002', flow_id: 'ebi_download', user_id: 'u-1002', username: 'li_si',
    name: 'EBI PRJEB12345 原始数据下载', status: 'failed', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '远程连接超时，FTP 服务器无响应',
    progress: 0.18, logs: [], created_at: '2026-07-03T08:40:00',
    started_at: '2026-07-03T08:41:00', finished_at: '2026-07-03T09:05:00',
  },
  {
    id: 't-003', flow_id: 'atac-seq', user_id: 'u-1003', username: 'wang_wu',
    name: '拟南芥根尖 ATAC-seq 开放区域检测', status: 'success', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '/results/atac-seq/t-003', error_message: '',
    progress: 1, logs: [], created_at: '2026-07-02T16:20:00',
    started_at: '2026-07-02T16:21:00', finished_at: '2026-07-02T18:02:00',
  },
  {
    id: 't-004', flow_id: 'rna-seq', user_id: 'u-1001', username: 'zhang_san',
    name: '黄瓜果实转录组时间序列分析', status: 'queued', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0, logs: [], created_at: '2026-07-03T09:30:00',
    started_at: null, finished_at: null,
  },
  {
    id: 't-005', flow_id: 'variant_calling', user_id: 'u-1004', username: 'zhao_liu',
    name: '水稻群体 128 份种质 SNP/InDel 变异检测', status: 'pending', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0, logs: [], created_at: '2026-07-03T09:45:00',
    started_at: null, finished_at: null,
  },
  {
    id: 't-006', flow_id: 'spatial-transcriptomics', user_id: 'u-1005', username: 'chen_qi',
    name: '小鼠脑组织 10x Visium 空间转录组聚类', status: 'running', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0.35, logs: [], created_at: '2026-07-03T07:50:00',
    started_at: '2026-07-03T07:52:00', finished_at: null,
  },
  {
    id: 't-007', flow_id: 'scrna-seq', user_id: 'u-1003', username: 'wang_wu',
    name: '人 PBMC 单细胞转录组质控与降维', status: 'success', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '/results/scrna-seq/t-007', error_message: '',
    progress: 1, logs: [], created_at: '2026-07-01T14:10:00',
    started_at: '2026-07-01T14:11:00', finished_at: '2026-07-01T15:48:00',
  },
  {
    id: 't-008', flow_id: 'ebi_download', user_id: 'u-1006', username: 'sun_ba',
    name: 'EBI PRJNA678901 双端测序数据批量下载', status: 'cancelled', execution_mode: 'celery',
    parameters: {}, work_dir: '', result_path: '', error_message: '',
    progress: 0.42, logs: [], created_at: '2026-07-02T11:00:00',
    started_at: '2026-07-02T11:01:00', finished_at: '2026-07-02T11:35:00',
  },
]

function fetchTasks() {
  loading.value = true
  setTimeout(() => {
    tasks.value = [...MOCK_TASKS]
    loading.value = false
  }, 600)
}

function handleDelete(task: Task) {
  tasks.value = tasks.value.filter(t => t.id !== task.id)
  message.success(`已删除「${task.name}」`)
}

onMounted(fetchTasks)
</script>

<template>
  <div class="page-container">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="page-title">任务中心</h1>
        <p class="text-sm text-gray-400 mt-1">管理和监控所有生信分析任务的执行状态</p>
      </div>
    </div>

    <TaskTable
      :tasks="tasks"
      :loading="loading"
      @refresh="fetchTasks"
      @delete="handleDelete"
    />
  </div>
</template>
