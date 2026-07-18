<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NCollapse, NCollapseItem, NDataTable, NEmpty, NIcon, NInput, NInputNumber,
  NProgress, NRadioButton, NRadioGroup, NSelect, NSpace, NSpin, NSwitch, NUpload, useMessage,
  type UploadFileInfo,
} from 'naive-ui'
import {
  ArrowBackOutline, BuildOutline, DownloadOutline, ExpandOutline, SearchOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import { useThemeStore } from '@/stores/theme'
import PageHeader from '@/components/PageHeader.vue'
import {
  cancelTask, fetchPhyloMethods, getDownloadUrl, getTaskStatus, submitTreeBuild, uploadSequenceFile,
} from '@/api/phylo'
import type {
  AlignmentTool, PhyloMethodOption, PhyloMethodsResponse, PhyloSubmitRequest, PhyloTaskResponse,
  SequenceType, TreeLayout, TreeMethod, TreeStatistics,
} from '@/types/phylo'
import {
  computeTreeStatistics, createRenderOptions, downloadBlob, parseNewick,
  PhyloTreeRenderer, svgToPng,
} from '@/utils/phyloProcessor'

const router = useRouter()
const message = useMessage()
const themeStore = useThemeStore()

const POLLING_INTERVAL = 2000

const EXAMPLE_NEWICK = `((A:0.1,B:0.2)95:0.3,(C:0.4,D:0.5)88:0.6)100;`

// ---------------------------------------------------------------------------
// Refs / State
// ---------------------------------------------------------------------------

const treeContainerRef = ref<HTMLElement | null>(null)
const rendererRef = ref<PhyloTreeRenderer | null>(null)
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)

const fileId = ref('')
const fileName = ref('')
const newickString = ref('')
const taskId = ref('')
const isBuilding = ref(false)
const taskProgress = ref(0)
const taskPhase = ref('')
const taskMessage = ref('')
const searchKeyword = ref('')
const sequences = ref<Array<{ id: string; length: number }>>([])
const treeLoading = ref(false)

const methods = ref<PhyloMethodsResponse>({
  alignment_tools: [],
  tree_methods: [],
  substitution_models: {},
  bootstrap_types: [],
  presets: {},
})

const buildParams = reactive<PhyloSubmitRequest>({
  file_id: '',
  alignment_tool: 'mafft',
  alignment_mode: 'auto',
  tree_method: 'nj',
  substitution_model: 'auto',
  bootstrap_enabled: false,
  bootstrap_type: 'standard',
  bootstrap_replicates: 100,
  sequence_type: 'auto',
  advanced_params: '',
})

const vizConfig = reactive({
  layout: 'rectangular' as TreeLayout,
  isRooted: true,
  showLabels: true,
  showBootstrap: true,
  showScaleBar: true,
  alignTips: true,
  branchWidth: 1.5,
  fontSize: 12,
})

const treeStats = ref<TreeStatistics>({
  sequence_count: 0,
  total_branches: 0,
  total_tree_length: 0,
  mean_branch_length: 0,
  tree_height: 0,
  min_bootstrap: 0,
  max_bootstrap: 0,
  avg_bootstrap: 0,
  has_bootstrap_support: false,
})

const isDark = computed(() => themeStore.isDark)
const hasTree = computed(() => newickString.value.length > 0)

// ---------------------------------------------------------------------------
// 选项计算
// ---------------------------------------------------------------------------

const alignmentToolOptions = computed(() =>
  methods.value.alignment_tools.map((m: PhyloMethodOption) => ({ label: m.label, value: m.key })),
)

const treeMethodOptions = computed(() =>
  methods.value.tree_methods.map((m: PhyloMethodOption) => ({ label: m.label, value: m.key })),
)

const selectedTreeMethod = computed(() =>
  methods.value.tree_methods.find((m) => m.key === buildParams.tree_method),
)

const supportsBootstrap = computed(
  () => selectedTreeMethod.value?.supports_bootstrap ?? false,
)

watch(
  () => buildParams.tree_method,
  () => {
    if (!supportsBootstrap.value) {
      buildParams.bootstrap_enabled = false
    }
  },
)

