<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  NAlert, NButton, NDataTable, NEmpty, NIcon, NInput, NRadioButton, NRadioGroup,
  NSwitch, NTag, useMessage,
  type DataTableColumns,
} from 'naive-ui'
import {
  AddOutline, CopyOutline, DownloadOutline, SparklesOutline, TrashOutline,
} from '@vicons/ionicons5'
import {
  computeRegions, describeRegion, genSampleLists, parseListText,
  type NamedSet,
} from '@/utils/vennUpsetProcessor'
import PageHeader from '@/components/PageHeader.vue'
import { useThemeStore } from '@/stores/theme'

const message = useMessage()
const themeStore = useThemeStore()

const MIN_LISTS = 2
const MAX_LISTS = 6

interface ListEntry {
  id: number
  name: string
  text: string
}

let listSeq = 0
function newList(name = '', text = ''): ListEntry {
  listSeq += 1
  return { id: listSeq, name, text }
}

const lists = ref<ListEntry[]>([newList('集合 A'), newList('集合 B')])
const caseSensitive = ref(false)
const viewMode = ref<'auto' | 'venn' | 'upset'>('auto')

type Selection = { kind: 'region'; key: string } | { kind: 'set'; index: number } | null
const selection = ref<Selection>(null)

/* ---------- 颜色（从 CSS 变量解析，导出 SVG/PNG 时不含 var() 引用） ---------- */

const CHART_FALLBACKS = ['#165DFF', '#F53F3F', '#00B42A', '#8E54E9', '#FF7D00', '#14C8D4']
const palette = ref<string[]>([...CHART_FALLBACKS])
const textColor = ref('#1d2129')
const subTextColor = ref('#86909c')
const cardColor = ref('#ffffff')
const primaryColor = ref('#165DFF')
const dotMutedColor = ref('#e5e6eb')

function resolveColors() {
  const cs = getComputedStyle(document.documentElement)
  palette.value = CHART_FALLBACKS.map(
    (fb, i) => cs.getPropertyValue(`--kimi-chart-${i + 1}`).trim() || fb,
  )
  textColor.value = cs.getPropertyValue('--neutral-text-1').trim() || '#1d2129'
  subTextColor.value = cs.getPropertyValue('--neutral-text-3').trim() || '#86909c'
  cardColor.value = cs.getPropertyValue('--neutral-card').trim() || '#ffffff'
  primaryColor.value = cs.getPropertyValue('--arco-primary').trim() || '#165DFF'
  dotMutedColor.value = cs.getPropertyValue('--neutral-border').trim() || '#e5e6eb'
}

function setColor(i: number): string {
  return palette.value[i % palette.value.length]
}

/* ---------- 数据管线 ---------- */

const parsedLists = computed(() =>
  lists.value.map((l) => ({ ...l, parsed: parseListText(l.text, caseSensitive.value) })),
)

const nonEmptySets = computed<NamedSet[]>(() =>
  parsedLists.value
    .filter((l) => l.parsed.items.length > 0)
    .map((l) => ({ name: l.name.trim() || '未命名集合', items: l.parsed.items })),
)

const emptyListNames = computed(() =>
  parsedLists.value.filter((l) => !l.parsed.items.length).map((l) => l.name.trim() || '未命名集合'),
)

const regions = computed(() => computeRegions(nonEmptySets.value, caseSensitive.value))

const effectiveMode = computed<'venn' | 'upset'>(() => {
  const n = nonEmptySets.value.length
  if (viewMode.value === 'venn' && n >= 2 && n <= 3) return 'venn'
  if (viewMode.value === 'upset' && n >= 2) return 'upset'
  return n <= 3 ? 'venn' : 'upset'
})

watch(
  () => parsedLists.value.map((l) => `${l.text}|${l.name}`).join('') + caseSensitive.value,
  () => { selection.value = null },
)

function addList() {
  if (lists.value.length >= MAX_LISTS) return
  lists.value.push(newList(`集合 ${String.fromCharCode(65 + lists.value.length)}`))
}

