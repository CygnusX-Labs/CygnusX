<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NSelect, useMessage } from 'naive-ui'

type SourceTab = 'sra' | 'cloud-drive' | 'cloud-storage'

interface DownloadTask {
  id: string
  name: string
  source: string
  accession: string
  status: 'running' | 'queued' | 'success' | 'failed' | 'pending'
  progress: number
  size: string
  speed: string
  createdAt: string
}

const router = useRouter()
const message = useMessage()

const activeTab = ref<SourceTab>('sra')
const submitting = ref(false)

// ── SRA 基础表单 ──
const sraAccession = ref('')
const sraMethod = ref<'aws' | 'aspera' | 'ftp'>('aws')
const targetDirectory = ref('')

// ── 高级选项：仅 4 个正则过滤字段 ──
const advancedOpen = ref(false)
const includeSample = ref('')
const excludeSample = ref('')
const includeRun = ref('')
const excludeRun = ref('')

// ── 云盘表单 ──
const driveProvider = ref<'baidu' | '123'>('baidu')
const driveLink = ref('')
const driveCode = ref('')

// ── 云存储表单 ──
const storageProvider = ref<'aliyun' | 'volc' | 'huawei'>('aliyun')
const storageUri = ref('')

// ── 任务列表状态筛选 ──
const statusFilter = ref<'all' | DownloadTask['status']>('all')

const tabs: { key: SourceTab; icon: string; label: string }[] = [
  { key: 'sra', icon: '🧬', label: '公共数据库' },
  { key: 'cloud-drive', icon: '☁️', label: '云盘极速提取' },
  { key: 'cloud-storage', icon: '🏢', label: '云存储直拉' },
]

const tabDescriptions: Record<SourceTab, string> = {
  'sra': '输入 NCBI/EBI 登录号（如 PRJNA），通过高并发节点直接将原始测序数据同步至您的工作空间。',
  'cloud-drive': '支持解析百度网盘或 123 云盘分享链接，无需消耗本地带宽，云端内网极速拉取交接数据。',
  'cloud-storage': '通过云厂商内网（阿里云、火山、华为等）实现对象存储之间的数据秒级克隆。',
}

const statusConfig: Record<string, { label: string; badge: string; icon: string }> = {
  success: { label: '已完成', badge: 'bg-green-50 text-green-700', icon: 'check' },
  running: { label: '下载中', badge: 'bg-blue-50 text-blue-700', icon: 'loading' },
  failed:  { label: '失败',   badge: 'bg-red-50 text-red-700', icon: 'x' },
  queued:  { label: '排队中', badge: 'bg-neutral-hover text-text-secondary', icon: 'clock' },
  pending: { label: '等待中', badge: 'bg-neutral-hover text-text-secondary', icon: 'clock' },
}

function scfg(status: string) {
  return statusConfig[status] || statusConfig.pending
}

function pct(task: DownloadTask) {
  return Math.round(task.progress * 100)
}

const gradientBar = 'background: linear-gradient(90deg, #4F8EF7, #9B59B6)'

