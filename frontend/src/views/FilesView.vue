<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { DataFile, Directory, QuotaInfo } from '@/types'
import apiClient from '@/api/client'
import {
  CloudUploadOutline, SearchOutline, FolderOpenOutline, ScanOutline,
  CloudDownloadOutline, GlobeOutline, LinkOutline, GridOutline, ListOutline,
  DocumentTextOutline, RefreshOutline, EllipsisHorizontalOutline, DownloadOutline,
  CreateOutline, TrashOutline,
} from '@vicons/ionicons5'
import {
  NButton, NBreadcrumb, NBreadcrumbItem, NDataTable, NDropdown, NIcon, NInput,
  NSelect, NSpin, NTag, NUpload, useDialog, useMessage,
} from 'naive-ui'
import type { DataTableColumns, UploadFileInfo } from 'naive-ui'
import DirectoryTree from '@/components/DirectoryTree.vue'
import OverviewStats from '@/components/data-management/OverviewStats.vue'
import StorageOverviewWidget from '@/components/data-management/StorageOverviewWidget.vue'
import RecentActivitiesWidget from '@/components/data-management/RecentActivitiesWidget.vue'
import FileDetailPanel from '@/components/data-management/FileDetailPanel.vue'
import JBrowseLinkGenerator from '@/components/data-management/JBrowseLinkGenerator.vue'
import { useUploadStore } from '@/stores/upload'
import { storeToRefs } from 'pinia'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const treeRef = ref<InstanceType<typeof DirectoryTree>>()
const uploadStore = useUploadStore()
const { completedSeq } = storeToRefs(uploadStore)

const allFiles = ref<DataFile[]>([])
const directories = ref<Directory[]>([])
const samplesCount = ref(0)
const quota = ref<QuotaInfo>({ used: 0, total: 0, percent: 0 })
const loading = ref(false)
const currentDirectory = ref('')
const siderWidth = ref(280)

// Finder 状态
const viewMode = ref<'list' | 'grid'>('list')
const searchQuery = ref('')
const sortBy = ref<'name' | 'size' | 'time'>('time')
const selectedFile = ref<DataFile | null>(null)
const showJbrowseLinkGen = ref(false)