function removeList(id: number) {
  if (lists.value.length <= MIN_LISTS) return
  lists.value = lists.value.filter((l) => l.id !== id)
}

function loadSample(silent = false) {
  const samples = genSampleLists()
  while (lists.value.length < samples.length) addList()
  samples.forEach((s, i) => {
    lists.value[i].name = s.name
    lists.value[i].text = s.text
  })
  if (!silent) message.success('已载入示例数据（3 个基因列表）')
}

function refresh() {
  resolveColors()
  message.success('图表已根据当前列表刷新')
}

/* ---------- 韦恩图布局 ---------- */

interface CircleSpec { cx: number; cy: number; r: number }
interface PointSpec { x: number; y: number }

const VENN_VIEWBOX = '0 0 560 400'
const VENN_LAYOUT: Record<number, { circles: CircleSpec[]; labels: Record<string, PointSpec>; names: PointSpec[] }> = {
  2: {
    circles: [
      { cx: 215, cy: 190, r: 130 },
      { cx: 345, cy: 190, r: 130 },
    ],
    labels: { '0': { x: 165, y: 190 }, '1': { x: 395, y: 190 }, '0,1': { x: 280, y: 190 } },
    names: [{ x: 150, y: 50 }, { x: 410, y: 50 }],
  },
  3: {
    circles: [
      { cx: 225, cy: 160, r: 118 },
      { cx: 335, cy: 160, r: 118 },
      { cx: 280, cy: 250, r: 118 },
    ],
    labels: {
      '0': { x: 195, y: 125 },
      '1': { x: 365, y: 125 },
      '2': { x: 280, y: 345 },
      '0,1': { x: 280, y: 112 },
      '0,2': { x: 190, y: 255 },
      '1,2': { x: 370, y: 255 },
      '0,1,2': { x: 280, y: 195 },
    },
    names: [{ x: 150, y: 50 }, { x: 410, y: 50 }, { x: 280, y: 392 }],
  },
}

const vennLayout = computed(() => VENN_LAYOUT[nonEmptySets.value.length] ?? null)

const vennRegions = computed(() => {
  const layout = vennLayout.value
  if (!layout) return []
  const names = nonEmptySets.value.map((s) => s.name)
  return regions.value
    .filter((r) => layout.labels[r.key])
    .map((r) => ({
      ...r,
      x: layout.labels[r.key].x,
      y: layout.labels[r.key].y,
      label: describeRegion(r.indices, names),
    }))
})

/* ---------- UpSet 图布局 ---------- */

const UPSET_MAX_COLS = 24
const UPSET = { leftPad: 150, colW: 44, topPad: 26, barAreaH: 130, gapY: 14, rowH: 28, bottomPad: 16 }

interface UpsetCol {
  key: string
  label: string
  count: number
  x: number
  barH: number
  barY: number
  memberRows: number[]
  selected: boolean
}

const upsetCols = computed<UpsetCol[]>(() => {
  const sets = nonEmptySets.value
  const names = sets.map((s) => s.name)
  const sorted = [...regions.value].sort(
    (a, b) => b.elements.length - a.elements.length || a.key.localeCompare(b.key),
  )
  const cols = sorted.slice(0, UPSET_MAX_COLS)
  const maxCount = Math.max(1, ...cols.map((c) => c.elements.length))
  return cols.map((r, i) => {
    const barH = Math.max(2, (r.elements.length / maxCount) * UPSET.barAreaH)
    return {
      key: r.key,
      label: describeRegion(r.indices, names),
      count: r.elements.length,
      x: UPSET.leftPad + i * UPSET.colW,
      barH,
      barY: UPSET.topPad + UPSET.barAreaH - barH,
      memberRows: r.indices,
      selected: selection.value?.kind === 'region' && selection.value.key === r.key,
    }
  })
})

const upsetTruncated = computed(() => regions.value.length > UPSET_MAX_COLS)

