<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NIcon, NSelect, NInput, NTag, NSpace, NSpin, NEmpty,
  NModal, NUpload, NUploadDragger, NCheckbox, NProgress,
  NDivider, NForm, NFormItem, useMessage } from 'naive-ui'
import {
  LocationOutline, CloudUploadOutline,
  FolderOpenOutline, DesktopOutline,
} from '@vicons/ionicons5'
import { jbrowseApi } from '@/api/jbrowse'
import { absolutizeUris } from '@/utils/jbrowse'
import JbrowseFileDrawer from '@/components/data-management/JbrowseFileDrawer.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { AssemblyDTO, ScannedFileDTO, SelectedTrack } from '@/types/jbrowse'

const route = useRoute()
const router = useRouter()
const message = useMessage()

// ==================== 状态 ====================
const assemblies = ref<AssemblyDTO[]>([])
const assembliesLoading = ref(false)
const selectedAssembly = ref<string>('')
const regionInput = ref('')
const jbrowseUrl = ref('')
const selectedTracks = ref<SelectedTrack[]>([])
let currentBlobUrl = ''

// 初始化 loading + 超时兜底
const loading = ref(false)
const loadingText = ref('正在初始化基因组浏览器...')
let initTimer: ReturnType<typeof setTimeout> | null = null
// iframe 强制刷新 key：每次生成新配置时自增，确保 iframe 元素重建，
// 避免 JBrowse 2 复用 localStorage 旧 session 导致只显示 Logo
const iframeKey = ref(0)
let iframeLoadTimer: ReturnType<typeof setTimeout> | null = null
let uploadCloseTimer: ReturnType<typeof setTimeout> | null = null

// 上传
const showUploadModal = ref(false)
const uploadFileList = ref<any[]>([])
const uploadForm = ref({ assemblyId: '' as string, autoIndex: true })
interface UploadProgress { filename: string; status: 'uploading' | 'success' | 'error'; statusText: string; percent: number; message: string }
const uploadProgress = ref<UploadProgress[]>([])

// 我的文件抽屉
const showScanDrawer = ref(false)

// ==================== 计算属性 ====================
const assemblyOptions = computed(() =>
  assemblies.value.map((a) => ({
    label: a.name,
    value: a.id,
    species: a.species,
  })),
)

function renderAssemblyLabel(option: { label: string; species?: string }) {
  return h('div', { class: 'assembly-option' }, [
    h('span', { class: 'assembly-name' }, option.label),
    option.species ? h('span', { class: 'assembly-species' }, option.species) : null,
  ])
}

// 已选轨道路径（传给抽屉回显勾选态）
const selectedPaths = computed(() => selectedTracks.value.map((t) => t.path))

// ==================== 生命周期 ====================
onMounted(async () => {
  await loadAssemblies()

  // 从 URL 参数恢复状态（方便从「数据管理」模块深链跳转）
  const { assembly, tracks, region, autoLoad } = route.query
  if (typeof assembly === 'string' && assembly) selectedAssembly.value = assembly
  if (typeof region === 'string') regionInput.value = region
  if (typeof autoLoad === 'string' && autoLoad) {
    selectedTracks.value.push({
      path: autoLoad,
      name: autoLoad.split('/').pop() || autoLoad,
      indexed: true,
    })
  } else if (tracks) {
    const arr = Array.isArray(tracks) ? tracks : [tracks]
    const trackPaths = arr.filter((p): p is string => typeof p === 'string')
    selectedTracks.value = trackPaths.map((p) => ({
      path: p,
      name: p.split('/').pop() || p,
      indexed: true,
    }))
  }

  // 自动初始化：无需用户点击「加载浏览器」
  if (selectedAssembly.value) {
    await loadBrowser()
  } else {
    message.warning('未找到可用的参考基因组，请先在管理端配置')
  }
})

onUnmounted(() => {
  revokeBlobUrl()
  if (initTimer) clearTimeout(initTimer)
  if (iframeLoadTimer) clearTimeout(iframeLoadTimer)
  if (uploadCloseTimer) clearTimeout(uploadCloseTimer)
})

function revokeBlobUrl() {
  if (currentBlobUrl) {
    URL.revokeObjectURL(currentBlobUrl)
    currentBlobUrl = ''
  }
}

