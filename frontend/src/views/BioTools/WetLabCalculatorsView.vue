<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, CustomChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption } from 'echarts/core'
import {
  NAlert, NButton, NCard, NDataTable, NIcon, NInput, NInputNumber,
  NRadioButton, NRadioGroup, NSelect, NTabPane, NTabs, NTag, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { DownloadOutline, FlaskOutline, SparklesOutline } from '@vicons/ionicons5'
import PageHeader from '@/components/PageHeader.vue'
import { useThemeStore } from '@/stores/theme'
import {
  CONC_FACTORS, DIL_CONC_UNITS, DIL_VOL_UNITS, MASS_FACTORS, NUC_MW_PER_NT,
  VOL_FACTORS, computeQpcr, formatNum, friendlySI, genSampleCtData,
  ngUlToNm, nmToNgUl, parseCtTable, solveDilution, solveMolar, toCsv,
  type DilConcUnit, type DilVolUnit, type MolarTarget,
  type NucleicType, type QpcrDetailRow,
} from '@/utils/wetLabProcessor'

use([CanvasRenderer, GridComponent, LegendComponent, TooltipComponent, BarChart, CustomChart])

const message = useMessage()
const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark)

// ---------------------------------------------------------------------------
// 子计算器 1：母液稀释
// ---------------------------------------------------------------------------
const dilC1 = ref<number | null>(100)
const dilC2 = ref<number | null>(10)
const dilV2 = ref<number | null>(100)
const dilConcUnit = ref<DilConcUnit>('µM')
const dilVolUnit = ref<DilVolUnit>('µL')

const dilution = computed(() =>
  solveDilution({
    c1: dilC1.value, c2: dilC2.value, v2: dilV2.value,
    concUnit: dilConcUnit.value, volUnit: dilVolUnit.value,
  }),
)

function loadDilSample() {
  dilC1.value = 100
  dilC2.value = 10
  dilV2.value = 100
  dilConcUnit.value = 'µM'
  dilVolUnit.value = 'µL'
  message.info('已载入示例：100 µM 母液稀释为 10 µM、100 µL 工作液')
}

// ---------------------------------------------------------------------------
// 子计算器 2：qPCR 2^-ΔΔCt
// ---------------------------------------------------------------------------
const ctText = ref('')
const controlGroup = ref('')
const errorType = ref<'sd' | 'sem'>('sd')

const ctParsed = computed(() => parseCtTable(ctText.value))
const groupOptions = computed(() =>
  ctParsed.value.groups.map((g) => ({ label: g, value: g })),
)
const activeControl = computed(() => {
  if (controlGroup.value && ctParsed.value.groups.includes(controlGroup.value)) {
    return controlGroup.value
  }
  return ctParsed.value.groups[0] ?? ''
})
const qpcrResult = computed(() => computeQpcr(ctParsed.value.rows, activeControl.value))

const qpcrColumns = computed<DataTableColumns<QpcrDetailRow>>(() => [
  { title: '样本', key: 'sample', sorter: (a, b) => a.sample.localeCompare(b.sample) },
  { title: '分组', key: 'group' },
  { title: '目的基因 Ct', key: 'targetCt', sorter: (a, b) => a.targetCt - b.targetCt },
  { title: '内参 Ct', key: 'refCt' },
  {
    title: 'ΔCt', key: 'dCt', sorter: (a, b) => a.dCt - b.dCt,
    render: (r) => r.dCt.toFixed(3),
  },
  {
    title: 'ΔΔCt', key: 'ddCt', sorter: (a, b) => a.ddCt - b.ddCt,
    render: (r) => r.ddCt.toFixed(3),
  },
  {
    title: '2^-ΔΔCt', key: 'relExp', sorter: (a, b) => a.relExp - b.relExp,
    render: (r) => r.relExp.toFixed(3),
  },
])