const upsetGeom = computed(() => {
  const nCols = upsetCols.value.length
  const nSets = nonEmptySets.value.length
  const matrixTop = UPSET.topPad + UPSET.barAreaH + UPSET.gapY
  return {
    width: UPSET.leftPad + nCols * UPSET.colW + 12,
    height: matrixTop + nSets * UPSET.rowH + UPSET.bottomPad,
    matrixTop,
    colCenter: (i: number) => UPSET.leftPad + i * UPSET.colW + UPSET.colW / 2 - 3,
    rowCenter: (i: number) => matrixTop + i * UPSET.rowH + UPSET.rowH / 2,
  }
})

function truncateName(name: string, max = 12): string {
  return name.length > max ? `${name.slice(0, max)}…` : name
}

/* ---------- 选中区域与结果表 ---------- */

const selectedElements = computed<string[]>(() => {
  const sel = selection.value
  if (!sel) return []
  if (sel.kind === 'set') {
    return [...(nonEmptySets.value[sel.index]?.items ?? [])].sort((a, b) => a.localeCompare(b))
  }
  return regions.value.find((r) => r.key === sel.key)?.elements ?? []
})

const selectedTitle = computed(() => {
  const sel = selection.value
  if (!sel) return ''
  const names = nonEmptySets.value.map((s) => s.name)
  if (sel.kind === 'set') return `${names[sel.index] ?? ''}（全部元素）`
  const r = regions.value.find((x) => x.key === sel.key)
  return r ? describeRegion(r.indices, names) : ''
})

function selectRegion(key: string) {
  selection.value = { kind: 'region', key }
}

function selectSet(index: number) {
  selection.value = { kind: 'set', index }
}

function isRegionSelected(key: string): boolean {
  return selection.value?.kind === 'region' && selection.value.key === key
}

interface ElementRow { value: string }
const elementColumns: DataTableColumns<ElementRow> = [
  { title: '元素 ID', key: 'value', sorter: (a, b) => a.value.localeCompare(b.value) },
]
const elementRows = computed<ElementRow[]>(() => selectedElements.value.map((v) => ({ value: v })))

async function copyElements() {
  if (!selectedElements.value.length) {
    message.warning('暂无可复制的元素')
    return
  }
  try {
    await navigator.clipboard.writeText(selectedElements.value.join('\n'))
    message.success(`已复制 ${selectedElements.value.length} 个元素`)
  } catch {
    message.error('复制失败，请手动选择文本')
  }
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function exportCsv() {
  if (!selectedElements.value.length) {
    message.warning('暂无可导出的元素')
    return
  }
  const content = `element\n${selectedElements.value.join('\n')}\n`
  downloadBlob(new Blob([content], { type: 'text/csv;charset=utf-8' }), 'venn_upset_elements.csv')
}

/* ---------- 图表导出 ---------- */

const svgRef = ref<SVGSVGElement | null>(null)

function buildExportSvg(): string | null {
  const svg = svgRef.value
  if (!svg) return null
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const vb = svg.viewBox.baseVal
  clone.setAttribute('width', String(Math.round(vb.width)))
  clone.setAttribute('height', String(Math.round(vb.height)))
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('width', '100%')
  bg.setAttribute('height', '100%')
  bg.setAttribute('fill', cardColor.value)
  clone.insertBefore(bg, clone.firstChild)
  return new XMLSerializer().serializeToString(clone)
}

function exportSvg() {
  const data = buildExportSvg()
  if (!data) {
    message.warning('暂无可导出的图表')
    return
  }
  downloadBlob(new Blob([data], { type: 'image/svg+xml;charset=utf-8' }), 'venn_upset_plot.svg')
}

function exportPng() {
  const data = buildExportSvg()
  const svg = svgRef.value
  if (!data || !svg) {
    message.warning('暂无可导出的图表')
    return
  }
  const vb = svg.viewBox.baseVal
  const scale = 2
  const url = URL.createObjectURL(new Blob([data], { type: 'image/svg+xml;charset=utf-8' }))
  const img = new Image()
  img.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(vb.width * scale)
    canvas.height = Math.round(vb.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      URL.revokeObjectURL(url)
      message.error('导出失败：无法创建画布')
      return
    }
    ctx.fillStyle = cardColor.value
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    URL.revokeObjectURL(url)
    canvas.toBlob((blob) => {
      if (blob) downloadBlob(blob, 'venn_upset_plot.png')
      else message.error('导出 PNG 失败')
    }, 'image/png')
  }
  img.onerror = () => {
    URL.revokeObjectURL(url)
    message.error('导出 PNG 失败')
  }
  img.src = url
}