// ==================== API 调用 ====================
async function loadAssemblies() {
  assembliesLoading.value = true
  try {
    const data = await jbrowseApi.listAssemblies()
    assemblies.value = data.assemblies || []
    // 默认选第一个有 .fai 索引的
    if (!selectedAssembly.value) {
      const available = assemblies.value.find((a) => a.fai_exists) || assemblies.value[0]
      if (available) selectedAssembly.value = available.id
    }
  } catch {
    message.error('加载参考基因组失败')
  } finally {
    assembliesLoading.value = false
  }
}

/**
 * 生成 JBrowse 2 配置并以 iframe 加载。
 * - 坐标格式校验 → 配置生成（写 blob URL 绕过 JWT）→ iframe 重建（key 自增）
 * - loading 覆盖层：iframe @load 后隐藏；10s 超时兜底提示
 */
async function loadBrowser() {
  if (!selectedAssembly.value) {
    message.warning('请先选择参考基因组')
    return
  }
  // 坐标格式校验（用户已输入时）
  if (regionInput.value && !validateRegion(regionInput.value)) {
    message.error('坐标格式错误，请使用 chr:start-end 格式')
    return
  }

  loading.value = true
  loadingText.value = '正在初始化基因组浏览器...'
  if (initTimer) clearTimeout(initTimer)
  // 超时兜底：iframe 10s 未完成加载则判定初始化失败
  initTimer = setTimeout(() => {
    if (loading.value) {
      loading.value = false
      message.error('初始化失败：参考基因组文件可能缺失或格式错误')
      console.error(
        '[JBrowse] 初始化超时(10s)。可能原因：参考基因组 FASTA/.fai 缺失、' +
          '/tracks/ 不可达、或 /jbrowse2/ 静态资源未正确挂载',
      )
    }
  }, 10000)

  try {
    const config = await jbrowseApi.generateConfig({
      assembly: selectedAssembly.value,
      tracks: selectedTracks.value.map((t) => t.path),
      region: regionInput.value || undefined,
    })
    // ⚠️ 关键：后端返回的 uri 是相对路径（/tracks/...），而 blob URL 是 opaque base，
    // JBrowse 用 new URL(uri, blobBase) 解析会抛 Invalid URL → 参考序列加载失败、只显示 Logo。
    // 写入 blob 前把所有 uri 补成绝对 URL（带 origin），绕开 opaque base 限制。
    absolutizeUris(config)
    // 写入 blob URL 交给 iframe：JBrowse 2 fetch blob 不需要 JWT，
    // 轨道数据经 nginx /tracks/ 流式读取
    revokeBlobUrl()
    const blob = new Blob([JSON.stringify(config)], { type: 'application/json' })
    currentBlobUrl = URL.createObjectURL(blob)
    // 追加 &loc= 让 JBrowse 2 web 在引导时直接定位到目标区域，
    // 配合 defaultSession 双保险，避免只渲染 Logo
    const loc = regionInput.value || ''
    jbrowseUrl.value =
      `/jbrowse2/?config=${encodeURIComponent(currentBlobUrl)}` +
      (loc ? `&loc=${encodeURIComponent(loc)}` : '')
    // 强制 iframe 重建，丢弃 JBrowse localStorage 中的旧 session
    iframeKey.value++

    // 更新 URL，方便分享 / 刷新恢复
    router.replace({
      query: {
        ...route.query,
        assembly: selectedAssembly.value,
        tracks: selectedTracks.value.map((t) => t.path),
        region: regionInput.value || undefined,
      },
    })
  } catch (e: any) {
    loading.value = false
    if (initTimer) {
      clearTimeout(initTimer)
      initTimer = null
    }
    message.error(e?.response?.data?.detail || '生成浏览器配置失败')
    console.error('[JBrowse] 配置生成失败:', e)
  }
}

/** iframe HTML 加载完成（JBrowse app 开始引导）→ 隐藏 loading */
function onIframeLoad() {
  // 留一帧让 JBindView 完成首屏渲染，避免 loading 闪烁与 Logo 残影叠加
  if (iframeLoadTimer) clearTimeout(iframeLoadTimer)
  iframeLoadTimer = setTimeout(() => {
    loading.value = false
    if (initTimer) {
      clearTimeout(initTimer)
      initTimer = null
    }
  }, 300)
}

function onAssemblyChange() {
  // 切换参考基因组：清空已选轨道与坐标，自动重新加载
  selectedTracks.value = []
  regionInput.value = ''
  loadBrowser()
}