function formatSize(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(2)} ${sizes[i]}`
}

const projectsCount = computed(
  () => directories.value.filter((d) => !d.parent_path && !d.is_system).length,
)

/** 每个目录的直接文件计数（供 DirectoryTree 显示） */
const fileCounts = computed<Record<string, number>>(() => {
  const m: Record<string, number> = {}
  for (const f of allFiles.value) {
    const dir = f.directory || ''
    m[dir] = (m[dir] || 0) + 1
  }
  return m
})

/** 当前目录下的文件（客户端过滤全量列表） */
const directoryFiles = computed(() =>
  allFiles.value.filter((f) => (f.directory || '') === currentDirectory.value),
)

/** 面包屑：根目录 > seg1 > seg2 ...，可点击跳转 */
const breadcrumbItems = computed(() => {
  const segs = currentDirectory.value.split('/').filter(Boolean)
  const items: { label: string; path: string }[] = [{ label: '根目录', path: '' }]
  let acc = ''
  for (const s of segs) {
    acc = acc ? `${acc}/${s}` : s
    items.push({ label: s, path: acc })
  }
  return items
})
function navigateTo(path: string) {
  currentDirectory.value = path
}

/** 搜索 + 排序后的展示列表 */
const displayFiles = computed(() => {
  let list = directoryFiles.value
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter((f) => f.original_name.toLowerCase().includes(q))
  }
  const sorted = [...list]
  sorted.sort((a, b) => {
    if (sortBy.value === 'name') return a.original_name.localeCompare(b.original_name)
    if (sortBy.value === 'size') return b.size - a.size
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
  return sorted
})

/** 文件格式 Tag 元信息 */
const fileTypeTagMeta: Record<string, { label: string; type?: 'info' | 'success' | 'warning' | 'default'; color?: string }> = {
  fastq: { label: 'FASTQ', type: 'info' },
  bam: { label: 'BAM', type: 'success' },
  vcf: { label: 'VCF', type: 'warning' },
  count_matrix: { label: '矩阵', color: '#0FC6C2' },
  h5ad: { label: 'H5AD', color: '#8E54E9' },
  rds: { label: 'RDS', color: '#8E54E9' },
  meta: { label: '元数据', type: 'default' },
  report: { label: '报告', type: 'default' },
  image: { label: '图片', type: 'default' },
  other: { label: '其他', type: 'default' },
}

function renderFileTypeTag(fileType: string) {
  const meta = fileTypeTagMeta[fileType] || fileTypeTagMeta.other
  return h(
    NTag,
    { size: 'small', round: true, type: meta.type, color: meta.color ? { color: meta.color, textColor: '#fff', borderColor: meta.color } : undefined },
    { default: () => meta.label },
  )
}

function fileIcon(fileType: string) {
  return ScanOutline
}

/** 文件名后缀 → emoji 图标 */
function fileEmoji(name: string): string {
  const n = name.toLowerCase()
  if (n.endsWith('.zip')) return '📦'
  if (n.endsWith('.tsv') || n.endsWith('.csv')) return '📊'
  if (n.endsWith('.fastq.gz') || n.endsWith('.fq.gz') || n.endsWith('.fastq') || n.endsWith('.fq')) return '🧬'
  if (n.endsWith('.log')) return '📜'
  return '📄'
}

function rowActionOptions() {
  return [
    { label: '下载', key: 'download', icon: () => h(NIcon, null, { default: () => h(DownloadOutline) }) },
    { label: '重命名', key: 'rename', icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) },
    { label: '删除', key: 'delete', icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) },
  ]
}

function onRowAction(key: string, row: DataFile) {
  if (key === 'download') downloadFile(row)
  else if (key === 'rename') message.info('重命名功能即将上线')
  else if (key === 'delete') confirmDelete(row)
}

const columns = computed<DataTableColumns<DataFile>>(() => [
  {
    title: '文件名',
    key: 'original_name',
    render: (row) =>
      h('div', { class: 'file-name-cell' }, [
        h('span', { class: 'file-emoji' }, fileEmoji(row.original_name)),
        h('span', null, row.original_name),
      ]),
  },
  { title: '格式', key: 'file_type', width: 100, render: (row) => renderFileTypeTag(row.file_type) },
  { title: '大小', key: 'size', width: 110, render: (row) => formatSize(row.size) },
  {
    title: '创建时间',
    key: 'created_at',
    width: 170,
    render: (row) => (row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-'),
  },
  {
    title: '操作',
    key: 'actions',
    width: 70,
    render: (row) =>
      h(
        NDropdown,
        {
          trigger: 'click',
          placement: 'bottom-end',
          options: rowActionOptions(),
          onSelect: (k: string) => onRowAction(k, row),
        },
        {
          default: () =>
            h(
              NButton,
              { size: 'tiny', quaternary: true, onClick: (e: Event) => e.stopPropagation() },
              { icon: () => h(NIcon, null, { default: () => h(EllipsisHorizontalOutline) }) },
            ),
        },
      ),
  },
])

const sortOptions = [
  { label: '按时间排序', value: 'time' },
  { label: '按名称排序', value: 'name' },
  { label: '按大小排序', value: 'size' },
]

const syncing = ref(false)

/** 同步磁盘文件到 file_records（只增不删），silent=true 用于进页面自动同步（不弹提示） */
async function syncFiles(silent = false) {
  syncing.value = true
  try {
    const res = await apiClient.post<{ added: number; added_size: number }>('/files/sync')
    if (!silent) {
      message.success(
        res.data.added > 0 ? `同步完成，新增 ${res.data.added} 个文件` : '同步完成，无新增文件',
      )
    }
  } catch {
    if (!silent) message.error('同步失败，请稍后重试')
  } finally {
    syncing.value = false
    await fetchAll()
  }
}

/** 拖拽调整左侧目录树宽度（200~480px） */
function startResize(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startW = siderWidth.value
  const onMove = (ev: MouseEvent) => {
    siderWidth.value = Math.min(480, Math.max(200, startW + ev.clientX - startX))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

async function fetchAll() {
  loading.value = true
  try {
    const [filesRes, dirsRes, samplesRes, quotaRes] = await Promise.all([
      apiClient.get<{ items: DataFile[]; total: number }>('/files'),
      apiClient.get<Directory[]>('/files/directories'),
      apiClient.get<{ items: unknown[]; total: number }>('/files/samples'),
      apiClient.get<QuotaInfo>('/files/quota'),
    ])
    allFiles.value = filesRes.data.items
    directories.value = dirsRes.data
    samplesCount.value = samplesRes.data.total ?? samplesRes.data.items.length
    quota.value = quotaRes.data
  } catch (error) {
    console.error('加载数据失败', error)
    message.error('加载数据失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function selectFile(row: DataFile) {
  selectedFile.value = selectedFile.value?.id === row.id ? null : row
}

function rowProps(row: DataFile) {
  return {
    style: selectedFile.value?.id === row.id ? 'background: rgba(22,93,255,0.06)' : '',
    onClick: () => selectFile(row),
  }
}

async function downloadFile(row: DataFile) {
  try {
    const res = await apiClient.get(`/files/${row.id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = row.original_name
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    message.error('下载失败，请稍后重试')
  }
}