const chartOption = computed<EChartsCoreOption>(() => {
  const textColor = isDark.value ? '#c9cdd4' : '#4e5969'
  const axisColor = isDark.value ? '#3a3a3c' : '#e5e6eb'
  if (!('groupStats' in qpcrResult.value)) return {}
  const stats = qpcrResult.value.groupStats
  const names = stats.map((s) => s.group)
  const means = stats.map((s) => +s.mean.toFixed(3))
  return {
    grid: { top: 40, right: 24, bottom: 40, left: 64 },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number }[]
        const i = arr[0]?.dataIndex ?? 0
        const s = stats[i]
        return `${s.group}<br/>均值: ${s.mean.toFixed(3)}<br/>SD: ${s.sd.toFixed(3)}<br/>SEM: ${s.sem.toFixed(3)}<br/>n = ${s.n}`
      },
    },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { color: textColor },
      axisLine: { lineStyle: { color: axisColor } },
    },
    yAxis: {
      type: 'value',
      name: '相对表达量',
      nameTextStyle: { color: textColor },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: axisColor } },
    },
    series: [
      {
        type: 'bar',
        data: means,
        barMaxWidth: 48,
        itemStyle: { color: '#165DFF', borderRadius: [4, 4, 0, 0] },
      },
      {
        type: 'custom',
        renderItem: (_params: unknown, api: {
          value: (i: number) => number
          coord: (v: [number, number]) => number[]
          size: (v: [number, number]) => number[]
        }) => {
          const x = api.coord([api.value(0), api.value(1)])[0]
          const yHigh = api.coord([0, api.value(1) + api.value(2)])[1]
          const yLow = api.coord([0, Math.max(api.value(1) - api.value(2), 0)])[1]
          const cap = 6
          const style = { stroke: isDark.value ? '#86909c' : '#4e5969', lineWidth: 1.5 }
          return {
            type: 'group',
            children: [
              { type: 'line', shape: { x1: x, y1: yHigh, x2: x, y2: yLow }, style },
              { type: 'line', shape: { x1: x - cap, y1: yHigh, x2: x + cap, y2: yHigh }, style },
              { type: 'line', shape: { x1: x - cap, y1: yLow, x2: x + cap, y2: yLow }, style },
            ],
          }
        },
        data: stats.map((s, i) => [i, +s.mean.toFixed(3), +(errorType.value === 'sd' ? s.sd : s.sem).toFixed(3)]),
        tooltip: { show: false },
        z: 10,
      },
    ],
  }
})

const chartRef = ref<InstanceType<typeof VChart> | null>(null)

function loadQpcrSample() {
  ctText.value = genSampleCtData()
  controlGroup.value = '对照组'
  message.info('已载入示例 Ct 数据（对照组 / 处理组，各 3 个样本）')
}

function exportChartPng() {
  if (!chartRef.value || !('groupStats' in qpcrResult.value)) {
    message.warning('暂无可导出的图表')
    return
  }
  try {
    const url = chartRef.value.getDataURL({
      type: 'png',
      pixelRatio: 3,
      backgroundColor: isDark.value ? '#1d1d1f' : '#ffffff',
    })
    const a = document.createElement('a')
    a.href = url
    a.download = `qpcr_relative_expression_${Date.now()}.png`
    a.click()
    message.success('已导出 PNG')
  } catch {
    message.error('导出失败')
  }
}

function exportQpcrCsv() {
  if (!('details' in qpcrResult.value)) {
    message.warning('暂无数据可导出')
    return
  }
  const rows = qpcrResult.value.details.map((d) => [
    d.sample, d.group, d.targetCt, d.refCt,
    d.dCt.toFixed(3), d.ddCt.toFixed(3), d.relExp.toFixed(3),
  ])
  downloadText(toCsv(['样本', '分组', '目的基因Ct', '内参Ct', 'ΔCt', 'ΔΔCt', '2^-ΔΔCt'], rows), 'qpcr_details.csv')
}

function downloadText(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
  message.success(`已导出 ${filename}`)
}