function jumpToRegion() {
  regionInput.value = formatRegion(regionInput.value)
  loadBrowser()
}

function formatRegion(value: string): string {
  const match = value.trim().match(/^([A-Za-z0-9_.]+)\s*:\s*([\d,]+)\s*-\s*([\d,]+)$/)
  if (!match) return value
  const formatNumber = (part: string) => Number(part.replace(/,/g, '')).toLocaleString('en-US')
  return `${match[1]}:${formatNumber(match[2])}-${formatNumber(match[3])}`
}

/** 校验 chr:start-end（支持逗号千分位与空白） */
function validateRegion(s: string): boolean {
  const norm = s.replace(/\s/g, '').replace(/,/g, '')
  return /^[A-Za-z0-9_.]+:\d+-\d+$/.test(norm)
}

// ==================== 轨道管理 ====================
function removeTrack(track: SelectedTrack) {
  const idx = selectedTracks.value.findIndex((t) => t.path === track.path)
  if (idx > -1) {
    selectedTracks.value.splice(idx, 1)
    if (jbrowseUrl.value) loadBrowser()
  }
}

// ==================== 上传 ====================
async function handleUpload() {
  if (uploadFileList.value.length === 0) {
    message.warning('请选择要上传的文件')
    return
  }
  uploadProgress.value = uploadFileList.value.map((f) => ({
    filename: f.name,
    status: 'uploading',
    statusText: '上传中',
    percent: 0,
    message: '',
  }))

  for (let i = 0; i < uploadFileList.value.length; i++) {
    const item = uploadFileList.value[i]
    const prog = uploadProgress.value[i]
    const rawFile = item.file as File
    if (!rawFile) {
      prog.status = 'error'
      prog.statusText = '失败'
      prog.message = '无法读取文件'
      continue
    }
    try {
      const res = await jbrowseApi.upload(
        rawFile,
        { assemblyId: uploadForm.value.assemblyId, autoIndex: uploadForm.value.autoIndex },
        (p) => { prog.percent = p },
      )
      prog.status = 'success'
      prog.statusText = '上传成功'
      prog.percent = 100
      prog.message = res.index_task_id ? '索引任务已排队' : ''
      // 自动加入已选轨道
      if (!selectedTracks.value.some((t) => t.path === res.saved_path)) {
        selectedTracks.value.push({ path: res.saved_path, name: res.filename, indexed: true })
      }
    } catch (e: any) {
      prog.status = 'error'
      prog.statusText = '上传失败'
      prog.message = e?.response?.data?.detail || e.message || '未知错误'
    }
  }

  if (uploadCloseTimer) clearTimeout(uploadCloseTimer)
  uploadCloseTimer = setTimeout(() => {
    showUploadModal.value = false
    resetUpload()
  }, 1500)
}

function resetUpload() {
  uploadFileList.value = []
  uploadForm.value = { assemblyId: '', autoIndex: true }
  uploadProgress.value = []
}

// ==================== 我的文件抽屉事件 ====================
/** 抽屉切换文件选中态：增删 selectedTracks（单一数据源在父级） */
function onDrawerToggle(file: ScannedFileDTO, selected: boolean) {
  if (selected) {
    if (!selectedTracks.value.some((t) => t.path === file.path)) {
      selectedTracks.value.push({ path: file.path, name: file.name, indexed: file.indexed })
    }
  } else {
    const idx = selectedTracks.value.findIndex((t) => t.path === file.path)
    if (idx > -1) selectedTracks.value.splice(idx, 1)
  }
}

/** 抽屉「加载选中文件」：触发浏览器重新渲染（抽屉自行关闭） */
function onDrawerLoad() {
  loadBrowser()
}
</script>