function confirmDelete(row: DataFile) {
  dialog.error({
    title: '删除文件',
    content: `确认删除「${row.original_name}」？将释放 ${formatSize(row.size)} 空间。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.delete(`/files/${row.id}`)
        message.success('已删除')
        if (selectedFile.value?.id === row.id) selectedFile.value = null
        await fetchAll()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}

async function openMoveModal(row: DataFile) {
  let dirs: Directory[] = []
  try {
    const res = await apiClient.get<Directory[]>('/files/directories')
    dirs = res.data
  } catch {
    message.error('获取目录失败')
    return
  }
  const options = [{ label: '根目录', value: '' }, ...dirs.map((d) => ({ label: d.path, value: d.path }))]
  let target = row.directory || ''
  dialog.create({
    title: `移动「${row.original_name}」`,
    content: () => h(NSelect, {
      value: target,
      'onUpdate:value': (v: string) => (target = v),
      options, placeholder: '选择目标目录', filterable: true,
    }),
    positiveText: '移动',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.put(`/files/${row.id}/move`, { directory: target })
        message.success('已移动')
        await fetchAll()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '移动失败')
      }
    },
  })
}

function handleDropUpload({ file }: { file: UploadFileInfo }): boolean {
  if (file.file) {
    uploadStore.open(currentDirectory.value)
    uploadStore.addFile(file.file)
  }
  return false
}

function importFromSRA() { message.info('SRA 公共数据库导入即将上线') }
function importFromGEO() { message.info('GEO 公共数据库导入即将上线') }
function importFromURL() { message.info('URL 导入即将上线') }

const supportedFormats = ['FASTQ', 'BAM', 'VCF', 'CRAM', 'ZIP']

watch(completedSeq, () => { fetchAll() })
watch(currentDirectory, () => { selectedFile.value = null })

onMounted(() => syncFiles(true))
</script>

<template>
  <div class="finder-page">
    <!-- 顶部统计大盘 -->
    <OverviewStats
      :samples="samplesCount"
      :files="allFiles.length"
      :projects="projectsCount"
      :quota="quota"
    />

    <!-- Finder 三栏 -->
    <div class="finder-grid">
      <!-- 左：目录树（可拖拽调宽） -->
      <aside class="col-tree" :style="{ width: siderWidth + 'px' }">
        <DirectoryTree
          v-model="currentDirectory"
          ref="treeRef"
          :file-counts="fileCounts"
          @refresh-files="fetchAll"
        />
        <div class="resize-handle" title="拖拽调整宽度" @mousedown="startResize"></div>
      </aside>

      <!-- 中：Data Workspace -->
      <section class="col-workspace">
        <!-- 面包屑导航 -->
        <div class="breadcrumb-bar">
          <NBreadcrumb>
            <NBreadcrumbItem
              v-for="item in breadcrumbItems"
              :key="item.path"
              @click="navigateTo(item.path)"
            >
              {{ item.label }}
            </NBreadcrumbItem>
          </NBreadcrumb>
        </div>
        <!-- 工具栏 -->
        <div class="toolbar">
          <div class="toolbar-left">
            <NButton type="primary" size="small" @click="uploadStore.open(currentDirectory)">
              <template #icon><NIcon><CloudUploadOutline /></NIcon></template>
              上传
            </NButton>
            <NButton size="small" @click="treeRef?.openCreateModal?.(currentDirectory)">
              <template #icon><NIcon><FolderOpenOutline /></NIcon></template>
              新建文件夹
            </NButton>
            <NButton size="small" :loading="syncing" @click="syncFiles(false)">
              <template #icon><NIcon><RefreshOutline /></NIcon></template>
              同步
            </NButton>
            <NButton size="small" @click="showJbrowseLinkGen = true">
              <template #icon><NIcon><LinkOutline /></NIcon></template>
              JBrowse 直链
            </NButton>
            <NSelect
              v-model:value="sortBy"
              :options="sortOptions"
              size="small"
              style="width: 130px"
            />
          </div>
          <div class="toolbar-right">
            <NInput
              v-model:value="searchQuery"
              size="small"
              placeholder="搜索文件..."
              clearable
              style="width: 180px"
            >
              <template #prefix><NIcon :size="14"><SearchOutline /></NIcon></template>
            </NInput>
            <div class="view-toggle">
              <NButton size="small" :type="viewMode === 'list' ? 'primary' : 'default'" quaternary @click="viewMode = 'list'">
                <template #icon><NIcon><ListOutline /></NIcon></template>
              </NButton>
              <NButton size="small" :type="viewMode === 'grid' ? 'primary' : 'default'" quaternary @click="viewMode = 'grid'">
                <template #icon><NIcon><GridOutline /></NIcon></template>
              </NButton>
            </div>
          </div>
        </div>

        <!-- 工作台主体 -->
        <NSpin :show="loading" class="workspace-body">
          <!-- 有文件 -->
          <template v-if="displayFiles.length">
            <!-- 列表视图 -->
            <NDataTable
              v-if="viewMode === 'list'"
              :columns="columns"
              :data="displayFiles"
              :row-key="(row: DataFile) => row.id"
              :bordered="false"
              size="small"
              :row-props="rowProps"
              class="file-table"
            />
            <!-- 网格视图 -->
            <div v-else class="file-grid">
              <div
                v-for="f in displayFiles"
                :key="f.id"
                class="grid-card"
                :class="{ active: selectedFile?.id === f.id }"
                @click="selectFile(f)"
              >
                <div class="grid-icon">
                  <NIcon :size="28" color="#165DFF"><component :is="fileIcon(f.file_type)" /></NIcon>
                </div>
                <span class="grid-name" :title="f.original_name">{{ f.original_name }}</span>
                <span class="grid-size">{{ formatSize(f.size) }}</span>
                <div class="grid-tag">
                  <component :is="renderFileTypeTag(f.file_type)" />
                </div>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <div v-else class="empty-state">
            <svg class="dna-illustration" width="96" height="96" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M30 15 C 90 15, 90 105, 30 105" stroke="#165DFF" stroke-width="2.5" stroke-linecap="round" fill="none" opacity="0.4"/>
              <path d="M90 15 C 30 15, 30 105, 90 105" stroke="#165DFF" stroke-width="2.5" stroke-linecap="round" fill="none" opacity="0.4"/>
              <line x1="38" y1="28" x2="82" y2="28" stroke="#165DFF" stroke-width="2" opacity="0.3" stroke-linecap="round"/>
              <line x1="44" y1="44" x2="76" y2="44" stroke="#165DFF" stroke-width="2" opacity="0.3" stroke-linecap="round"/>
              <line x1="46" y1="60" x2="74" y2="60" stroke="#165DFF" stroke-width="2" opacity="0.3" stroke-linecap="round"/>
              <line x1="44" y1="76" x2="76" y2="76" stroke="#165DFF" stroke-width="2" opacity="0.3" stroke-linecap="round"/>
              <line x1="38" y1="92" x2="82" y2="92" stroke="#165DFF" stroke-width="2" opacity="0.3" stroke-linecap="round"/>
            </svg>
            <h3 class="empty-title">No datasets in this folder</h3>
            <p class="empty-subtitle">拖拽测序数据到下方，或点击选择文件上传到「{{ currentDirectory || '根目录' }}」</p>

            <NUpload
              class="empty-dropzone"
              :show-file-list="false"
              :default-upload="false"
              multiple
              directory-dnd
              @before-upload="handleDropUpload"
            >
              <div class="dropzone-inner">
                <NIcon :size="28" class="dropzone-icon"><CloudDownloadOutline /></NIcon>
                <p class="dropzone-title">拖拽文件到此处，或点击选择</p>
                <div class="format-chips">
                  <span v-for="fmt in supportedFormats" :key="fmt" class="format-chip">{{ fmt }}</span>
                </div>
              </div>
            </NUpload>

            <div class="import-row">
              <NButton size="small" quaternary @click="importFromSRA">
                <template #icon><NIcon><GlobeOutline /></NIcon></template>
                Import from SRA
              </NButton>
              <NButton size="small" quaternary @click="importFromGEO">
                <template #icon><NIcon><GlobeOutline /></NIcon></template>
                Import from GEO
              </NButton>
              <NButton size="small" quaternary @click="importFromURL">
                <template #icon><NIcon><LinkOutline /></NIcon></template>
                Import from URL
              </NButton>
            </div>
            <a class="help-link" @click="message.info('帮助文档即将上线')">
              <NIcon :size="13"><DocumentTextOutline /></NIcon> 查看支持的数据格式与上传帮助
            </a>
          </div>
        </NSpin>
      </section>

      <!-- 右：详情面板 -->
      <aside class="col-detail">
        <JBrowseLinkGenerator v-model:show="showJbrowseLinkGen" :files="displayFiles" />
        <FileDetailPanel
          v-if="selectedFile"
          :file="selectedFile"
          @close="selectedFile = null"
          @download="downloadFile"
          @move="openMoveModal"
          @delete="confirmDelete"
        />
        <template v-else>
          <StorageOverviewWidget
            :quota="quota"
            :directory-count="directories.length"
            @clean-cache="fetchAll"
            @manage-storage="message.info('存储管理面板即将上线')"
          />
          <RecentActivitiesWidget :files="allFiles" :directories="directories" />
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.finder-page {
  background: var(--page-bg, #F7F9FC);
  flex: 1;
  min-height: 0;
  padding: 16px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}
.finder-grid {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0; /* 允许子项收缩并独立滚动 */
}
.col-tree,
.col-workspace,
.col-detail {
  background: var(--neutral-card, #fff);
  border-radius: var(--radius-lg, 16px);
  box-shadow: var(--shadow-soft, 0 4px 12px rgba(0, 0, 0, 0.05));
  border: 1px solid rgba(229, 230, 235, 0.5);
  min-height: 0;
}
.col-tree {
  position: relative;
  flex-shrink: 0;
  overflow: visible; /* 让 resize-handle 可超出右边缘 */
}
.resize-handle {
  position: absolute;
  top: 0;
  right: -6px;
  width: 12px;
  height: 100%;
  cursor: col-resize;
  z-index: 5;
}
.resize-handle:hover,
.resize-handle:active {
  background: rgba(22, 93, 255, 0.12);
  border-radius: 4px;
}
.col-workspace {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.breadcrumb-bar {
  padding: 10px 16px;
  border-bottom: 1px solid var(--neutral-border, #e5e6eb);
  flex-shrink: 0;
}
.col-detail {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}
.file-emoji {
  font-size: 16px;
  line-height: 1;
  margin-right: 6px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--neutral-border, #e5e6eb);
  flex-wrap: wrap;
  flex-shrink: 0;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.view-toggle {
  display: flex;
  gap: 2px;
  background: var(--neutral-bg, #f2f3f8);
  border-radius: 8px;
  padding: 2px;
}
.workspace-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 12px 16px;
}
.workspace-body :deep(.n-spin-content) {
  height: 100%;
}

/* 文件表格 */
.file-table {
  cursor: default;
}
.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 网格视图 */
.file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  padding: 8px 4px;
}
.grid-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 10px;
  border-radius: var(--radius-md, 12px);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: center;
}
.grid-card:hover {
  background: #F5F8FF;
  border-color: rgba(22, 93, 255, 0.15);
}
.grid-card.active {
  background: #E8F3FF;
  border-color: #165DFF;
}
.grid-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-md, 12px);
  background: #F5F8FF;
  display: flex;
  align-items: center;
  justify-content: center;
}
.grid-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--neutral-text-1, #1d2129);
  word-break: break-all;
  line-height: 1.3;
  max-width: 100%;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.grid-size {
  font-size: 11px;
  color: var(--neutral-text-3, #86909c);
  font-variant-numeric: tabular-nums;
}
.grid-tag {
  margin-top: 2px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 24px 40px;
}
.dna-illustration {
  margin-bottom: 16px;
}
.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0 0 6px;
}
.empty-subtitle {
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
  margin: 0 0 22px;
  text-align: center;
}
.empty-dropzone {
  width: 100%;
  max-width: 480px;
}
.empty-dropzone :deep(.n-upload-trigger) {
  width: 100%;
}
.dropzone-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px;
  border: 2px dashed var(--neutral-border, #d9d9d9);
  border-radius: var(--radius-lg, 16px);
  background: var(--neutral-card, #fff);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  width: 100%;
  box-sizing: border-box;
}
.dropzone-inner:hover {
  border-color: #165DFF;
  background: #F5F8FF;
}
.dropzone-icon {
  color: #165DFF;
  margin-bottom: 8px;
}
.dropzone-title {
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--neutral-text-1, #1d2129);
}
.format-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}
.format-chip {
  font-size: 11px;
  font-weight: 600;
  color: #165DFF;
  background: #E8F3FF;
  padding: 3px 10px;
  border-radius: 8px;
}
.import-row {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
  justify-content: center;
}
.help-link {
  margin-top: 16px;
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.help-link:hover {
  color: #165DFF;
}

@media (max-width: 1100px) {
  .finder-grid {
    grid-template-columns: 220px 1fr;
  }
  .col-detail {
    grid-column: 1 / -1;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .col-detail > * {
    flex: 1 1 280px;
  }
}
@media (max-width: 820px) {
  .finder-grid {
    grid-template-columns: 1fr;
  }
  .col-tree {
    order: 0;
  }
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .toolbar-left,
  .toolbar-right {
    justify-content: center;
  }
}
</style>
