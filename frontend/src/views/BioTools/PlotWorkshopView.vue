<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NSelect, NUpload, NSpace } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, ScatterChart, HeatmapChart, BoxplotChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  VisualMapComponent, TitleComponent,
} from 'echarts/components'

use([
  CanvasRenderer, BarChart, LineChart, ScatterChart, HeatmapChart, BoxplotChart,
  GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, TitleComponent,
])

const router = useRouter()

const chartType = ref('bar')
const xColumn = ref('Gene')
const yColumn = ref('Expression')
const colorScheme = ref('viridis')
const hasFile = ref(false)
const fileName = ref('')

const chartTypeOptions = [
  { label: '柱状图', value: 'bar' },
  { label: '折线图', value: 'line' },
  { label: '散点图', value: 'scatter' },
  { label: '热图', value: 'heatmap' },
  { label: '箱线图', value: 'boxplot' },
]

const columnOptions = [
  { label: 'Gene', value: 'Gene' },
  { label: 'Expression', value: 'Expression' },
  { label: 'log2FC', value: 'log2FC' },
  { label: 'p-value', value: 'p-value' },
  { label: 'Sample', value: 'Sample' },
  { label: 'Condition', value: 'Condition' },
]

const colorOptions = [
  { label: 'Viridis', value: 'viridis' },
  { label: '红蓝渐变', value: 'red-blue' },
  { label: '暖色调', value: 'warm' },
  { label: '冷色调', value: 'cool' },
]

function handleFileSelect({ file }: { file: UploadFileInfo }) {
  hasFile.value = true
  fileName.value = file.name
  return false
}

const genes = ['TP53', 'BRCA1', 'EGFR', 'MYC', 'KRAS', 'PTEN', 'RB1', 'APC', 'VHL', 'CDH1']
const samples = ['Sample_A', 'Sample_B', 'Sample_C', 'Sample_D', 'Sample_E']

const chartOption = computed(() => {
  const seed = hasFile.value ? 42 : 7
  const rand = (i: number, max: number) => ((Math.sin(seed + i * 127.1) * 43758.5453) % 1 + 1) % 1 * max

  if (chartType.value === 'bar') {
    return {
      tooltip: { trigger: 'axis' as const },
      xAxis: { type: 'category' as const, data: genes, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value' as const, name: yColumn.value },
      series: [{
        type: 'bar' as const,
        data: genes.map((_, i) => +(rand(i, 100)).toFixed(1)),
        itemStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#165DFF' },
              { offset: 1, color: '#6B8DD6' },
            ],
          },
          borderRadius: [4, 4, 0, 0],
        },
      }],
      grid: { left: 50, right: 20, top: 20, bottom: 60 },
    }
  }

  if (chartType.value === 'line') {
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['Control', 'Treatment'], top: 4 },
      xAxis: { type: 'category' as const, data: samples },
      yAxis: { type: 'value' as const, name: yColumn.value },
      series: [
        { name: 'Control', type: 'line' as const, data: samples.map((_, i) => +(rand(i, 80) + 20).toFixed(1)), smooth: true, lineStyle: { width: 2 } },
        { name: 'Treatment', type: 'line' as const, data: samples.map((_, i) => +(rand(i + 10, 90) + 10).toFixed(1)), smooth: true, lineStyle: { width: 2 } },
      ],
      grid: { left: 50, right: 20, top: 40, bottom: 30 },
    }
  }

  if (chartType.value === 'scatter') {
    return {
      tooltip: {
        formatter: (p: any) => `${genes[p.dataIndex]}<br/>${xColumn.value}: ${p.value[0]}<br/>${yColumn.value}: ${p.value[1]}`,
      },
      xAxis: { type: 'value' as const, name: xColumn.value },
      yAxis: { type: 'value' as const, name: yColumn.value },
      series: [{
        type: 'scatter' as const,
        data: genes.map((_, i) => [+(rand(i, 10) - 5).toFixed(2), +(rand(i + 5, 8) - 4).toFixed(2)]),
        symbolSize: 12,
        itemStyle: { color: '#8E54E9' },
      }],
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
    }
  }

  if (chartType.value === 'heatmap') {
    const data: number[][] = []
    genes.forEach((_, gi) => {
      samples.forEach((_, si) => {
        data.push([si, gi, +(rand(gi * 10 + si, 6) - 3).toFixed(2)])
      })
    })
    return {
      tooltip: { position: 'top' as const },
      xAxis: { type: 'category' as const, data: samples, splitArea: { show: true } },
      yAxis: { type: 'category' as const, data: genes, splitArea: { show: true } },
      visualMap: {
        min: -3, max: 3, calculable: true, orient: 'horizontal' as const,
        left: 'center', bottom: 0,
        inRange: { color: ['#165DFF', '#f5f5f5', '#F53F3F'] },
      },
      series: [{
        type: 'heatmap' as const, data,
        label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
      }],
      grid: { left: 80, right: 20, top: 10, bottom: 60 },
    }
  }

  return {
    tooltip: { trigger: 'item' as const },
    xAxis: { type: 'category' as const, data: samples },
    yAxis: { type: 'value' as const, name: yColumn.value },
    series: [{
      type: 'boxplot' as const,
      data: samples.map((_, i) => {
        const base = rand(i, 50) + 20
        return [base - 15, base - 5, base, base + 8, base + 20].map((v) => +v.toFixed(1))
      }),
      itemStyle: { color: '#165DFF', borderColor: '#165DFF' },
    }],
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
  }
})
</script>

<template>
  <div class="plot-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回工具箱
      </NButton>
      <h1 class="page-title">组学绘图工坊</h1>
    </div>

    <div class="plot-layout">
      <aside class="config-panel">
        <div class="panel-section">
          <h3 class="section-title">数据文件</h3>
          <NUpload accept=".csv,.tsv,.txt" :max="1" :default-upload="false" @change="handleFileSelect">
            <NButton size="small" block>上传 CSV / TSV</NButton>
          </NUpload>
          <p class="file-hint" v-if="hasFile">{{ fileName }}</p>
          <p class="file-hint" v-else>未选择文件时使用 Mock 数据演示</p>
        </div>

        <div class="panel-section">
          <h3 class="section-title">图表类型</h3>
          <NSelect v-model:value="chartType" :options="chartTypeOptions" />
        </div>

        <div class="panel-section">
          <h3 class="section-title">X 轴</h3>
          <NSelect v-model:value="xColumn" :options="columnOptions" />
        </div>

        <div class="panel-section">
          <h3 class="section-title">Y 轴</h3>
          <NSelect v-model:value="yColumn" :options="columnOptions" />
        </div>

        <div class="panel-section">
          <h3 class="section-title">配色方案</h3>
          <NSelect v-model:value="colorScheme" :options="colorOptions" />
        </div>

        <NButton type="primary" block class="generate-btn">
          生成图表
        </NButton>
      </aside>

      <main class="canvas-area">
        <div class="canvas-card">
          <VChart :option="chartOption" autoresize class="plot-chart" />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.plot-page {
  padding: 24px;
  min-height: 100%;
}
.page-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0;
}
.plot-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 20px;
  align-items: start;
}
.config-panel {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 20px;
}
.panel-section {
  margin-bottom: 18px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0 0 8px;
}
.file-hint {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  margin: 6px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.generate-btn {
  margin-top: 4px;
}
.canvas-area {
  min-height: 480px;
}
.canvas-card {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 20px;
}
.plot-chart {
  height: 480px;
}
@media (max-width: 900px) {
  .plot-layout {
    grid-template-columns: 1fr;
  }
}
</style>