// ---------------------------------------------------------------------------
// 子计算器 3：摩尔浓度换算
// ---------------------------------------------------------------------------
const molarTarget = ref<MolarTarget>('mass')
const molarMw = ref<number | null>(180.16)
const molarMass = ref<number | null>(18)
const molarMassUnit = ref('mg')
const molarVol = ref<number | null>(100)
const molarVolUnit = ref('mL')
const molarConc = ref<number | null>(1)
const molarConcUnit = ref('mM')

const massUnitOptions = Object.keys(MASS_FACTORS).map((u) => ({ label: u, value: u }))
const volUnitOptions = Object.keys(VOL_FACTORS).map((u) => ({ label: u, value: u }))
const concUnitOptions = Object.keys(CONC_FACTORS).map((u) => ({ label: u, value: u }))

const molar = computed(() =>
  solveMolar({
    target: molarTarget.value,
    mw: molarTarget.value === 'mw' ? null : molarMw.value,
    mass: molarTarget.value === 'mass' ? null : molarMass.value,
    massUnit: molarMassUnit.value,
    volume: molarTarget.value === 'volume' ? null : molarVol.value,
    volUnit: molarVolUnit.value,
    conc: molarTarget.value === 'conc' ? null : molarConc.value,
    concUnit: molarConcUnit.value,
  }),
)

const molarFriendly = computed(() =>
  molar.value.valid ? friendlySI(molar.value.value, molarTarget.value) : '—',
)

function loadMolarSample() {
  molarTarget.value = 'mass'
  molarMw.value = 180.16
  molarVol.value = 100
  molarVolUnit.value = 'mL'
  molarConc.value = 1
  molarConcUnit.value = 'mM'
  message.info('已载入示例：配制 100 mL 1 mM 葡萄糖溶液（MW 180.16）')
}

// ---------------------------------------------------------------------------
// 子计算器 4：核酸浓度换算
// ---------------------------------------------------------------------------
const nucDirection = ref<'ng2nm' | 'nm2ng'>('ng2nm')
const nucConc = ref<number | null>(50)
const nucLength = ref<number | null>(3000)
const nucType = ref<NucleicType>('dsDNA')

const nucTypeOptions = [
  { label: `双链 DNA（${NUC_MW_PER_NT.dsDNA} g/mol/bp）`, value: 'dsDNA' },
  { label: `单链 DNA（${NUC_MW_PER_NT.ssDNA} g/mol/nt）`, value: 'ssDNA' },
  { label: `单链 RNA（${NUC_MW_PER_NT.ssRNA} g/mol/nt）`, value: 'ssRNA' },
]

const nucResult = computed(() => {
  const c = nucConc.value
  const len = nucLength.value
  if (c === null || len === null) return null
  return nucDirection.value === 'ng2nm' ? ngUlToNm(c, len, nucType.value) : nmToNgUl(c, len, nucType.value)
})

function loadNucSample() {
  nucDirection.value = 'ng2nm'
  nucConc.value = 50
  nucLength.value = 3000
  nucType.value = 'dsDNA'
  message.info('已载入示例：50 ng/µL、3000 bp 双链 DNA 质粒')
}

// ---------------------------------------------------------------------------
// 通用示例入口
// ---------------------------------------------------------------------------
function loadSample() {
  const loaders = [loadDilSample, loadQpcrSample, loadMolarSample, loadNucSample]
  loaders[Number(activeTab.value) - 1]?.()
}

const activeTab = ref('1')
</script>