// ── Mock 任务 ──
const tasks = ref<DownloadTask[]>([
  { id: 'd-001', name: 'PRJNA1251654 原始数据下载', source: 'SRA', accession: 'PRJNA1251654', status: 'running', progress: 0.62, size: '18.4 / 29.7 GB', speed: '12.3 MB/s', createdAt: '2026-07-03T09:12:00' },
  { id: 'd-002', name: 'SRR19852341 单样本下载', source: 'SRA', accession: 'SRR19852341', status: 'success', progress: 1, size: '4.2 GB', speed: '-', createdAt: '2026-07-03T08:40:00' },
  { id: 'd-003', name: 'PRJEB54321 批量下载', source: 'SRA', accession: 'PRJEB54321', status: 'failed', progress: 0.18, size: '1.1 / 6.2 GB', speed: '-', createdAt: '2026-07-03T07:50:00' },
  { id: 'd-004', name: '百度网盘 — 黄瓜果实转录组', source: '云盘', accession: 'link', status: 'queued', progress: 0, size: '8.6 GB', speed: '-', createdAt: '2026-07-03T09:30:00' },
  { id: 'd-005', name: '123 云盘 — 拟南芥 ATAC 数据', source: '云盘', accession: 'link', status: 'running', progress: 0.35, size: '2.1 / 6.0 GB', speed: '5.8 MB/s', createdAt: '2026-07-03T09:15:00' },
  { id: 'd-006', name: '阿里云 OSS — 水稻变异检测', source: '云存储', accession: 'oss://rg-seq/raw', status: 'success', progress: 1, size: '12.3 GB', speed: '-', createdAt: '2026-07-02T16:20:00' },
  { id: 'd-007', name: '火山引擎 TOS — PBMC 单细胞', source: '云存储', accession: 'tos://scrna/pbmc', status: 'pending', progress: 0, size: '3.8 GB', speed: '-', createdAt: '2026-07-03T09:45:00' },
  { id: 'd-008', name: 'PRJNA678901 双端数据', source: 'SRA', accession: 'PRJNA678901', status: 'running', progress: 0.81, size: '22.5 / 27.8 GB', speed: '15.1 MB/s', createdAt: '2026-07-02T11:00:00' },
  { id: 'd-009', name: '华为 OBS — 小鼠脑组织空间组', source: '云存储', accession: 'obs://spatial/mouse-brain', status: 'failed', progress: 0.42, size: '1.7 / 4.0 GB', speed: '-', createdAt: '2026-07-02T14:30:00' },
  { id: 'd-010', name: 'SRR21876543 转录组下载', source: 'SRA', accession: 'SRR21876543', status: 'success', progress: 1, size: '3.1 GB', speed: '-', createdAt: '2026-07-01T20:10:00' },
])

const stats = computed(() => {
  const t = tasks.value
  return {
    total: t.length,
    running: t.filter(x => x.status === 'running').length,
    success: t.filter(x => x.status === 'success').length,
    failed: t.filter(x => x.status === 'failed').length,
  }
})

const filteredTasks = computed(() => {
  if (statusFilter.value === 'all') return tasks.value
  return tasks.value.filter(t => t.status === statusFilter.value)
})

// ── 下拉选项（统一走 NSelect，继承全局浅色主题：白底 + 蓝色高亮 + 右侧对勾）──
const sraMethodOptions = [
  { label: 'AWS S3（推荐，最快）', value: 'aws' },
  { label: 'Aspera 高速', value: 'aspera' },
  { label: 'FTP 标准下载', value: 'ftp' },
]

const targetDirectoryOptions = [
  { label: '根目录（默认）', value: '' },
  { label: 'raw-data', value: 'raw-data' },
  { label: 'projects/rna-seq', value: 'projects/rna-seq' },
  { label: 'projects/variant', value: 'projects/variant' },
]

const storageProviderOptions = [
  { label: '阿里云 OSS', value: 'aliyun' },
  { label: '火山引擎 TOS', value: 'volc' },
  { label: '华为云 OBS', value: 'huawei' },
]

const statusFilterOptions = [
  { label: '全部状态', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'success' },
  { label: '失败', value: 'failed' },
]

function formatTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function toggleAdvanced() {
  advancedOpen.value = !advancedOpen.value
  if (advancedOpen.value) {
    await nextTick()
    const el = document.getElementById('advanced-panel-bottom')
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }
}

function handleSubmit() {
  if (activeTab.value === 'sra') {
    if (!sraAccession.value.trim()) { message.warning('请输入登录号'); return }
    message.success(`已提交 SRA 下载任务：${sraAccession.value}`)
    sraAccession.value = ''
  } else if (activeTab.value === 'cloud-drive') {
    if (!driveLink.value.trim()) { message.warning('请输入分享链接'); return }
    message.success('已提交云盘提取任务')
    driveLink.value = ''
    driveCode.value = ''
  } else {
    if (!storageUri.value.trim()) { message.warning('请输入对象 URI'); return }
    message.success('已提交云存储拉取任务')
    storageUri.value = ''
  }
  submitting.value = true
  setTimeout(() => { submitting.value = false }, 800)
}

const inputFocusStyle = {
  onFocus: (e: Event) => {
    const el = e.target as HTMLInputElement | HTMLTextAreaElement
    el.style.borderColor = 'var(--arco-primary)'
    el.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--arco-primary) 15%, transparent)'
  },
  onBlur: (e: Event) => {
    const el = e.target as HTMLInputElement | HTMLTextAreaElement
    el.style.borderColor = 'var(--neutral-border)'
    el.style.boxShadow = 'none'
  },
}
</script>

