<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NIcon, NSlider, NSwitch, NSpace, NUpload, NTag,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
} from 'echarts/components'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const router = useRouter()

const phredThreshold = ref(20)
const truncateLength = ref(150)
const removeAdapters = ref(true)
const selectedFile = ref<string>('sample_R1.fastq.gz')
const isProcessing = ref(false)

function handleFileSelect({ file }: { file: UploadFileInfo }) {
  selectedFile.value = file.name
  return false
}

const mockRetentionRate = computed(() => {
  const base = 92.5
  const phredPenalty = Math.max(0, (phredThreshold.value - 10) * 0.8)
  const lenPenalty = Math.max(0, (200 - truncateLength.value) * 0.05)
  return Math.max(40, base - phredPenalty - lenPenalty).toFixed(1)
})

const mockTotalReads = computed(() => {
  const base = 25_000_000
  const rate = parseFloat(mockRetentionRate.value) / 100
  return Math.round(base * rate).toLocaleString()
})

const mockGcContent = computed(() => {
  return (46.2 + (phredThreshold.value - 20) * 0.1).toFixed(1)
})

const qualityChartOption = computed(() => {
  const positions = Array.from({ length: 150 }, (_, i) => i + 1)
  const beforeQ = positions.map((pos) => {
    if (pos < 10) return 28 + Math.random() * 4
    if (pos < 80) return 34 + Math.random() * 3
    if (pos < 120) return 30 + Math.random() * 4
    return 24 + Math.random() * 6
  })
  const afterQ = positions
    .filter((pos) => pos <= truncateLength.value)
    .map((pos) => {
      const base = beforeQ[pos - 1]
      return pos < 10 ? base + 2 : Math.min(40, base + 3 + Math.random() * 2)
    })
  const filteredPositions = positions.filter((pos) => pos <= truncateLength.value)

  return {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['质控前', '质控后'], top: 8 },
    grid: { left: 50, right: 20, top: 44, bottom: 60 },
    xAxis: {
      type: 'category' as const,
      data: filteredPositions.map(String),
      name: '碱基位置 (bp)',
      nameLocation: 'center' as const,
      nameGap: 30,
    },
    yAxis: {
      type: 'value' as const,
      name: 'Phred 质量值',
      min: 15,
      max: 42,
    },
    dataZoom: [{ type: 'slider' as const, start: 0, end: 100, height: 20, bottom: 8 }],
    series: [
      {
        name: '质控前',
        type: 'line' as const,
        data: beforeQ.map((v) => +v.toFixed(1)),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#86909c' },
        areaStyle: { color: 'rgba(134,144,156,0.08)' },
      },
      {
        name: '质控后',
        type: 'line' as const,
        data: afterQ.map((v) => +v.toFixed(1)),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#165DFF' },
        areaStyle: { color: 'rgba(22,93,255,0.08)' },
      },
    ],
  }
})

function handleRunQC() {
  isProcessing.value = true
  setTimeout(() => { isProcessing.value = false }, 1500)
}
</script>

<template>
  <div class="fastq-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回工具箱
      </NButton>
      <h1 class="page-title">FASTQ 极速质控</h1>
    </div>

    <div class="fastq-layout">
      <aside class="param-panel">
        <div class="panel-section">
          <h3 class="section-title">输入文件</h3>
          <NUpload :max="1" accept=".fastq,.fq,.fastq.gz,.fq.gz" :default-upload="false" @change="handleFileSelect">
            <NButton size="small" block>选择 FASTQ 文件</NButton>
          </NUpload>
          <p class="selected-file" v-if="selectedFile">
            <NTag size="small" type="info" round>{{ selectedFile }}</NTag>
          </p>
        </div>

        <div class="panel-section">
          <h3 class="section-title">Phred 质量阈值</h3>
          <NSlider v-model:value="phredThreshold" :min="5" :max="35" :step="1" :format-tooltip="(v: number) => `Q${v}`" />
          <p class="param-hint">过滤掉平均质量低于 Q{{ phredThreshold }} 的 reads</p>
        </div>

        <div class="panel-section">
          <h3 class="section-title">截断长度</h3>
          <NSlider v-model:value="truncateLength" :min="50" :max="300" :step="10" :format-tooltip="(v: number) => `${v} bp`" />
          <p class="param-hint">将 reads 截断至 {{ truncateLength }} bp</p>
        </div>

        <div class="panel-section switch-row">
          <h3 class="section-title">去除接头序列</h3>
          <NSwitch v-model:value="removeAdapters" />
        </div>

        <NButton type="primary" block :loading="isProcessing" class="run-btn" @click="handleRunQC">
          开始质控
        </NButton>
      </aside>

      <main class="chart-area">
        <div class="stats-row">
          <div class="stat-card">
            <span class="stat-label">保留率</span>
            <span class="stat-value">{{ mockRetentionRate }}%</span>
          </div>
          <div class="stat-card">
            <span class="stat-label">保留 Reads</span>
            <span class="stat-value">{{ mockTotalReads }}</span>
          </div>
          <div class="stat-card">
            <span class="stat-label">GC 含量</span>
            <span class="stat-value">{{ mockGcContent }}%</span>
          </div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">碱基质量分布 (Per-base Quality)</h3>
          <VChart :option="qualityChartOption" autoresize class="quality-chart" />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.fastq-page {
  padding: 16px;
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
  color: var(--neutral-text-1);
  margin: 0;
}
.fastq-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  align-items: start;
}
.param-panel {
  background: var(--neutral-card);
  border: 1px solid var(--neutral-border);
  border-radius: 12px;
  padding: 20px;
}
.panel-section {
  margin-bottom: 20px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 0 0 10px;
}
.param-hint {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin: 8px 0 0;
}
.selected-file {
  margin: 8px 0 0;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.switch-row .section-title {
  margin: 0;
}
.run-btn {
  margin-top: 8px;
}
.chart-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.stat-card {
  background: var(--neutral-card);
  border: 1px solid var(--neutral-border);
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat-label {
  font-size: 12px;
  color: var(--neutral-text-3);
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--neutral-text-1);
  font-variant-numeric: tabular-nums;
}
.chart-card {
  background: var(--neutral-card);
  border: 1px solid var(--neutral-border);
  border-radius: 12px;
  padding: 16px 20px;
}
.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 0 0 12px;
}
.quality-chart {
  height: 360px;
}
@media (max-width: 900px) {
  .fastq-layout {
    grid-template-columns: 1fr;
  }
  .stats-row {
    grid-template-columns: 1fr;
  }
}
</style>