const substitutionModelOptions = computed(() => {
  const dna = (methods.value.substitution_models.dna ?? []).map((m: string) => ({
    label: m,
    value: m,
  }))
  const protein = (methods.value.substitution_models.protein ?? []).map((m: string) => ({
    label: m,
    value: m,
  }))
  return buildParams.sequence_type === 'protein' ? protein : dna
})

watch(
  () => buildParams.sequence_type,
  () => {
    if (!substitutionModelOptions.value.some((o) => o.value === buildParams.substitution_model)) {
      buildParams.substitution_model = 'auto'
    }
  },
)

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

onMounted(async () => {
  rendererRef.value = new PhyloTreeRenderer()
  if (treeContainerRef.value) {
    await rendererRef.value.init(treeContainerRef.value, { zoom: true, brush: false })
  }
  loadExampleData()
  try {
    methods.value = await fetchPhyloMethods()
  } catch {
    message.warning('获取方法列表失败，使用默认选项')
  }
})

onUnmounted(() => {
  stopPolling()
  rendererRef.value?.destroy()
})

// ---------------------------------------------------------------------------
// 渲染与统计
// ---------------------------------------------------------------------------

async function renderTree(nwk: string) {
  if (!rendererRef.value) return
  treeLoading.value = true
  // 让 UI 先完成一帧绘制，再执行较重的 D3 渲染
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  const options = createRenderOptions(vizConfig, isDark.value)
  await rendererRef.value.render(nwk, options)
  try {
    const root = parseNewick(nwk)
    treeStats.value = computeTreeStatistics(root)
  } catch {
    /* 统计失败不影响渲染 */
  }
  treeLoading.value = false
}

async function updateTreeStyle() {
  if (!hasTree.value || !rendererRef.value) return
  const options = createRenderOptions(vizConfig, isDark.value)
  await rendererRef.value.updateOptions(options)
}

watch(
  () => newickString.value,
  (nwk) => {
    if (nwk) nextTick(() => renderTree(nwk))
  },
)

watch(
  () => vizConfig,
  () => {
    if (hasTree.value) updateTreeStyle()
  },
  { deep: true },
)

watch(isDark, () => {
  if (hasTree.value) updateTreeStyle()
})

// ---------------------------------------------------------------------------
// 文件上传
// ---------------------------------------------------------------------------

async function handleUpload({ file }: { file: UploadFileInfo }) {
  if (!file.file) return
  try {
    const resp = await uploadSequenceFile(file.file)
    fileId.value = resp.file_id
    fileName.value = resp.filename
    buildParams.file_id = resp.file_id
    buildParams.sequence_type = (resp.sequence_type === 'protein' ? 'protein' : 'auto') as SequenceType
    sequences.value = await parseSequencesFromFile(file.file)
    message.success(`已上传 ${resp.sequence_count ?? sequences.value.length} 条序列`)
  } catch (e) {
    message.error(`上传失败：${e instanceof Error ? e.message : '未知错误'}`)
  }
}

function parseSequencesFromFile(file: File): Promise<Array<{ id: string; length: number }>> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result || '')
      const lines = text.split(/\r?\n/)
      const result: Array<{ id: string; length: number }> = []
      let currentId = ''
      let currentSeq = ''
      const pushCurrent = () => {
        if (currentId) {
          result.push({ id: currentId, length: currentSeq.length })
        }
      }
      for (const line of lines) {
        if (line.startsWith('>')) {
          pushCurrent()
          currentId = line.slice(1).trim().split(/\s+/)[0]
          currentSeq = ''
        } else {
          currentSeq += line.trim()
        }
      }
      pushCurrent()
      resolve(result)
    }
    reader.onerror = () => resolve([])
    reader.readAsText(file)
  })
}

// ---------------------------------------------------------------------------
// 构建任务
// ---------------------------------------------------------------------------

async function buildTree() {
  if (!fileId.value) {
    message.warning('请先上传序列文件')
    return
  }
  isBuilding.value = true
  taskProgress.value = 0
  taskPhase.value = 'PENDING'
  taskMessage.value = '任务投递中...'
  try {
    const resp = await submitTreeBuild(buildParams)
    taskId.value = resp.task_id
    startPolling()
  } catch (e) {
    isBuilding.value = false
    message.error(`任务提交失败：${e instanceof Error ? e.message : '未知错误'}`)
  }
}