<template>
  <div class="downloads-page">

    <!-- ═══ 页面标题区 ═══ -->
    <div class="mb-6">
      <h1 class="text-lg font-semibold" style="color: var(--neutral-text-1)">数据下载与聚合</h1>
      <p class="text-sm mt-1" style="color: var(--neutral-text-3)">从 NCBI/EBI 公共数据库、网盘或云存储拉取测序数据，下载完成后自动入库</p>
    </div>

    <!-- ═══ Pill 胶囊式 Tab 栏 ═══ -->
    <div class="flex items-center gap-2 mb-5">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="flex items-center gap-1.5 px-4 py-2 text-sm rounded-full transition-all duration-200"
        :class="activeTab === tab.key
          ? 'text-white shadow-md shadow-blue-500/20'
          : 'text-gray-500 hover:text-gray-800'"
        :style="activeTab === tab.key ? 'background: linear-gradient(135deg, #4F8EF7, #7C6FD4)' : 'background: var(--neutral-hover)'"
        @click="activeTab = tab.key"
      >
        <span class="text-sm">{{ tab.icon }}</span>
        {{ tab.label }}
      </button>
    </div>

    <!-- ═══ 动态描述条 ═══ -->
    <div class="flex items-start gap-2.5 text-sm p-3.5 rounded-lg mb-5" style="background: color-mix(in srgb, var(--arco-primary) 6%, transparent); color: var(--neutral-text-2); border-radius: 8px">
      <svg class="w-4 h-4 mt-0.5 flex-shrink-0" style="color: var(--arco-primary)" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" /></svg>
      <span class="leading-relaxed">{{ tabDescriptions[activeTab] }}</span>
    </div>

    <!-- ═══ 参数配置卡片 ═══ -->
    <div class="bg-neutral-card rounded-xl mb-5" style="box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.05); border: 1px solid var(--neutral-border)">

      <!-- ── SRA 表单 ── -->
      <div v-if="activeTab === 'sra'" class="p-6 space-y-5">

        <!-- 登录号（Textarea 自适应高度） -->
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">
            登录号 <span class="text-red-400">*</span>
          </label>
          <div class="flex-1 max-w-lg">
            <textarea
              v-model="sraAccession"
              rows="1"
              placeholder="PRJNA1251654 或 SRRxxxxxx，多个用逗号或换行分隔"
              class="w-full px-3.5 py-2.5 text-sm border resize-none transition-all duration-200 focus:outline-none"
              style="border-color: var(--neutral-border); border-radius: 8px; color: var(--neutral-text-1); min-height: 40px; max-height: 120px"
              v-on="inputFocusStyle"
            />
          </div>
        </div>

        <!-- 下载方式（NSelect 下拉，统一浅色主题） -->
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">下载方式</label>
          <NSelect
            v-model:value="sraMethod"
            :options="sraMethodOptions"
            size="large"
            style="width: 280px"
          />
        </div>

        <!-- 下载到 -->
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">下载到</label>
          <NSelect
            v-model:value="targetDirectory"
            :options="targetDirectoryOptions"
            size="large"
            style="width: 240px"
          />
        </div>

        <!-- ── 高级选项折叠面板 ── -->
        <div class="flex items-start gap-4">
          <div class="w-20 shrink-0"></div>
          <div class="flex-1 max-w-lg">
            <button
              class="w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-all duration-200"
              :style="advancedOpen
                ? 'background: var(--neutral-hover); border-color: var(--neutral-border); border-style: solid; border-radius: 8px 8px 0 0'
                : 'background: var(--neutral-bg); border-color: var(--neutral-border); border-style: dashed'"
              @mouseenter="($event.currentTarget as HTMLElement).style.background='var(--neutral-hover)'; ($event.currentTarget as HTMLElement).style.borderStyle='solid'"
              @mouseleave="($event.currentTarget as HTMLElement).style.background=advancedOpen ? '#F3F4F6' : '#F9FAFB'; ($event.currentTarget as HTMLElement).style.borderStyle=advancedOpen ? 'solid' : 'dashed'"
              @click="toggleAdvanced"
            >
              <span class="text-sm font-medium" style="color: var(--neutral-text-1)">高级选项：样本与 Run 过滤</span>
              <svg class="w-4 h-4 transition-transform duration-300" style="color: var(--neutral-text-2)" :class="advancedOpen ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" /></svg>
            </button>

            <!-- 展开内容：2x2 正则过滤 -->
            <div
              v-if="advancedOpen"
              id="advanced-panel-bottom"
              class="border rounded-b-lg bg-neutral-card p-5"
              style="border-color: var(--neutral-border); border-top: none; border-radius: 0 0 8px 8px"
            >
              <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                <!-- 包含样本 -->
                <div class="flex flex-col gap-1.5">
                  <label class="text-sm font-medium flex items-center gap-1.5" style="color: var(--neutral-text-1)">
                    <span class="inline-flex items-center justify-center w-5 h-5 rounded text-xs font-semibold" style="background: var(--arco-primary-light); color: #4F8EF7; border-radius: 4px">+</span>
                    包含样本 (Include)
                  </label>
                  <input
                    v-model="includeSample"
                    type="text"
                    placeholder="如：^SAMN.*"
                    class="h-10 px-3.5 text-sm border rounded-lg transition-all duration-200 focus:outline-none"
                    style="border-color: var(--neutral-border); color: var(--neutral-text-1); border-radius: 8px"
                    v-on="inputFocusStyle"
                  />
                  <span class="text-xs" style="color: var(--neutral-text-3)">正则匹配样本 ID，留空不过滤</span>
                </div>

                <!-- 排除样本 -->
                <div class="flex flex-col gap-1.5">
                  <label class="text-sm font-medium flex items-center gap-1.5" style="color: var(--neutral-text-1)">
                    <span class="inline-flex items-center justify-center w-5 h-5 rounded text-xs font-semibold" style="background: var(--arco-danger-light); color: #EF4444; border-radius: 4px">−</span>
                    排除样本 (Exclude)
                  </label>
                  <input
                    v-model="excludeSample"
                    type="text"
                    placeholder="如：.control."
                    class="h-10 px-3.5 text-sm border rounded-lg transition-all duration-200 focus:outline-none"
                    style="border-color: var(--neutral-border); color: var(--neutral-text-1); border-radius: 8px"
                    v-on="inputFocusStyle"
                  />
                  <span class="text-xs" style="color: var(--neutral-text-3)">匹配到的样本将被跳过</span>
                </div>

                <!-- 包含 Run -->
                <div class="flex flex-col gap-1.5">
                  <label class="text-sm font-medium flex items-center gap-1.5" style="color: var(--neutral-text-1)">
                    <span class="inline-flex items-center justify-center w-5 h-5 rounded text-xs font-semibold" style="background: var(--arco-primary-light); color: #4F8EF7; border-radius: 4px">+</span>
                    包含 Run (Include)
                  </label>
                  <input
                    v-model="includeRun"
                    type="text"
                    placeholder="如：SRR123.*"
                    class="h-10 px-3.5 text-sm border rounded-lg transition-all duration-200 focus:outline-none"
                    style="border-color: var(--neutral-border); color: var(--neutral-text-1); border-radius: 8px"
                    v-on="inputFocusStyle"
                  />
                  <span class="text-xs" style="color: var(--neutral-text-3)">正则匹配 Run 编号</span>
                </div>

                <!-- 排除 Run -->
                <div class="flex flex-col gap-1.5">
                  <label class="text-sm font-medium flex items-center gap-1.5" style="color: var(--neutral-text-1)">
                    <span class="inline-flex items-center justify-center w-5 h-5 rounded text-xs font-semibold" style="background: var(--arco-danger-light); color: #EF4444; border-radius: 4px">−</span>
                    排除 Run (Exclude)
                  </label>
                  <input
                    v-model="excludeRun"
                    type="text"
                    placeholder="如：.test."
                    class="h-10 px-3.5 text-sm border rounded-lg transition-all duration-200 focus:outline-none"
                    style="border-color: var(--neutral-border); color: var(--neutral-text-1); border-radius: 8px"
                    v-on="inputFocusStyle"
                  />
                  <span class="text-xs" style="color: var(--neutral-text-3)">匹配到的 Run 将被跳过</span>
                </div>
              </div>

              <p class="text-xs mt-4" style="color: var(--neutral-text-3)">支持正则表达式过滤，留空表示不过滤。多个模式用逗号分隔。</p>
            </div>
          </div>
        </div>

        <!-- ── 提交按钮组 ── -->
        <div class="flex items-start gap-4 pt-1">
          <div class="w-20 shrink-0"></div>
          <div class="flex items-center gap-3">
            <button
              class="h-10 px-6 text-sm font-semibold text-white transition-all duration-200 flex items-center gap-2 disabled:opacity-50 hover:-translate-y-px active:scale-[0.98]"
              :disabled="submitting"
              style="background: linear-gradient(135deg, #4F8EF7, #9B59B6); box-shadow: 0 4px 14px rgba(79,142,247,0.3); border-radius: 8px"
              @mouseenter="($event.currentTarget as HTMLElement).style.boxShadow='0 6px 20px rgba(79,142,247,0.4)'"
              @mouseleave="($event.currentTarget as HTMLElement).style.boxShadow='0 4px 14px rgba(79,142,247,0.3)'"
              @click="handleSubmit"
            >
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
              提交拉取任务
            </button>
            <button
              class="h-10 px-5 text-sm font-medium rounded-lg transition-all duration-200 flex items-center gap-2 border hover:-translate-y-px active:scale-[0.98]"
              style="border-color: var(--neutral-border); color: var(--neutral-text-1); border-radius: 8px; background: transparent"
              @mouseenter="($event.currentTarget as HTMLElement).style.background='var(--neutral-bg)'"
              @mouseleave="($event.currentTarget as HTMLElement).style.background='transparent'"
            >
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" /></svg>
              Dry Run
            </button>
          </div>
        </div>
      </div>

      <!-- ── 云盘表单 ── -->
      <div v-if="activeTab === 'cloud-drive'" class="p-6 space-y-5">
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">网盘来源</label>
          <div class="flex items-center gap-4 h-10">
            <label class="flex items-center gap-1.5 text-sm cursor-pointer" style="color: var(--neutral-text-1)"><input v-model="driveProvider" type="radio" value="baidu" class="accent-blue-500 w-3.5 h-3.5" /> 百度网盘</label>
            <label class="flex items-center gap-1.5 text-sm cursor-pointer" style="color: var(--neutral-text-1)"><input v-model="driveProvider" type="radio" value="123" class="accent-blue-500 w-3.5 h-3.5" /> 123 云盘</label>
          </div>
        </div>
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">分享链接 <span class="text-red-400">*</span></label>
          <input v-model="driveLink" type="text" placeholder="粘贴网盘分享链接" class="flex-1 max-w-lg h-10 px-3.5 text-sm border transition-all duration-200 focus:outline-none" style="border-color: var(--neutral-border); border-radius: 8px; color: var(--neutral-text-1)" v-on="inputFocusStyle" />
        </div>
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">提取码</label>
          <input v-model="driveCode" type="text" placeholder="可选" maxlength="8" class="w-36 h-10 px-3.5 text-sm border text-center transition-all duration-200 focus:outline-none" style="border-color: var(--neutral-border); border-radius: 8px; color: var(--neutral-text-1)" v-on="inputFocusStyle" />
        </div>
        <div class="flex items-start gap-4 pt-1">
          <div class="w-20 shrink-0"></div>
          <button class="h-10 px-6 text-sm font-semibold text-white rounded-lg transition-all duration-200 flex items-center gap-2 disabled:opacity-50 hover:-translate-y-px active:scale-[0.98]" :disabled="submitting" style="background: linear-gradient(135deg, #4F8EF7, #9B59B6); box-shadow: 0 4px 14px rgba(79,142,247,0.3); border-radius: 8px" @click="handleSubmit">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
            提交拉取任务
          </button>
        </div>
      </div>

      <!-- ── 云存储表单 ── -->
      <div v-if="activeTab === 'cloud-storage'" class="p-6 space-y-5">
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">云服务商</label>
          <NSelect
            v-model:value="storageProvider"
            :options="storageProviderOptions"
            size="large"
            style="width: 240px"
          />
        </div>
        <div class="flex items-start gap-4">
          <label class="w-20 text-right text-sm font-medium pt-2.5 shrink-0" style="color: var(--neutral-text-1)">对象 URI <span class="text-red-400">*</span></label>
          <input v-model="storageUri" type="text" placeholder="oss://bucket-name/path/to/data/" class="flex-1 max-w-lg h-10 px-3.5 text-sm font-mono border transition-all duration-200 focus:outline-none" style="border-color: var(--neutral-border); border-radius: 8px; color: var(--neutral-text-1)" v-on="inputFocusStyle" />
        </div>
        <div class="flex items-start gap-4 pt-1">
          <div class="w-20 shrink-0"></div>
          <button class="h-10 px-6 text-sm font-semibold text-white rounded-lg transition-all duration-200 flex items-center gap-2 disabled:opacity-50 hover:-translate-y-px active:scale-[0.98]" :disabled="submitting" style="background: linear-gradient(135deg, #4F8EF7, #9B59B6); box-shadow: 0 4px 14px rgba(79,142,247,0.3); border-radius: 8px" @click="handleSubmit">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
            提交拉取任务
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ 下载任务卡片 ═══ -->
    <div class="bg-neutral-card rounded-xl" style="box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.05); border: 1px solid var(--neutral-border)">

      <!-- 队列头部 -->
      <div class="flex items-center justify-between px-5 py-3.5 border-b" style="border-color: var(--neutral-border)">
        <div class="flex items-center gap-4">
          <h3 class="text-sm font-semibold" style="color: var(--neutral-text-1)">下载任务</h3>
          <div class="flex items-center gap-3 text-xs" style="color: var(--neutral-text-3)">
            <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span> 共 {{ stats.total }} 个</span>
            <span v-if="stats.running" class="flex items-center gap-1" style="color: #4F8EF7"><span class="w-1.5 h-1.5 rounded-full animate-pulse" style="background: #4F8EF7"></span> {{ stats.running }} 下载中</span>
            <span v-if="stats.success" class="flex items-center gap-1 text-green-600"><span class="w-1.5 h-1.5 rounded-full bg-green-500"></span> {{ stats.success }} 已完成</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <NSelect
            v-model:value="statusFilter"
            :options="statusFilterOptions"
            size="small"
            style="width: 120px"
          />
          <button class="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md transition-colors" style="color: var(--neutral-text-2); border-radius: 6px" @mouseenter="($event.currentTarget as HTMLElement).style.color='#4F8EF7'; ($event.currentTarget as HTMLElement).style.background='var(--neutral-hover)'" @mouseleave="($event.currentTarget as HTMLElement).style.color='var(--neutral-text-2)'; ($event.currentTarget as HTMLElement).style.background='transparent'">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            刷新
          </button>
        </div>
      </div>

      <!-- 表格 -->
      <div class="overflow-x-auto">
        <table class="min-w-full text-left">
          <thead class="border-b" style="background: var(--neutral-bg); border-color: var(--neutral-border)">
            <tr>
              <th class="text-xs font-medium px-5 py-2.5" style="color: var(--neutral-text-2)">任务名称</th>
              <th class="text-xs font-medium px-5 py-2.5 w-[100px]" style="color: var(--neutral-text-2)">登录号</th>
              <th class="text-xs font-medium px-5 py-2.5 w-[100px]" style="color: var(--neutral-text-2)">状态</th>
              <th class="text-xs font-medium px-5 py-2.5 w-[180px]" style="color: var(--neutral-text-2)">进度</th>
              <th class="text-xs font-medium px-5 py-2.5 w-[120px]" style="color: var(--neutral-text-2)">提交时间</th>
              <th class="text-xs font-medium px-5 py-2.5 w-[100px] text-right" style="color: var(--neutral-text-2)">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="task in filteredTasks"
              :key="task.id"
              class="transition-colors group"
              style="height: 52px"
              @mouseenter="($event.currentTarget as HTMLElement).style.background='var(--neutral-hover)'"
              @mouseleave="($event.currentTarget as HTMLElement).style.background='transparent'"
            >
              <!-- 任务名称 -->
              <td class="px-5 py-3 border-b" style="border-color: var(--neutral-border)">
                <span class="text-sm font-medium truncate block max-w-[280px]" style="color: var(--neutral-text-1)" :title="task.name">{{ task.name }}</span>
              </td>

              <!-- 登录号 -->
              <td class="px-5 py-3 border-b" style="border-color: var(--neutral-border)">
                <span class="text-xs font-mono truncate block max-w-[110px]" style="color: var(--neutral-text-2)" :title="task.accession">{{ task.accession }}</span>
              </td>

              <!-- 状态 -->
              <td class="px-5 py-3 border-b" style="border-color: var(--neutral-border)">
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium" style="border-radius: 4px" :class="scfg(task.status).badge">
                  <svg v-if="scfg(task.status).icon === 'check'" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                  <svg v-else-if="scfg(task.status).icon === 'loading'" class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>
                  <svg v-else-if="scfg(task.status).icon === 'x'" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                  <svg v-else class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  {{ scfg(task.status).label }}
                </span>
              </td>

              <!-- 进度条 -->
              <td class="px-5 py-3 border-b" style="border-color: var(--neutral-border)">
                <div class="flex items-center gap-2">
                  <div class="flex-1 h-1.5 rounded-full overflow-hidden" style="background: var(--neutral-hover); border-radius: 3px">
                    <div
                      class="h-full rounded-full transition-all duration-500"
                      :style="`${gradientBar}; width: ${pct(task)}%; border-radius: 3px`"
                    ></div>
                  </div>
                  <span class="text-xs font-medium tabular-nums w-8 text-right" style="color: var(--neutral-text-2)">{{ pct(task) }}%</span>
                </div>
              </td>

              <!-- 时间 -->
              <td class="px-5 py-3 border-b" style="border-color: var(--neutral-border)">
                <span class="text-xs" style="color: var(--neutral-text-3)">{{ formatTime(task.createdAt) }}</span>
              </td>

              <!-- 操作 -->
              <td class="px-5 py-3 border-b text-right" style="border-color: var(--neutral-border)">
                <div class="flex items-center justify-end gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button v-if="task.status === 'running'" class="p-1.5 rounded-md transition-colors" style="color: var(--neutral-text-3)" title="暂停" @mouseenter="($event.target as HTMLElement).style.color='#F59E0B'" @mouseleave="($event.target as HTMLElement).style.color='var(--neutral-text-3)'">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25v13.5m-7.5-13.5v13.5" /></svg>
                  </button>
                  <button class="p-1.5 rounded-md transition-colors" style="color: var(--neutral-text-3)" title="查看日志" @mouseenter="($event.target as HTMLElement).style.color='#4F8EF7'" @mouseleave="($event.target as HTMLElement).style.color='var(--neutral-text-3)'" @click="router.push(`/tasks/${task.id}`)">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
                  </button>
                  <button v-if="task.status === 'failed'" class="p-1.5 rounded-md transition-colors" style="color: var(--neutral-text-3)" title="重新下载" @mouseenter="($event.target as HTMLElement).style.color='#10B981'" @mouseleave="($event.target as HTMLElement).style.color='var(--neutral-text-3)'">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                  </button>
                  <button class="p-1.5 rounded-md transition-colors" style="color: var(--neutral-text-3)" title="删除" @mouseenter="($event.target as HTMLElement).style.color='#EF4444'" @mouseleave="($event.target as HTMLElement).style.color='var(--neutral-text-3)'">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 空状态 -->
        <div v-if="filteredTasks.length === 0" class="flex flex-col items-center justify-center py-20">
          <svg class="w-16 h-16 mb-4" style="color: var(--neutral-border)" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="0.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 16v-4m0 0V8m0 4h4m-4 0H8m12 4v1a3 3 0 01-3 3H7a3 3 0 01-3-3v-1" />
          </svg>
          <p class="text-sm font-medium mb-1" style="color: var(--neutral-text-2)">暂无下载任务</p>
          <p class="text-xs" style="color: var(--neutral-text-3)">输入登录号后开始拉取数据，下载完成的文件将自动出现在「数据管理」中</p>
        </div>
      </div>
    </div>

    <!-- 底部留白 -->
    <div class="h-20"></div>
  </div>
</template>

<style scoped>
.downloads-page {
  padding-bottom: 80px;
}
</style>
