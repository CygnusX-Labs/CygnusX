<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NForm, NFormItem, NInput, NSelect, NInputNumber, NButton,
  NSpace, NIcon, NDataTable, NTag, NProgress, NEmpty, NSpin, useMessage,
} from 'naive-ui'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { DownloadOutline, RefreshOutline, EyeOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import type { Task } from '@/types'

const router = useRouter()
const message = useMessage()

const accession = ref('')
const downloadMethod = ref<'aws' | 'aspera' | 'ftp'>('aws')
const multithreads = ref(4)
const awsThreads = ref(8)
const submitting = ref(false)

const tasks = ref<Task[]>([])
const loading = ref(false)

const methodOptions: SelectOption[] = [
  { label: 'AWS S3（推荐，最快）', value: 'aws' },
  { label: 'Aspera', value: 'aspera' },
  { label: 'FTP', value: 'ftp' },
]

function statusConfig(status: string) {
  const map: Record<string, { type: 'success' | 'warning' | 'error' | 'info' | 'default'; text: string }> = {
    success: { type: 'success', text: '已完成' },
    failed: { type: 'error', text: '失败' },
    running: { type: 'info', text: '运行中' },
    queued: { type: 'warning', text: '排队中' },
    pending: { type: 'warning', text: '待开始' },
    cancelled: { type: 'default', text: '已取消' },
  }
  return map[status] || { type: 'default', text: status }
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

const columns = computed<DataTableColumns<Task>>(() => [
  { title: '任务名称', key: 'name', ellipsis: { tooltip: true } },
  {
    title: '登录号',
    key: 'parameters',
    width: 160,
    render: (row) => String(row.parameters?.accession ?? '-'),
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
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
      percentage: Math.round((row.progress ?? 0) * 100),
      height: 6,
      color: { stops: ['#165DFF', '#6B8DD6'] },
      railColor: '#E5E6EB',
      showIndicator: false,
    }),
  },
  {
    title: '提交时间',
    key: 'created_at',
    width: 150,
    render: (row) => formatTime(row.created_at),
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row) => h(NButton, {
      size: 'tiny', quaternary: true, circle: true,
      onClick: () => router.push(`/tasks/${row.id}`),
    }, { icon: () => h(NIcon, null, { default: () => h(EyeOutline) }) }),
  },
])

async function fetchTasks() {
  loading.value = true
  try {
    const res = await apiClient.get<{ items: Task[]; total: number }>('/downloads')
    tasks.value = res.data.items ?? []
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!accession.value.trim()) {
    message.warning('请输入登录号')
    return
  }
  submitting.value = true
  try {
    const res = await apiClient.post<Task>('/downloads', {
      accession: accession.value.trim(),
      download_method: downloadMethod.value,
      multithreads: multithreads.value,
      aws_threads: awsThreads.value,
    })
    message.success('下载任务已提交')
    accession.value = ''
    await fetchTasks()
    // 跳转到任务详情查看实时进度/日志
    router.push(`/tasks/${res.data.id}`)
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    message.error(detail || '提交失败，请检查数据下载是否已启用')
  } finally {
    submitting.value = false
  }
}

onMounted(fetchTasks)
</script>

<template>
  <div class="downloads-page">
    <h1 class="page-title">数据下载</h1>
    <p class="page-desc">
      输入 EBI/NCBI 登录号（如 PRJNA1251654、SRRxxxxxx），异步下载测序数据。
      下载完成的 FASTQ 会自动出现在「数据管理」中，可直接用于分析流程。
    </p>

    <NCard class="form-card" :bordered="false">
      <NForm label-placement="left" label-width="120" require-mark-placement="right-hanging">
        <NFormItem label="登录号" required>
          <NInput
            v-model:value="accession"
            placeholder="PRJNA1251654 或 SRRxxxxxx"
            clearable
            @keyup.enter="submit"
          />
        </NFormItem>
        <NFormItem label="下载方式">
          <NSelect v-model:value="downloadMethod" :options="methodOptions" style="width: 280px" />
        </NFormItem>
        <NSpace>
          <NFormItem label="并发下载数">
            <NInputNumber v-model:value="multithreads" :min="1" :max="32" />
          </NFormItem>
          <NFormItem label="AWS 线程数">
            <NInputNumber v-model:value="awsThreads" :min="1" :max="64" />
          </NFormItem>
        </NSpace>
        <NFormItem label=" " :show-label="false">
          <NButton type="primary" :loading="submitting" @click="submit">
            <template #icon>
              <NIcon><DownloadOutline /></NIcon>
            </template>
            提交下载
          </NButton>
        </NFormItem>
      </NForm>
    </NCard>

    <NCard class="list-card" :bordered="false">
      <div class="card-header">
        <h3 class="card-title">下载任务</h3>
        <NButton text size="small" class="refresh-btn" @click="fetchTasks">
          <template #icon>
            <NIcon :size="16"><RefreshOutline /></NIcon>
          </template>
          刷新
        </NButton>
      </div>
      <NSpin :show="loading">
        <NDataTable
          v-if="tasks.length > 0"
          :columns="columns"
          :data="tasks"
          :bordered="false"
          size="small"
          :single-line="false"
        />
        <NEmpty v-else description="暂无下载任务">
          <template #extra>
            <p class="empty-hint">提交一个登录号开始下载数据</p>
          </template>
        </NEmpty>
      </NSpin>
    </NCard>
  </div>
</template>

<style scoped>
.downloads-page {
  padding: 24px;
  min-height: 100%;
  background: var(--neutral-bg);
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  line-height: 32px;
  color: var(--neutral-text-1);
  margin: 0 0 8px;
}

.page-desc {
  font-size: 13px;
  color: var(--neutral-text-3);
  margin: 0 0 24px;
}

.form-card,
.list-card {
  margin-bottom: 20px;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 0;
}

.refresh-btn {
  color: var(--arco-primary) !important;
}

.empty-hint {
  font-size: 13px;
  color: var(--neutral-text-3);
  margin: 0;
}
</style>