<template>
  <div class="jbrowse-page" role="main" aria-label="Web 基因组浏览器">
    <PageHeader
      title="Web 基因组浏览器"
      subtitle="基于 JBrowse 2 · 支持 BAM / BigWig / VCF / GFF3 流式浏览"
      back-to="/tools"
      back-label="返回工具箱"
    />

    <section class="browser-toolbar" aria-label="基因组浏览器工具栏">
      <div class="toolbar-primary">
        <span class="ctrl-label">参考基因组</span>
        <NSelect
          v-model:value="selectedAssembly"
          :options="assemblyOptions"
          :loading="assembliesLoading"
          placeholder="选择参考基因组"
          size="small"
          :render-label="renderAssemblyLabel"
          class="assembly-select"
          @update:value="onAssemblyChange"
        />
        <NInput
          v-model:value="regionInput"
          placeholder="chr1:1,000,000-2,000,000"
          size="small"
          class="region-input"
          @blur="regionInput = formatRegion(regionInput)"
          @keyup.enter="jumpToRegion"
        />
        <NButton class="jump-button" size="small" type="primary" @click="jumpToRegion">
          <template #icon><NIcon><LocationOutline /></NIcon></template>
          跳转
        </NButton>
      </div>
      <div class="toolbar-actions">
        <NButton class="outline-button" size="small" @click="showUploadModal = true">
          <template #icon><NIcon><CloudUploadOutline /></NIcon></template>
          上传文件
        </NButton>
        <NButton class="outline-button" size="small" @click="showScanDrawer = true">
          <template #icon><NIcon><FolderOpenOutline /></NIcon></template>
          我的文件
        </NButton>
      </div>
    </section>

    <!-- 已选轨道 -->
    <div v-if="selectedTracks.length > 0" class="track-bar">
      <span class="track-label">已选轨道：</span>
      <NSpace :size="6" wrap>
        <NTag
          v-for="track in selectedTracks"
          :key="track.path"
          closable
          type="info"
          size="small"
          @close="removeTrack(track)"
        >
          {{ track.name }}
          <template v-if="!track.indexed" #avatar>
            <span style="color: #d03050">待索引</span>
          </template>
        </NTag>
      </NSpace>
    </div>

    <!-- JBrowse 2 渲染区（flex:1 铺满剩余高度，iframe 100% 继承） -->
    <div class="browser-view">
      <div v-if="loading" class="loading-mask">
        <NSpin size="large" />
        <p class="loading-text">{{ loadingText }}</p>
      </div>
      <iframe
        v-if="jbrowseUrl"
        :key="iframeKey"
        :src="jbrowseUrl"
        frameborder="0"
        class="jbrowse-iframe"
        @load="onIframeLoad"
      />
      <div v-else-if="!loading" class="empty-state">
        <NEmpty>
          <template #icon><NIcon :size="64"><DesktopOutline /></NIcon></template>
          <div class="empty-desc">
            <p class="empty-title">基因组浏览器未加载</p>
            <p class="empty-hint">请选择参考基因组；若持续未加载，请检查 FASTA/.fai 是否完整、/tracks/ 是否可达</p>
          </div>
        </NEmpty>
      </div>
    </div>

    <!-- 上传弹窗 -->
    <NModal
      v-model:show="showUploadModal"
      preset="card"
      title="上传轨道文件"
      style="width: 600px; max-width: 92vw"
      :mask-closable="false"
    >
      <NForm label-placement="top">
        <NFormItem label="选择文件" required>
          <NUpload
            v-model:file-list="uploadFileList"
            :default-upload="false"
            multiple
            :max="5"
            accept=".bam,.cram,.bw,.bigwig,.vcf,.vcf.gz,.bed,.bed.gz,.gff3,.gff3.gz,.fasta,.fa"
          >
            <NUploadDragger>
              <div class="upload-drag">
                <NIcon :size="36" class="upload-icon"><CloudUploadOutline /></NIcon>
                <p class="upload-title">点击或拖拽文件到此处上传</p>
                <p class="upload-hint">支持 BAM / BigWig / VCF / BED / GFF3 / FASTA，单个文件最大 10GB</p>
              </div>
            </NUploadDragger>
          </NUpload>
        </NFormItem>
        <NFormItem label="关联参考基因组">
          <NSelect
            v-model:value="uploadForm.assemblyId"
            :options="assemblyOptions"
            placeholder="可选：关联参考基因组"
            clearable
          />
        </NFormItem>
        <NFormItem>
          <NCheckbox v-model:checked="uploadForm.autoIndex">上传后自动创建索引（推荐）</NCheckbox>
        </NFormItem>
      </NForm>

      <NDivider v-if="uploadProgress.length > 0" style="margin: 8px 0" />
      <div v-if="uploadProgress.length > 0" class="upload-progress">
        <div v-for="item in uploadProgress" :key="item.filename" class="progress-item">
          <div class="progress-header">
            <span class="progress-name">{{ item.filename }}</span>
            <NTag
              size="small"
              :type="item.status === 'success' ? 'success' : item.status === 'error' ? 'error' : 'info'"
            >
              {{ item.statusText }}
            </NTag>
          </div>
          <NProgress
            v-if="item.status === 'uploading'"
            :percentage="item.percent"
            size="small"
            :show-indicator="false"
          />
          <p v-if="item.message" class="progress-msg">{{ item.message }}</p>
        </div>
      </div>

      <template #footer>
        <NSpace justify="end">
          <NButton @click="showUploadModal = false">取消</NButton>
          <NButton type="primary" :loading="uploadProgress.some((p) => p.status === 'uploading')" @click="handleUpload">
            开始上传
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- 我的文件抽屉（独立组件：扫描 / 搜索 / 勾选 / 加载）-->
    <JbrowseFileDrawer
      v-model:show="showScanDrawer"
      :selected-paths="selectedPaths"
      @toggle="onDrawerToggle"
      @load="onDrawerLoad"
    />
  </div>
