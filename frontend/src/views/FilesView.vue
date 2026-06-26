<script setup lang="ts">
import type { DataFile } from '@/types'
import apiClient from '@/api/client'
import { CloudUploadOutline, DocumentOutline, FolderOpenOutline } from '@vicons/ionicons5'
import { NButton, NDataTable, NEmpty, NIcon, NSpin, NTag, useMessage } from 'naive-ui'
import { h, onMounted, ref } from 'vue'

const message = useMessage()
const files = ref<DataFile[]>([])
const loading = ref(false)

function formatSize(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(2)} ${sizes[i]}`
}

const fileTypeText: Record<string, string> = {
  fastq: 'FASTQ',
  bam: 'BAM',
  vcf: 'VCF',
  count_matrix: '表达矩阵',
  h5ad: 'H5AD',
  rds: 'RDS',
  meta: '元数据',
  report: '报告',
  image: '图片',
  other: '其他',
}

const columns = [
  {
    title: '文件名',
    key: 'original_name',
    render: (row: DataFile) =>
      h('div', { class: 'file-name-cell' }, [
        h(NIcon, { size: 18 }, { default: () => h(DocumentOutline) }),
        h('span', null, row.original_name),
      ]),
  },
  {
    title: '类型',
    key: 'file_type',
    width: 120,
    render: (row: DataFile) => h(NTag, { size: 'small', round: true }, { default: () => fileTypeText[row.file_type] || '其他' }),
  },
  {
    title: '大小',
    key: 'size',
    width: 120,
    render: (row: DataFile) => formatSize(row.size),
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
  },
]

async function fetchFiles() {
  loading.value = true
  try {
    const res = await apiClient.get<{ items: DataFile[]; total: number }>('/files')
    files.value = res.data.items
  } catch (error) {
    console.error('获取文件列表失败', error)
    message.error('获取文件列表失败，请稍后重试')
    files.value = []
  } finally {
    loading.value = false
  }
}

function handleUpload() {
  message.info('文件上传功能即将上线，敬请期待')
}

onMounted(fetchFiles)
</script>

<template>
  <div class="page-container">
    <div class="files-header">
      <div>
        <h1 class="page-title" style="margin-bottom: 8px;">数据管理</h1>
        <p class="page-subtitle">管理您的样本数据与分析输入文件</p>
      </div>
      <NButton type="primary" disabled @click="handleUpload">
        <template #icon>
          <NIcon><CloudUploadOutline /></NIcon>
        </template>
        上传样本数据
      </NButton>
    </div>

    <NSpin :show="loading">
      <div class="arco-card">
        <NDataTable
          v-if="files.length"
          :columns="columns"
          :data="files"
          :row-key="(row: DataFile) => row.id"
          :bordered="false"
          size="small"
        />
        <NEmpty v-else>
          <template #icon>
            <NIcon :size="48"><FolderOpenOutline /></NIcon>
          </template>
          <template #default>
            <div style="text-align: center;">
              <p>暂无文件</p>
              <p style="font-size: 13px; color: var(--neutral-text-3);">上传功能即将上线，请先通过分析流程提交任务生成结果文件</p>
            </div>
          </template>
        </NEmpty>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.files-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 768px) {
  .files-header {
    flex-direction: column;
  }
}
</style>