/* ---------- 生命周期 ---------- */

onMounted(() => {
  resolveColors()
  if (parsedLists.value.every((l) => !l.parsed.items.length)) loadSample(true)
})

watch(
  () => themeStore.isDark,
  async () => {
    await nextTick()
    resolveColors()
  },
)
</script>

<template>
  <div class="venn-upset-page">
    <PageHeader
      title="Venn / UpSet 集合分析"
      subtitle="2~3 个集合绘制韦恩图，4~6 个集合自动切换 UpSet 图，全部在浏览器本地完成"
      back-to="/tools"
      back-label="返回工具箱"
    >
      <template #actions>
        <NButton size="small" quaternary @click="loadSample()">
          <template #icon><NIcon><SparklesOutline /></NIcon></template>
          示例数据
        </NButton>
        <NButton size="small" type="primary" @click="refresh">生成图表</NButton>
      </template>
    </PageHeader>

    <NAlert type="info" class="local-alert" :bordered="false">
      纯本地运算，数据不离开浏览器
    </NAlert>

    <div class="venn-upset-layout">
      <!-- 左：列表输入 -->
      <aside class="param-panel">
        <div class="panel-header">
          <span class="panel-title">集合列表（{{ lists.length }}/{{ MAX_LISTS }}）</span>
          <NButton size="tiny" secondary :disabled="lists.length >= MAX_LISTS" @click="addList">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            添加列表
          </NButton>
        </div>

        <div class="case-switch">
          <span>区分大小写</span>
          <NSwitch v-model:value="caseSensitive" size="small" />
        </div>

        <NAlert v-if="emptyListNames.length && nonEmptySets.length" type="warning" class="empty-alert" :bordered="false">
          列表「{{ emptyListNames.join('、') }}」为空，已自动忽略空列表。
        </NAlert>

        <div v-for="(l, i) in parsedLists" :key="l.id" class="list-card">
          <div class="list-card-head">
            <span class="list-dot" :style="{ background: setColor(i) }" />
            <NInput v-model:value="l.name" size="small" placeholder="列表名称" class="list-name" />
            <NTag size="small" :bordered="false">{{ l.parsed.items.length }} 条</NTag>
            <NButton
              size="tiny" quaternary circle
              :disabled="lists.length <= MIN_LISTS"
              @click="removeList(l.id)"
            >
              <template #icon><NIcon><TrashOutline /></NIcon></template>
            </NButton>
          </div>
          <NInput
            v-model:value="l.text"
            type="textarea"
            :autosize="{ minRows: 5, maxRows: 12 }"
            placeholder="粘贴基因 / ID 列表，支持换行、逗号、空格、Tab 混合分隔"
          />
          <div v-if="l.parsed.dupCount > 0" class="dup-hint">
            已自动去除 {{ l.parsed.dupCount }} 个重复条目
          </div>
        </div>
      </aside>

      <!-- 右：图表与结果 -->
      <main class="work-area">
        <div class="work-card">
          <div class="chart-toolbar">
            <NRadioGroup v-model:value="viewMode" size="small">
              <NRadioButton value="auto">自动</NRadioButton>
              <NRadioButton value="venn" :disabled="nonEmptySets.length > 3">韦恩图</NRadioButton>
              <NRadioButton value="upset">UpSet</NRadioButton>
            </NRadioGroup>
            <div class="chart-actions">
              <NButton size="tiny" secondary :disabled="nonEmptySets.length < 2" @click="exportPng">
                <template #icon><NIcon><DownloadOutline /></NIcon></template>PNG
              </NButton>
              <NButton size="tiny" secondary :disabled="nonEmptySets.length < 2" @click="exportSvg">
                <template #icon><NIcon><DownloadOutline /></NIcon></template>SVG
              </NButton>
            </div>
          </div>

          <NEmpty v-if="nonEmptySets.length < 2" description="至少需要 2 个非空列表才能绘制，请在左侧粘贴数据或载入示例" class="chart-empty" />

          <!-- 韦恩图（2~3 个集合） -->
          <svg
            v-else-if="effectiveMode === 'venn' && vennLayout"
            ref="svgRef"
            :viewBox="VENN_VIEWBOX"
            class="chart-svg"
            role="img"
          >
            <circle
              v-for="(c, i) in vennLayout.circles"
              :key="`c${i}`"
              :cx="c.cx" :cy="c.cy" :r="c.r"
              :fill="setColor(i)" fill-opacity="0.22"
              :stroke="setColor(i)" stroke-width="2"
              class="venn-circle"
              @click="selectSet(i)"
            >
              <title>{{ nonEmptySets[i].name }}：共 {{ nonEmptySets[i].items.length }} 个元素</title>
            </circle>
            <text
              v-for="(p, i) in vennLayout.names"
              :key="`n${i}`"
              :x="p.x" :y="p.y"
              text-anchor="middle"
              class="venn-name"
              :fill="setColor(i)"
            >{{ truncateName(nonEmptySets[i].name, 14) }}</text>
            <g
              v-for="r in vennRegions"
              :key="r.key"
              class="venn-region"
              @click="selectRegion(r.key)"
            >
              <title>{{ r.label }}：{{ r.elements.length }} 个元素（独占）</title>
              <circle
                :cx="r.x" :cy="r.y" r="24"
                :fill="primaryColor"
                :fill-opacity="isRegionSelected(r.key) ? 0.18 : 0"
                class="region-hit"
              />
              <text
                :x="r.x" :y="r.y"
                text-anchor="middle" dominant-baseline="central"
                class="region-count"
                :fill="textColor"
              >{{ r.elements.length }}</text>
            </g>
          </svg>

          <!-- UpSet 图（4~6 个集合或手动切换） -->
          <svg
            v-else
            ref="svgRef"
            :viewBox="`0 0 ${upsetGeom.width} ${upsetGeom.height}`"
            class="chart-svg"
            role="img"
          >
            <!-- 集合行标签 -->
            <g v-for="(s, i) in nonEmptySets" :key="`s${i}`">
              <circle :cx="14" :cy="upsetGeom.rowCenter(i)" r="5" :fill="setColor(i)" />
              <text
                :x="26" :y="upsetGeom.rowCenter(i)"
                dominant-baseline="central" class="upset-set-name" :fill="textColor"
              >{{ truncateName(s.name) }} ({{ s.items.length }})</text>
            </g>
            <!-- 交集列 -->
            <g
              v-for="(col, ci) in upsetCols"
              :key="col.key"
              class="upset-col"
              @click="selectRegion(col.key)"
            >
              <title>{{ col.label }}：{{ col.count }} 个元素</title>
              <rect
                :x="col.x" :y="8"
                :width="UPSET.colW - 8" :height="upsetGeom.height - 24"
                :fill="primaryColor" :fill-opacity="col.selected ? 0.1 : 0"
                class="col-hit"
              />
              <rect
                :x="col.x + 6" :y="col.barY"
                :width="UPSET.colW - 20" :height="col.barH"
                :fill="primaryColor" :fill-opacity="col.selected ? 1 : 0.75"
                rx="2"
              />
              <text
                :x="col.x + (UPSET.colW - 8) / 2" :y="col.barY - 4"
                text-anchor="middle" class="upset-count" :fill="subTextColor"
              >{{ col.count }}</text>
              <!-- 连接线 -->
              <line
                v-if="col.memberRows.length > 1"
                :x1="upsetGeom.colCenter(ci)" :x2="upsetGeom.colCenter(ci)"
                :y1="upsetGeom.rowCenter(Math.min(...col.memberRows))"
                :y2="upsetGeom.rowCenter(Math.max(...col.memberRows))"
                :stroke="textColor" stroke-width="2" stroke-opacity="0.7"
              />
              <!-- 点阵 -->
              <circle
                v-for="(s, ri) in nonEmptySets"
                :key="`d${ri}`"
                :cx="upsetGeom.colCenter(ci)" :cy="upsetGeom.rowCenter(ri)"
                r="6"
                :fill="col.memberRows.includes(ri) ? setColor(ri) : dotMutedColor"
              />
            </g>
          </svg>
          <div v-if="effectiveMode === 'upset' && upsetTruncated" class="truncate-hint">
            交集组合较多，仅展示元素数最多的前 {{ UPSET_MAX_COLS }} 个组合
          </div>
        </div>

        <!-- 选中区域元素表 -->
        <div class="work-card">
          <div class="panel-header">
            <span class="panel-title">
              {{ selection ? `${selectedTitle} · ${selectedElements.length} 个元素` : '点击图中区域查看元素列表' }}
            </span>
            <div class="chart-actions">
              <NButton size="tiny" secondary :disabled="!selectedElements.length" @click="copyElements">
                <template #icon><NIcon><CopyOutline /></NIcon></template>复制
              </NButton>
              <NButton size="tiny" secondary :disabled="!selectedElements.length" @click="exportCsv">
                <template #icon><NIcon><DownloadOutline /></NIcon></template>CSV
              </NButton>
            </div>
          </div>
          <NDataTable
            v-if="selection"
            :columns="elementColumns"
            :data="elementRows"
            size="small"
            :pagination="{ pageSize: 10 }"
            :max-height="320"
          />
          <NEmpty v-else description="点击韦恩图区域或 UpSet 柱子，此处展示该交集的元素" />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.venn-upset-page {
  padding: 16px;
  min-height: 100%;
}