</template>

<style scoped>
/* ===== 全高 flex 布局：依赖路由 meta.fullscreen 提供有界高度的 flex 链 ===== */
.jbrowse-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--neutral-bg);
  box-sizing: border-box;
  padding: 40px 24px 24px;
}

.browser-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  flex-shrink: 0;
  padding: 12px 16px;
  border: 1px solid var(--neutral-border, #e5e7eb);
  border-radius: 12px;
  background: var(--neutral-card, #fff);
}
.toolbar-primary,
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.toolbar-actions { margin-left: auto; }
.browser-toolbar :deep(.n-button),
.browser-toolbar :deep(.n-base-selection),
.browser-toolbar :deep(.n-input) { height: 36px; border-radius: 8px; }
.assembly-select { width: 240px; min-width: 240px; }
.region-input { width: 220px; min-width: 220px; }
.outline-button { border-color: #d1d5db; color: #374151; background: #fff; }
.outline-button:hover { border-color: #9ca3af; color: #1f2937; }
.assembly-option { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.assembly-name { color: #111827; font-size: 14px; white-space: nowrap; }
.assembly-species { color: #6b7280; font-size: 12px; font-style: italic; white-space: nowrap; }
.ctrl-label {
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
  white-space: nowrap;
}

/* ===== 已选轨道条 ===== */
.track-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 16px;
  background: var(--neutral-card, #fff);
  border-bottom: 1px solid var(--neutral-border, #e5e6eb);
  flex-wrap: wrap;
}
.track-label {
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
  white-space: nowrap;
}

/* ===== JBrowse 渲染区：flex:1 铺满，iframe 100% 继承 ===== */
.browser-view {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
  background: var(--neutral-card, #fff);
}
.jbrowse-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
.loading-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.75);
  z-index: 10;
}
.loading-text {
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
  margin: 0;
}
:root[data-theme="dark"] .loading-mask {
  background: rgba(21, 26, 37, 0.75);
}
.empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 8px 0 4px;
}
.empty-hint {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  max-width: 360px;
}

/* ===== 上传 ===== */
.upload-drag {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 20px;
}
.upload-icon {
  color: var(--neutral-text-3, #86909c);
  margin-bottom: 8px;
}
.upload-title {
  font-size: 14px;
  color: var(--neutral-text-2, #4e5969);
  margin: 0 0 4px;
}
.upload-hint {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  margin: 0;
}
.upload-progress {
  margin-top: 4px;
}
.progress-item {
  margin-bottom: 12px;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.progress-name {
  font-size: 13px;
  color: var(--neutral-text-1, #1d2129);
}
.progress-msg {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  margin: 4px 0 0;
}

@media (max-width: 768px) {
  .jbrowse-page { padding: 24px 12px 16px; }
  .browser-toolbar { align-items: stretch; flex-direction: column; }
  .toolbar-primary, .toolbar-actions { width: 100%; flex-wrap: wrap; margin-left: 0; }
  .toolbar-primary { align-items: stretch; }
  .toolbar-primary .ctrl-label { width: 100%; }
  .assembly-select, .region-input { flex: 1 1 100%; width: 100%; min-width: 0; }
  .toolbar-actions :deep(.n-button) { flex: 1 1 0; }
  .ctrl-label {
    display: none;
  }
}
</style>