<template>
  <div class="wetlab-calculators-page">
    <PageHeader title="湿实验计算器" subtitle="母液稀释、qPCR 相对表达、摩尔浓度与核酸浓度换算" back-to="/tools" back-label="返回工具箱">
      <template #actions>
        <NButton size="small" quaternary @click="loadSample">
          <template #icon><NIcon><SparklesOutline /></NIcon></template>
          示例数据
        </NButton>
      </template>
    </PageHeader>

    <NAlert type="info" :bordered="false" class="local-alert">
      <template #icon><NIcon><FlaskOutline /></NIcon></template>
      纯本地运算，数据不离开浏览器
    </NAlert>

    <div class="wetlab-calculators-layout">
      <NTabs v-model:value="activeTab" type="line" animated>
        <!-- ============ 1. 母液稀释 ============ -->
        <NTabPane name="1" tab="母液稀释">
          <NCard size="small" :bordered="false">
            <div class="calc-grid">
              <div class="calc-form">
                <div class="form-row">
                  <span class="form-label">母液浓度 C1</span>
                  <NInputNumber v-model:value="dilC1" size="small" :show-button="false" :min="0" placeholder="如 100" />
                  <NSelect v-model:value="dilConcUnit" size="small" class="unit-select"
                    :options="DIL_CONC_UNITS.map((u) => ({ label: u, value: u }))" />
                </div>
                <div class="form-row">
                  <span class="form-label">目标浓度 C2</span>
                  <NInputNumber v-model:value="dilC2" size="small" :show-button="false" :min="0" placeholder="如 10" />
                  <span class="unit-fixed">{{ dilConcUnit }}</span>
                </div>
                <div class="form-row">
                  <span class="form-label">目标体积 V2</span>
                  <NInputNumber v-model:value="dilV2" size="small" :show-button="false" :min="0" placeholder="如 100" />
                  <NSelect v-model:value="dilVolUnit" size="small" class="unit-select"
                    :options="DIL_VOL_UNITS.map((u) => ({ label: u, value: u }))" />
                </div>
                <div class="formula-hint">C1·V1 = C2·V2 → V1 = C2·V2 / C1</div>
              </div>
              <div class="calc-result">
                <NAlert v-if="dilution.error" type="warning" :bordered="false">{{ dilution.error }}</NAlert>
                <template v-else-if="dilution.valid">
                  <div class="result-hero">
                    取母液 <b>{{ formatNum(dilution.v1uL) }} µL</b> + 水/溶剂 <b>{{ formatNum(dilution.solventuL) }} µL</b>
                  </div>
                  <div class="result-sub">
                    母液占终体积 {{ formatNum(dilution.ratio, 3) }}%（稀释 {{ formatNum((dilC1 ?? 0) / (dilC2 ?? 1), 3) }} 倍）
                  </div>
                </template>
                <div v-else class="result-empty">输入 C1、C2、V2 后自动计算</div>
              </div>
            </div>
          </NCard>
        </NTabPane>

        <!-- ============ 2. qPCR ============ -->
        <NTabPane name="2" tab="qPCR 相对表达">
          <NCard size="small" :bordered="false">
            <div class="qpcr-grid">
              <div class="calc-form">
                <div class="panel-title">粘贴 Ct 数据（Tab 分隔：样本名 | 分组 | 目的基因Ct | 内参Ct）</div>
                <NInput v-model:value="ctText" type="textarea" :autosize="{ minRows: 8, maxRows: 14 }"
                  placeholder="支持从 Excel 直接粘贴，如：&#10;Ctrl-1&#9;对照组&#9;22.35&#9;17.12&#10;Treat-1&#9;处理组&#9;19.82&#9;17.31" />
                <div class="qpcr-meta">
                  <NTag v-if="ctParsed.rows.length" size="small" type="success">
                    {{ ctParsed.rows.length }} 行有效
                  </NTag>
                  <NTag v-if="ctParsed.skipped.length" size="small" type="warning">
                    跳过 {{ ctParsed.skipped.length }} 行（表头/格式错误）
                  </NTag>
                </div>
                <div class="form-row">
                  <span class="form-label">对照组</span>
                  <NSelect v-model:value="controlGroup" size="small" :options="groupOptions"
                    placeholder="选择对照组" />
                </div>
                <div class="form-row">
                  <span class="form-label">误差棒</span>
                  <NRadioGroup v-model:value="errorType" size="small">
                    <NRadioButton value="sd">SD</NRadioButton>
                    <NRadioButton value="sem">SEM</NRadioButton>
                  </NRadioGroup>
                </div>
              </div>
              <div class="calc-result">
                <template v-if="'details' in qpcrResult">
                  <div class="chart-toolbar">
                    <span class="panel-title">相对表达量（对照组归一化为 1）</span>
                    <div>
                      <NButton size="tiny" secondary @click="exportChartPng">
                        <template #icon><NIcon><DownloadOutline /></NIcon></template>PNG
                      </NButton>
                      <NButton size="tiny" secondary style="margin-left: 8px" @click="exportQpcrCsv">
                        <template #icon><NIcon><DownloadOutline /></NIcon></template>CSV
                      </NButton>
                    </div>
                  </div>
                  <VChart ref="chartRef" :option="chartOption" autoresize class="qpcr-chart" />
                  <NDataTable size="small" :columns="qpcrColumns" :data="qpcrResult.details"
                    :pagination="{ pageSize: 10 }" :scroll-x="640" class="qpcr-table" />
                </template>
                <NAlert v-else-if="ctText.trim()" type="warning" :bordered="false">
                  {{ qpcrResult.error }}
                </NAlert>
                <div v-else class="result-empty">粘贴 Ct 数据后自动计算 2^-ΔΔCt</div>
              </div>
            </div>
          </NCard>
        </NTabPane>

        <!-- ============ 3. 摩尔浓度换算 ============ -->
        <NTabPane name="3" tab="摩尔浓度换算">
          <NCard size="small" :bordered="false">
            <div class="calc-grid">
              <div class="calc-form">
                <div class="form-row">
                  <span class="form-label">要求解的量</span>
                  <NRadioGroup v-model:value="molarTarget" size="small">
                    <NRadioButton value="mass">质量</NRadioButton>
                    <NRadioButton value="volume">体积</NRadioButton>
                    <NRadioButton value="conc">浓度</NRadioButton>
                    <NRadioButton value="mw">分子量</NRadioButton>
                  </NRadioGroup>
                </div>
                <div v-if="molarTarget !== 'mw'" class="form-row">
                  <span class="form-label">分子量 (g/mol)</span>
                  <NInputNumber v-model:value="molarMw" size="small" :show-button="false" :min="0" placeholder="如 180.16" />
                </div>
                <div v-if="molarTarget !== 'mass'" class="form-row">
                  <span class="form-label">质量</span>
                  <NInputNumber v-model:value="molarMass" size="small" :show-button="false" :min="0" placeholder="如 18" />
                  <NSelect v-model:value="molarMassUnit" size="small" class="unit-select" :options="massUnitOptions" />
                </div>
                <div v-if="molarTarget !== 'volume'" class="form-row">
                  <span class="form-label">体积</span>
                  <NInputNumber v-model:value="molarVol" size="small" :show-button="false" :min="0" placeholder="如 100" />
                  <NSelect v-model:value="molarVolUnit" size="small" class="unit-select" :options="volUnitOptions" />
                </div>
                <div v-if="molarTarget !== 'conc'" class="form-row">
                  <span class="form-label">浓度</span>
                  <NInputNumber v-model:value="molarConc" size="small" :show-button="false" :min="0" placeholder="如 1" />
                  <NSelect v-model:value="molarConcUnit" size="small" class="unit-select" :options="concUnitOptions" />
                </div>
                <div class="formula-hint">n = m / MW，c = n / V</div>
              </div>
              <div class="calc-result">
                <NAlert v-if="molar.error" type="warning" :bordered="false">{{ molar.error }}</NAlert>
                <template v-else-if="molar.valid">
                  <div class="result-hero">{{ molar.label }} = <b>{{ molarFriendly }}</b></div>
                  <div class="result-sub">SI 值：{{ formatNum(molar.value) }} {{ molar.unit }}</div>
                </template>
                <div v-else class="result-empty">输入其余三项后自动求解</div>
              </div>
            </div>
          </NCard>
        </NTabPane>

        <!-- ============ 4. 核酸浓度换算 ============ -->
        <NTabPane name="4" tab="核酸浓度换算">
          <NCard size="small" :bordered="false">
            <div class="calc-grid">
              <div class="calc-form">
                <div class="form-row">
                  <span class="form-label">换算方向</span>
                  <NRadioGroup v-model:value="nucDirection" size="small">
                    <NRadioButton value="ng2nm">ng/µL → nM</NRadioButton>
                    <NRadioButton value="nm2ng">nM → ng/µL</NRadioButton>
                  </NRadioGroup>
                </div>
                <div class="form-row">
                  <span class="form-label">{{ nucDirection === 'ng2nm' ? '浓度 (ng/µL)' : '浓度 (nM)' }}</span>
                  <NInputNumber v-model:value="nucConc" size="small" :show-button="false" :min="0" placeholder="如 50" />
                </div>
                <div class="form-row">
                  <span class="form-label">长度 (bp/nt)</span>
                  <NInputNumber v-model:value="nucLength" size="small" :show-button="false" :min="0" placeholder="如 3000" />
                </div>
                <div class="form-row">
                  <span class="form-label">核酸类型</span>
                  <NSelect v-model:value="nucType" size="small" :options="nucTypeOptions" />
                </div>
              </div>
              <div class="calc-result">
                <NAlert v-if="nucResult && nucResult.error" type="warning" :bordered="false">
                  {{ nucResult.error }}
                </NAlert>
                <template v-else-if="nucResult && nucResult.valid">
                  <div class="result-hero">
                    <b>{{ formatNum(nucResult.ngPerUl) }}</b> ng/µL ⇌ <b>{{ formatNum(nucResult.nM) }}</b> nM
                  </div>
                  <div class="result-sub">
                    分子量 ≈ {{ formatNum(nucResult.mw) }} g/mol（{{ nucType === 'dsDNA' ? '双链 DNA 660' : nucType === 'ssDNA' ? '单链 DNA 330' : '单链 RNA 340' }} g/mol/{{ nucType === 'dsDNA' ? 'bp' : 'nt' }}）
                  </div>
                </template>
                <div v-else class="result-empty">输入浓度与长度后自动换算</div>
              </div>
            </div>
          </NCard>
        </NTabPane>
      </NTabs>
    </div>
  </div>