.local-alert {
  margin-bottom: 12px;
}

.venn-upset-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
  align-items: start;
}

.param-panel,
.work-card {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 12px;
}

.param-panel {
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
}

.case-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
  margin-bottom: 10px;
}

.empty-alert {
  margin-bottom: 10px;
}

.list-card {
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 10px;
  padding: 10px;
  margin-bottom: 10px;
}

.list-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.list-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.list-name {
  flex: 1;
  min-width: 0;
}

.dup-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
}

.work-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.chart-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.chart-actions {
  display: flex;
  gap: 8px;
}

.chart-empty {
  padding: 48px 0;
}

.chart-svg {
  width: 100%;
  height: auto;
  display: block;
}

.venn-circle,
.venn-region,
.upset-col {
  cursor: pointer;
}

.venn-name {
  font-size: 14px;
  font-weight: 600;
}

.region-count {
  font-size: 15px;
  font-weight: 600;
  pointer-events: none;
}

.region-hit {
  transition: fill-opacity 0.15s;
}

.venn-region:hover .region-hit {
  fill-opacity: 0.14;
}

.upset-set-name {
  font-size: 12px;
}

.upset-count {
  font-size: 11px;
}

.col-hit {
  transition: fill-opacity 0.15s;
}

.upset-col:hover .col-hit {
  fill-opacity: 0.08;
}

.truncate-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
}

@media (max-width: 1200px) {
  .venn-upset-layout {
    grid-template-columns: 1fr;
  }
  .param-panel {
    max-height: none;
  }
}

@media (max-width: 768px) {
  .venn-upset-page {
    padding: 12px;
  }
}
</style>
