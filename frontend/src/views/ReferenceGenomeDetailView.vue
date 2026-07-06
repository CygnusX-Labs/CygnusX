<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NDataTable, NDrawer, NDrawerContent, NIcon, NInput, NSelect, NStatistic,
  NTabPane, NTabs, NTag, useMessage,
  type DataTableColumns,
} from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import {
  ArrowBackOutline, CopyOutline, DownloadOutline, SearchOutline, SwapHorizontalOutline,
} from '@vicons/ionicons5'
import {
  getGenomeById, MOCK_CHROMOSOMES, MOCK_FILES, MOCK_GENES, MOCK_GENE_TYPES,
  MOCK_ID_MAP, MOCK_ID_MAP_REVERSE, type Gene,
} from '@/mock/referenceGenomes'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent])

const route = useRoute()
const router = useRouter()
const message = useMessage()

const genome = computed(() => getGenomeById(route.params.id as string))

const activeTab = ref<'overview' | 'search' | 'mapping'>('overview')

// ===== 概览：染色体条形图 =====
const maxChromLength = Math.max(...MOCK_CHROMOSOMES.map((c) => c.length))
const selectedChrom = ref('')

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 12 } },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: false,
      label: { show: false },
      data: MOCK_GENE_TYPES.map((t) => ({ name: t.name, value: t.value, itemStyle: { color: t.color } })),
    },
  ],
}))

// ===== 基因搜索 =====
const searchField = ref<'geneId' | 'geneName' | 'annotation'>('geneId')
const searchQuery = ref('')
const searchFieldOptions = [
  { label: 'Gene ID', value: 'geneId' },
  { label: 'Gene Name', value: 'geneName' },
  { label: '功能注释', value: 'annotation' },
]

const filteredGenes = computed(() => {
  let list = MOCK_GENES
  if (selectedChrom.value) list = list.filter((g) => g.chromosome === selectedChrom.value)
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((g) => {
      if (searchField.value === 'geneId') return g.geneId.toLowerCase().includes(q)
      if (searchField.value === 'geneName') return g.geneName.toLowerCase().includes(q)
      return g.annotation.toLowerCase().includes(q)
    })
  }
  return list
})

const drawerVisible = ref(false)
const drawerGene = ref<Gene | null>(null)

function openDrawer(g: Gene) {
  drawerGene.value = g
  drawerVisible.value = true
}

function selectChrom(name: string) {
  selectedChrom.value = selectedChrom.value === name ? '' : name
  if (selectedChrom.value) activeTab.value = 'search'
}

const columns: DataTableColumns<Gene> = [
  { title: '基因ID', key: 'geneId', width: 120, render: (g) => h('span', { class: 'mono' }, g.geneId) },
  { title: '基因名', key: 'geneName', width: 110 },
  { title: '染色体', key: 'chromosome', width: 80 },
  { title: '位置', key: 'position', width: 180, render: (g) => `${g.start.toLocaleString()}-${g.end.toLocaleString()}` },
  { title: '长度', key: 'length', width: 90, render: (g) => `${g.length} bp` },
  { title: '功能注释', key: 'annotation', ellipsis: { tooltip: true } },
  {
    title: '操作', key: 'actions', width: 100,
    render: (g) => h(NButton, { size: 'tiny', tertiary: true, onClick: () => openDrawer(g) }, { default: () => '查看详情' }),
  },
]

// ===== 版本映射 =====
const mapDirection = ref<'v8tov11' | 'v11tov8'>('v8tov11')
const mapInput = ref('')
const mapResult = ref<{ input: string; output: string | null; status: 'success' | 'fail' }[]>([])