function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(async () => {
    if (!taskId.value) return
    try {
      const data: PhyloTaskResponse = await getTaskStatus(taskId.value)
      if (data.status === 'PROGRESS') {
        taskProgress.value = Math.round((data.progress || 0) * 100)
        taskPhase.value = data.phase || ''
        taskMessage.value = data.message || ''
      } else if (data.status === 'SUCCESS') {
        stopPolling()
        isBuilding.value = false
        const result = data.result
        if (result?.output_files?.newick) {
          try {
            const res = await fetch(getDownloadUrl(taskId.value, 'newick'))
            const nwk = await res.text()
            newickString.value = nwk
          } catch {
            newickString.value = ''
          }
        }
        if (result?.statistics) {
          treeStats.value = result.statistics
        }
        message.success('系统发育树构建完成')
      } else if (data.status === 'FAILURE') {
        stopPolling()
        isBuilding.value = false
        message.error(`构建失败：${data.message || '未知错误'}`)
      } else if (data.status === 'REVOKED') {
        stopPolling()
        isBuilding.value = false
        message.info('任务已取消')
      }
    } catch {
      /* 继续轮询 */
    }
  }, POLLING_INTERVAL)
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

async function cancelBuild() {
  if (!taskId.value) return
  try {
    await cancelTask(taskId.value)
    stopPolling()
    isBuilding.value = false
    message.info('已发送取消请求')
  } catch (e) {
    message.error(`取消失败：${e instanceof Error ? e.message : '未知错误'}`)
  }
}

// ---------------------------------------------------------------------------
// 示例数据
// ---------------------------------------------------------------------------

function loadExampleData() {
  newickString.value = EXAMPLE_NEWICK
  sequences.value = [
    { id: 'A', length: 500 },
    { id: 'B', length: 498 },
    { id: 'C', length: 502 },
    { id: 'D', length: 495 },
  ]
  fileName.value = 'example.nwk'
}

// ---------------------------------------------------------------------------
// 导出
// ---------------------------------------------------------------------------

function exportSVG() {
  const svg = rendererRef.value?.exportSVG()
  if (!svg) {
    message.warning('没有可导出的树')
    return
  }
  downloadBlob(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }), 'phylogenetic_tree.svg')
}

async function exportPNG() {
  const svg = rendererRef.value?.exportSVG()
  if (!svg) {
    message.warning('没有可导出的树')
    return
  }
  try {
    const blob = await svgToPng(svg)
    downloadBlob(blob, 'phylogenetic_tree.png')
  } catch (e) {
    message.error(`PNG 导出失败：${e instanceof Error ? e.message : '未知错误'}`)
  }
}

function exportNewick() {
  if (!newickString.value) {
    message.warning('没有可导出的 Newick')
    return
  }
  const nwk = rendererRef.value?.exportNewick() || newickString.value
  downloadBlob(new Blob([nwk], { type: 'text/plain;charset=utf-8' }), 'tree.nwk')
}

// ---------------------------------------------------------------------------
// 序列列表
// ---------------------------------------------------------------------------

const filteredSequences = computed(() => {
  const q = searchKeyword.value.trim().toLowerCase()
  if (!q) return sequences.value
  return sequences.value.filter((s) => s.id.toLowerCase().includes(q))
})

const sequenceColumns = [
  { title: '序列 ID', key: 'id' },
  { title: '长度', key: 'length' },
]

function highlightSequence(row: { id: string }) {
  rendererRef.value?.highlightNode(row.id)
}

function handleRowClick(row: unknown) {
  highlightSequence(row as { id: string })
}
</script>

