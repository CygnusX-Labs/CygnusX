<script setup lang="ts">
import { computed } from 'vue'
import { NTooltip } from 'naive-ui'

interface HspData {
  hit_from: number
  hit_to: number
  identity_percent: number
  evalue: number
  bit_score: number
}

const props = withDefaults(defineProps<{
  hitLen: number
  hsps: HspData[]
  barHeight?: number
  showRuler?: boolean
}>(), {
  barHeight: 14,
  showRuler: true,
})

const svgWidth = 700
const padding = computed(() => ({
  left: props.showRuler ? 50 : 10,
  right: 30,
}))
const svgHeight = computed(() => props.barHeight + 16)

function scale(pos: number): number {
  return padding.value.left + (pos / props.hitLen) * (svgWidth - padding.value.left - padding.value.right)
}

function getColor(identity: number): string {
  if (identity >= 90) return '#10b981'
  if (identity >= 70) return '#3b82f6'
  if (identity >= 40) return '#f59e0b'
  return '#ef4444'
}
</script>

<template>
  <svg
    width="100%"
    :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
    style="font-family: monospace; font-size: 10px;"
  >
    <g v-if="showRuler">
      <line
        :x1="padding.left"
        :y1="barHeight / 2 + 6"
        :x2="svgWidth - padding.right"
        :y2="barHeight / 2 + 6"
        stroke="#e5e7eb"
        stroke-width="1.5"
      />
      <text
        :x="padding.left - 4"
        :y="barHeight / 2 + 10"
        text-anchor="end"
        fill="#9ca3af"
        font-size="9"
      >1</text>
      <text
        :x="svgWidth - padding.right + 4"
        :y="barHeight / 2 + 10"
        text-anchor="start"
        fill="#9ca3af"
        font-size="9"
      >{{ hitLen.toLocaleString() }}</text>
    </g>

    <NTooltip
      v-for="(hsp, idx) in hsps"
      :key="idx"
      placement="top"
      trigger="hover"
    >
      <template #trigger>
        <rect
          :x="scale(hsp.hit_from)"
          y="6"
          :width="Math.max(scale(hsp.hit_to) - scale(hsp.hit_from), 2)"
          :height="barHeight"
          rx="3"
          :fill="getColor(hsp.identity_percent)"
          opacity="0.9"
          style="cursor: pointer;"
        />
      </template>
      <div style="font-size: 12px; line-height: 1.5;">
        <div>Range: {{ hsp.hit_from }}-{{ hsp.hit_to }}</div>
        <div>Identity: {{ hsp.identity_percent.toFixed(1) }}%</div>
        <div>E: {{ hsp.evalue.toExponential(2) }}</div>
      </div>
    </NTooltip>
  </svg>
</template>