function runMap() {
  const ids = mapInput.value.split('\n').map((s) => s.trim()).filter(Boolean)
  if (!ids.length) {
    message.warning('请输入要转换的基因 ID（每行一个）')
    return
  }
  const map = mapDirection.value === 'v8tov11' ? MOCK_ID_MAP : MOCK_ID_MAP_REVERSE
  mapResult.value = ids.map((id) => ({
    input: id,
    output: map[id] || null,
    status: map[id] ? 'success' : 'fail',
  }))
  const ok = mapResult.value.filter((r) => r.status === 'success').length
  message.success(`转换完成：${ok}/${ids.length} 成功`)
}

function swapDirection() {
  mapDirection.value = mapDirection.value === 'v8tov11' ? 'v11tov8' : 'v8tov11'
  mapInput.value = ''
  mapResult.value = []
}

function downloadMap() {
  const content = mapResult.value
    .map((r) => `${r.input}\t${r.output || 'N/A'}\t${r.status}`)
    .join('\n')
  const blob = new Blob([`input\toutput\tstatus\n${content}`], { type: 'text/tsv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'id_mapping.tsv'
  a.click()
  URL.revokeObjectURL(url)
}

// ===== 文件清单复制 =====
async function copyPath(path: string) {
  try {
    await navigator.clipboard.writeText(path)
    message.success('路径已复制')
  } catch {
    message.error('复制失败')
  }
}

function setDefault() {
  message.success(`已将 ${genome.value?.commonName} ${genome.value?.version} 设为项目默认`)
}
</script>

<template>
  <div v-if="genome" class="detail-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/reference-genomes')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回基因组列表
      </NButton>
    </div>

    <div class="detail-layout">
      <!-- 左栏：信息面板 -->
      <aside class="info-panel">
        <div class="info-header">
          <div class="info-title">
            <span class="emoji">{{ genome.speciesEmoji }}</span>
            <span>{{ genome.commonName }} {{ genome.version }}</span>
          </div>
          <div class="info-subtitle">{{ genome.versionFull }} · 染色体级组装</div>
          <div class="info-tags">
            <NTag size="tiny" round>预置</NTag>
            <NTag v-for="t in genome.tags" :key="t" size="tiny" round :type="t.includes('最新') ? 'success' : 'info'">{{ t }}</NTag>
          </div>
        </div>

        <div class="stat-grid">
          <div class="stat-item"><NStatistic label="染色体数" :value="genome.chromosomes" /></div>
          <div class="stat-item"><NStatistic label="基因总数" :value="genome.totalGenes" /></div>
          <div class="stat-item"><NStatistic label="基因组大小" :value="genome.genomeSize" /></div>
          <div class="stat-item"><NStatistic label="N50" :value="genome.n50" /></div>
        </div>

        <div class="file-section">
          <div class="section-title">📁 参考文件</div>
          <div
            v-for="f in MOCK_FILES"
            :key="f.name"
            class="file-item"
            @click="copyPath(f.path)"
          >
            <div class="file-info">
              <div class="file-name">{{ f.name }}</div>
              <div class="file-size">{{ f.size }}</div>
            </div>
            <span class="file-status">✅</span>
            <NIcon class="copy-icon" :size="14"><CopyOutline /></NIcon>
          </div>
        </div>

        <div class="info-actions">
          <NButton size="small" type="primary" block @click="setDefault">设为项目默认</NButton>
          <NButton size="small" block quaternary>下载基因ID映射表</NButton>
        </div>
      </aside>

      <!-- 右栏：主内容 -->
      <main class="main-content">
        <NTabs v-model:value="activeTab" type="line" animated size="medium">
          <!-- Tab 1：概览 -->
          <NTabPane name="overview" tab="📊 概览">
            <div class="overview-section">
              <div class="block-title">
                染色体长度可视化
                <span v-if="selectedChrom" class="chrom-filter-hint">
                  已筛选：{{ selectedChrom }}
                  <NButton size="tiny" quaternary @click="selectedChrom = ''">清除</NButton>
                </span>
              </div>
              <div class="chrom-chart">
                <div
                  v-for="c in MOCK_CHROMOSOMES"
                  :key="c.name"
                  class="chrom-row"
                  :class="{ active: selectedChrom === c.name }"
                  @click="selectChrom(c.name)"
                >
                  <span class="chrom-name">{{ c.name }}</span>
                  <div class="chrom-bar-track">
                    <div
                      class="chrom-bar"
                      :style="{ width: `${(c.length / maxChromLength) * 100}%`, background: c.color }"
                    />
                  </div>
                  <span class="chrom-length">{{ (c.length / 1e6).toFixed(1) }} Mb</span>
                </div>
              </div>
            </div>

            <div class="overview-section">
              <div class="block-title">基因类型分布</div>
              <div class="pie-wrap">
                <VChart :option="pieOption" autoresize style="height: 280px" />
              </div>
            </div>
          </NTabPane>

          <!-- Tab 2：基因搜索 -->
          <NTabPane name="search" tab="🔍 基因搜索">
            <div class="search-bar">
              <NSelect
                v-model:value="searchField"
                :options="searchFieldOptions"
                size="small"
                style="width: 130px"
              />
              <NInput
                v-model:value="searchQuery"
                size="small"
                clearable
                placeholder="搜索基因ID、基因名、功能注释... 例如：LsG0001 或 MYB"
                style="flex: 1"
              >
                <template #prefix><NIcon><SearchOutline /></NIcon></template>
              </NInput>
            </div>

            <div v-if="selectedChrom" class="chrom-filter-hint">
              已按染色体 {{ selectedChrom }} 筛选
              <NButton size="tiny" quaternary @click="selectedChrom = ''">清除筛选</NButton>
            </div>

            <div v-if="filteredGenes.length" class="search-result">
              <div class="result-count">共 {{ filteredGenes.length }} 条结果</div>
              <NDataTable
                :columns="columns"
                :data="filteredGenes"
                :pagination="{ pageSize: 10 }"
                :bordered="true"
                size="small"
                :max-height="420"
              />
            </div>
            <div v-else class="search-empty">
              🌌 这片星空下没有找到该基因，换个关键词试试？
            </div>
          </NTabPane>

          <!-- Tab 3：版本映射 -->
          <NTabPane name="mapping" tab="🔄 版本映射">
            <div class="mapping-header">
              <div class="block-title">
                基因 ID 版本映射
                <span class="mapping-dir">{{ mapDirection === 'v8tov11' ? 'v8 → v11' : 'v11 → v8' }}</span>
              </div>
              <NButton size="small" quaternary @click="swapDirection">
                <template #icon><NIcon><SwapHorizontalOutline /></NIcon></template>交换方向
              </NButton>
            </div>

            <div class="mapping-layout">
              <div class="mapping-side">
                <div class="mapping-label">
                  输入 {{ mapDirection === 'v8tov11' ? 'v8' : 'v11' }} ID（每行一个）
                </div>
                <NInput
                  v-model:value="mapInput"
                  type="textarea"
                  :autosize="{ minRows: 8, maxRows: 14 }"
                  placeholder="Lsat_v8_0001&#10;Lsat_v8_0002&#10;..."
                  class="mono-input"
                />
                <NButton size="small" type="primary" block @click="runMap">
                  <template #icon><NIcon><SwapHorizontalOutline /></NIcon></template>
                  转换为 {{ mapDirection === 'v8tov11' ? 'v11' : 'v8' }}
                </NButton>
              </div>

              <div class="mapping-side">
                <div class="mapping-label">转换结果</div>
                <div class="mapping-result">
                  <div v-if="!mapResult.length" class="mapping-empty">等待转换...</div>
                  <div
                    v-for="r in mapResult"
                    :key="r.input"
                    class="mapping-row"
                    :class="{ fail: r.status === 'fail' }"
                  >
                    <span class="mono">{{ r.input }}</span>
                    <NIcon :size="12"><ArrowBackOutline class="rotate-90" /></NIcon>
                    <span class="mono">{{ r.output || '未找到' }}</span>
                    <NTag size="tiny" :type="r.status === 'success' ? 'success' : 'error'" round>
                      {{ r.status === 'success' ? '成功' : '未找到' }}
                    </NTag>
                  </div>
                </div>
                <NButton v-if="mapResult.length" size="small" block quaternary @click="downloadMap">
                  <template #icon><NIcon><DownloadOutline /></NIcon></template>下载映射表
                </NButton>
              </div>
            </div>
          </NTabPane>
        </NTabs>
      </main>
    </div>

    <!-- 基因详情抽屉 -->
    <NDrawer v-model:show="drawerVisible" :width="480" placement="right">
      <NDrawerContent v-if="drawerGene" :title="drawerGene.geneId" closable>
        <div class="gene-detail">
          <div class="gene-detail-row">
            <span class="gd-label">基因名</span>
            <span class="gd-value">{{ drawerGene.geneName }}</span>
          </div>
          <div class="gene-detail-row">
            <span class="gd-label">染色体</span>
            <span class="gd-value">{{ drawerGene.chromosome }}: {{ drawerGene.start.toLocaleString() }}-{{ drawerGene.end.toLocaleString() }} ({{ drawerGene.strand }})</span>
          </div>
          <div class="gene-detail-row">
            <span class="gd-label">长度</span>
            <span class="gd-value">{{ drawerGene.length.toLocaleString() }} bp</span>
          </div>
          <div class="gene-detail-row">
            <span class="gd-label">外显子数</span>
            <span class="gd-value">{{ drawerGene.exons }}</span>
          </div>
          <div class="gene-detail-row">
            <span class="gd-label">功能注释</span>
            <span class="gd-value">{{ drawerGene.annotation }}</span>
          </div>

          <div class="gene-structure-section">
            <div class="gd-label">外显子结构</div>
            <div class="gene-structure">
              <div class="strand-arrow">{{ drawerGene.strand === '+' ? '→' : '←' }}</div>
              <div class="exon-track">
                <template v-for="i in drawerGene.exons" :key="i">
                  <div v-if="i > 1" class="intron" />
                  <div class="exon" />
                </template>
              </div>
            </div>
            <div class="structure-hint">{{ drawerGene.chromosome }}: {{ drawerGene.start.toLocaleString() }} - {{ drawerGene.end.toLocaleString() }}</div>
          </div>
        </div>

        <template #footer>
          <NButton size="small" type="primary" @click="message.info('JBrowse 集成开发中')">
            在 JBrowse 中查看
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>
  </div>

  <!-- 基因组不存在 -->
  <div v-else class="not-found">
    <p class="empty-icon">🌌</p>
    <p>未找到该参考基因组</p>
    <NButton size="small" type="primary" @click="router.push('/reference-genomes')">返回列表</NButton>
  </div>
</template>

<style scoped>
.detail-page {
  min-height: 100%;
}
.page-toolbar {
  margin-bottom: 12px;
}
.detail-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  align-items: start;
}
.info-panel {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: sticky;
  top: 16px;
}
.info-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--neutral-text-1, #1e293b);
  display: flex;
  align-items: center;
  gap: 8px;
}
.info-title .emoji { font-size: 24px; }
.info-subtitle {
  font-size: 12px;
  color: var(--neutral-text-3, #94a3b8);
  margin-top: 4px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.info-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.stat-item {
  text-align: center;
  padding: 10px 6px;
  background: var(--neutral-bg, #f8fafc);
  border-radius: 8px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-1, #1e293b);
  margin-bottom: 8px;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}
.file-item:hover {
  background: var(--neutral-bg, #f8fafc);
}
.file-info { flex: 1; min-width: 0; }
.file-name {
  font-size: 13px;
  color: var(--neutral-text-1, #1e293b);
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.file-size {
  font-size: 11px;
  color: var(--neutral-text-3, #94a3b8);
}
.file-status { font-size: 12px; }
.copy-icon {
  color: var(--neutral-text-3, #94a3b8);
  opacity: 0;
  transition: opacity 0.2s;
}
.file-item:hover .copy-icon { opacity: 1; }
.info-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.main-content {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 16px;
  min-width: 0;
}
.block-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-text-1, #1e293b);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.chrom-filter-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--neutral-text-3, #94a3b8);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.overview-section { margin-bottom: 24px; }
.chrom-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chrom-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  transition: background 0.2s;
}
.chrom-row:hover, .chrom-row.active {
  background: var(--neutral-bg, #f8fafc);
}
.chrom-row.active {
  box-shadow: inset 0 0 0 1px rgba(124, 58, 237, 0.3);
}
.chrom-name {
  width: 48px;
  font-size: 12px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  color: var(--neutral-text-2, #475569);
}
.chrom-bar-track {
  flex: 1;
  height: 18px;
  background: var(--neutral-bg, #f1f5f9);
  border-radius: 4px;
  overflow: hidden;
}
.chrom-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}
.chrom-length {
  width: 64px;
  text-align: right;
  font-size: 12px;
  color: var(--neutral-text-3, #94a3b8);
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.pie-wrap { width: 100%; }

.search-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.result-count {
  font-size: 12px;
  color: var(--neutral-text-3, #94a3b8);
  margin-bottom: 8px;
}
.search-empty {
  padding: 40px;
  text-align: center;
  color: var(--neutral-text-3, #94a3b8);
  font-size: 14px;
}
:deep(.mono) {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}

.mapping-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.mapping-dir {
  font-size: 12px;
  font-weight: 400;
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
}
.mapping-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.mapping-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mapping-label {
  font-size: 12px;
  color: var(--neutral-text-2, #475569);
}
.mono-input :deep(textarea) {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}
.mapping-result {
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 8px;
  min-height: 200px;
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
}
.mapping-empty {
  padding: 40px 12px;
  text-align: center;
  color: var(--neutral-text-3, #c9cdd4);
  font-size: 13px;
}
.mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  border-bottom: 1px solid var(--neutral-border, #f0f1f5);
}
.mapping-row.fail { color: var(--neutral-text-3, #94a3b8); }
.mapping-row .mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.rotate-90 { transform: rotate(90deg); }

/* 基因详情抽屉 */
.gene-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gene-detail-row {
  display: flex;
  gap: 12px;
  font-size: 13px;
}
.gd-label {
  width: 72px;
  flex-shrink: 0;
  color: var(--neutral-text-3, #94a3b8);
}
.gd-value {
  color: var(--neutral-text-1, #1e293b);
  flex: 1;
}
.gene-structure-section {
  margin-top: 12px;
  padding: 16px;
  background: var(--neutral-bg, #f8fafc);
  border-radius: 8px;
}
.gene-structure {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 6px;
}
.strand-arrow {
  font-size: 18px;
  color: var(--neutral-text-3, #94a3b8);
}
.exon-track {
  flex: 1;
  display: flex;
  align-items: center;
  height: 24px;
}
.exon {
  width: 28px;
  height: 20px;
  background: linear-gradient(135deg, #3b82f6, #7c3aed);
  border-radius: 3px;
  flex-shrink: 0;
}
.intron {
  flex: 1;
  height: 2px;
  background: #cbd5e1;
  margin: 0 2px;
}
.structure-hint {
  font-size: 11px;
  color: var(--neutral-text-3, #94a3b8);
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.not-found {
  padding: 80px 24px;
  text-align: center;
  color: var(--neutral-text-3, #94a3b8);
}
.not-found .empty-icon {
  font-size: 48px;
  margin: 0 0 8px;
}
@media (max-width: 1024px) {
  .detail-layout { grid-template-columns: 1fr; }
  .info-panel { position: static; }
  .mapping-layout { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .stat-grid { grid-template-columns: 1fr; }
}
</style>