<template>
  <div class="phylo-page">
    <PageHeader title="系统发育树构建" subtitle="上传序列、配置比对与建树参数，交互式查看系统发育关系" back-to="/tools" back-label="返回工具箱">
      <template #actions>
        <NButton size="small" quaternary @click="loadExampleData">
        <template #icon><NIcon><SparklesOutline /></NIcon></template>
        示例数据
      </NButton>
      </template>
    </PageHeader>

    <!-- 主体三栏 -->
    <div class="phylo-layout">
      <!-- 左：参数面板 -->
      <aside class="param-panel">
        <NCollapse default-expanded-names="data,alignment,tree,viz">
          <NCollapseItem title="数据输入" name="data">
            <NUpload
              accept=".fasta,.fa,.fas,.phylip,.phy,.nex,.nexus,.nwk,.newick"
              :max="1"
              :custom-request="handleUpload"
            >
              <NButton block>上传序列/Newick 文件</NButton>
            </NUpload>
            <p v-if="fileName" class="file-hint">已加载：{{ fileName }}</p>
            <p class="panel-hint">支持 FASTA、Phylip、NEXUS、Newick</p>
          </NCollapseItem>

          <NCollapseItem title="比对配置" name="alignment">
            <div class="form-row">
              <span class="form-label">比对工具</span>
              <NSelect v-model:value="buildParams.alignment_tool" :options="alignmentToolOptions" />
            </div>
            <div v-if="buildParams.alignment_tool !== 'prealigned'" class="form-row">
              <span class="form-label">模式</span>
              <NInput v-model:value="buildParams.alignment_mode" placeholder="auto" />
            </div>
          </NCollapseItem>

          <NCollapseItem title="树构建" name="tree">
            <div class="form-row">
              <span class="form-label">构建方法</span>
              <NSelect v-model:value="buildParams.tree_method" :options="treeMethodOptions" />
            </div>
            <div class="form-row">
              <span class="form-label">序列类型</span>
              <NRadioGroup v-model:value="buildParams.sequence_type">
                <NRadioButton value="auto">自动</NRadioButton>
                <NRadioButton value="dna">DNA</NRadioButton>
                <NRadioButton value="protein">蛋白质</NRadioButton>
              </NRadioGroup>
            </div>
            <div class="form-row">
              <span class="form-label">替代模型</span>
              <NSelect v-model:value="buildParams.substitution_model" :options="substitutionModelOptions" />
            </div>
            <div class="form-row">
              <NSwitch v-model:value="buildParams.bootstrap_enabled" :disabled="!supportsBootstrap" />
              <span class="switch-label">启用 Bootstrap</span>
            </div>
            <div v-if="buildParams.bootstrap_enabled" class="form-row">
              <span class="form-label">重复次数</span>
              <NInputNumber v-model:value="buildParams.bootstrap_replicates" :min="10" :max="10000" />
            </div>
            <div class="form-row">
              <span class="form-label">高级参数</span>
              <NInput v-model:value="buildParams.advanced_params" placeholder="额外命令行参数" />
            </div>
          </NCollapseItem>

          <NCollapseItem title="可视化" name="viz">
            <div class="form-row">
              <span class="form-label">布局</span>
              <NRadioGroup v-model:value="vizConfig.layout">
                <NRadioButton value="rectangular">矩形</NRadioButton>
                <NRadioButton value="circular">圆形</NRadioButton>
                <NRadioButton value="radial">径向</NRadioButton>
              </NRadioGroup>
            </div>
            <div class="form-row">
              <NSwitch v-model:value="vizConfig.showLabels" />
              <span class="switch-label">显示标签</span>
            </div>
            <div class="form-row">
              <NSwitch v-model:value="vizConfig.showBootstrap" />
              <span class="switch-label">显示 Bootstrap</span>
            </div>
            <div class="form-row">
              <NSwitch v-model:value="vizConfig.showScaleBar" />
              <span class="switch-label">显示比例尺</span>
            </div>
            <div class="form-row">
              <span class="form-label">分支宽度</span>
              <NInputNumber v-model:value="vizConfig.branchWidth" :min="0.5" :max="5" :step="0.5" />
            </div>
            <div class="form-row">
              <span class="form-label">字体大小</span>
              <NInputNumber v-model:value="vizConfig.fontSize" :min="8" :max="24" />
            </div>
          </NCollapseItem>
        </NCollapse>

        <div class="build-actions">
          <NButton type="primary" block :disabled="isBuilding || !fileId" @click="buildTree">
            <template #icon>
              <NIcon><BuildOutline /></NIcon>
            </template>
            构建系统发育树
          </NButton>
          <NButton v-if="isBuilding" block @click="cancelBuild">取消任务</NButton>
        </div>

        <div v-if="isBuilding" class="progress-area">
          <NProgress type="line" :percentage="taskProgress" :indicator-placement="'inside'" />
          <p class="phase-text">{{ taskPhase }} {{ taskMessage }}</p>
        </div>
      </aside>

      <!-- 中：工作区 -->
      <main class="work-card">
        <div ref="treeContainerRef" class="tree-container">
          <NEmpty v-if="!hasTree" description="请上传文件或加载示例数据" />
          <div v-if="treeLoading" class="tree-loading">
            <NSpin size="large" description="正在渲染树..." />
          </div>
        </div>
        <div class="work-actions">
          <NButton size="small" @click="exportSVG">
            <template #icon><NIcon><DownloadOutline /></NIcon></template>
            SVG
          </NButton>
          <NButton size="small" @click="exportPNG">
            <template #icon><NIcon><DownloadOutline /></NIcon></template>
            PNG
          </NButton>
          <NButton size="small" @click="exportNewick">
            <template #icon><NIcon><ExpandOutline /></NIcon></template>
            Newick
          </NButton>
        </div>
      </main>

      <!-- 右：统计与序列 -->
      <aside class="side-panel">
        <h3 class="panel-title">树统计信息</h3>
        <div class="stat-grid">
          <div class="stat-item">
            <span class="stat-label">序列数</span>
            <span class="stat-value">{{ treeStats.sequence_count }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">分支数</span>
            <span class="stat-value">{{ treeStats.total_branches }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">树高</span>
            <span class="stat-value">{{ treeStats.tree_height.toFixed(4) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">平均枝长</span>
            <span class="stat-value">{{ treeStats.mean_branch_length.toFixed(4) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Bootstrap 均值</span>
            <span class="stat-value">{{ treeStats.avg_bootstrap.toFixed(1) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Bootstrap 范围</span>
            <span class="stat-value">{{ treeStats.min_bootstrap }}-{{ treeStats.max_bootstrap }}</span>
          </div>
        </div>

        <h3 class="panel-title">节点搜索</h3>
        <NInput v-model:value="searchKeyword" placeholder="输入序列 ID">
          <template #prefix>
            <NIcon><SearchOutline /></NIcon>
          </template>
        </NInput>

        <h3 class="panel-title">序列列表</h3>
        <NDataTable
          :columns="sequenceColumns"
          :data="filteredSequences"
          :row-key="(row) => row.id"
          :max-height="240"
          size="small"
          @row-click="handleRowClick"
        />

        <div class="tips">
          <p>💡 操作提示</p>
          <ul>
            <li>滚轮缩放 / 拖拽平移</li>
            <li>点击节点可高亮</li>
            <li>支持重定根与折叠</li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.phylo-page {
  padding: 16px;
  min-height: 100%;
}
.page-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0;
  flex: 1;
}
.phylo-layout {
  display: grid;
  grid-template-columns: 300px 1fr 280px;
  gap: 16px;
  align-items: start;
}
.param-panel,
.work-card,
.side-panel {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 12px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
}
.work-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tree-container {
  min-height: 540px;
  position: relative;
  flex: 1;
}
.tree-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--neutral-card-rgb, 255, 255, 255), 0.8);
  z-index: 10;
}
.tree-container :deep(svg) {
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.work-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.form-label {
  width: 72px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--neutral-text-2);
}
.switch-label {
  font-size: 13px;
  color: var(--neutral-text-2);
}
.file-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--neutral-text-3);
  word-break: break-all;
}
.panel-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--neutral-text-3);
}
.build-actions {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.progress-area {
  margin-top: 12px;
}
.phase-text {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--neutral-text-3);
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 16px 0 8px;
}
.panel-title:first-child {
  margin-top: 0;
}
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.stat-item {
  background: var(--neutral-fill-2, #f2f3f5);
  border-radius: 8px;
  padding: 8px;
  display: flex;
  flex-direction: column;
}
.stat-label {
  font-size: 11px;
  color: var(--neutral-text-3);
}
.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-text-1);
}
.tips {
  margin-top: 16px;
  padding: 10px;
  background: var(--neutral-fill-2, #f2f3f5);
  border-radius: 8px;
  font-size: 12px;
  color: var(--neutral-text-3);
}
.tips p {
  margin: 0 0 4px;
  font-weight: 500;
}
.tips ul {
  margin: 0;
  padding-left: 16px;
}
@media (max-width: 1024px) {
  .phylo-layout {
    grid-template-columns: 1fr;
  }
}
</style>