</template>

<style scoped>
.wetlab-calculators-page {
  padding: 16px;
  min-height: 100%;
}
.local-alert {
  margin-bottom: 12px;
}
.wetlab-calculators-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}
.wetlab-calculators-layout :deep(.n-card) {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
}
.panel-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--neutral-text-2, #4e5969);
}
.calc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  align-items: start;
}
.qpcr-grid {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  align-items: start;
}
.calc-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.form-label {
  flex: 0 0 110px;
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
}
.unit-select {
  flex: 0 0 96px;
}
.unit-fixed {
  flex: 0 0 96px;
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
}
.formula-hint {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  padding-left: 118px;
}
.calc-result {
  background: var(--neutral-bg, #f7f8fa);
  border: 1px dashed var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 16px;
  min-height: 120px;
}
.result-hero {
  font-size: 18px;
  color: var(--neutral-text-1, #1d2129);
}
.result-hero b {
  color: var(--arco-primary, #165dff);
  font-size: 22px;
}
.result-sub {
  margin-top: 8px;
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
}
.result-empty {
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
  display: flex;
  align-items: center;
  min-height: 80px;
}
.qpcr-meta {
  display: flex;
  gap: 8px;
}
.chart-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.qpcr-chart {
  width: 100%;
  height: 320px;
}
.qpcr-table {
  margin-top: 12px;
}
@media (max-width: 1200px) {
  .calc-grid,
  .qpcr-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .wetlab-calculators-page {
    padding: 12px;
  }
  .form-label {
    flex-basis: 90px;
  }
  .formula-hint {
    padding-left: 98px;
  }
}
</style>
