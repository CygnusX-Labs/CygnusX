<script setup lang="ts">
import { computed } from 'vue'
import { NSlider, NInputNumber } from 'naive-ui'

interface Props {
  memoryMb: number
  cpuCores: number
  memoryMin?: number
  memoryMax?: number
  memoryStep?: number
  cpuMin?: number
  cpuMax?: number
  cpuStep?: number
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  memoryMin: 256,
  memoryMax: 4096,
  memoryStep: 128,
  cpuMin: 0.5,
  cpuMax: 4.0,
  cpuStep: 0.5,
  disabled: false,
})

const emit = defineEmits<{
  'update:memoryMb': [value: number]
  'update:cpuCores': [value: number]
}>()

const memoryModel = computed({
  get: () => props.memoryMb,
  set: (val) => emit('update:memoryMb', val),
})

const cpuModel = computed({
  get: () => props.cpuCores,
  set: (val) => emit('update:cpuCores', val),
})

function formatMarkNumber(value: number) {
  if (Number.isInteger(value)) return `${value}`
  return value.toFixed(1).replace(/\.0$/, '')
}

function normalizeMarkValue(value: number) {
  return Number(value.toFixed(3))
}

function buildSliderMarks(
  min: number,
  max: number,
  step: number,
  formatter: (value: number) => string,
) {
  const marks: Record<number, string> = {}
  const boundedMin = Math.min(min, max)
  const boundedMax = Math.max(min, max)
  const baseStep = Math.max(step, 0.001)

  marks[normalizeMarkValue(boundedMin)] = formatter(boundedMin)
  if (boundedMax === boundedMin) return marks

  const targetSegments = 6
  const rawStep = (boundedMax - boundedMin) / targetSegments
  const markStep = Math.max(baseStep, Math.ceil(rawStep / baseStep) * baseStep)

  for (let value = boundedMin + markStep; value < boundedMax; value += markStep) {
    const normalized = normalizeMarkValue(value)
    marks[normalized] = formatter(normalized)
  }

  marks[normalizeMarkValue(boundedMax)] = formatter(boundedMax)
  return marks
}

function formatMemoryMark(value: number) {
  if (value >= 1024) return `${formatMarkNumber(value / 1024)}G`
  return `${formatMarkNumber(value)}M`
}

const memoryMarks = computed(() =>
  buildSliderMarks(props.memoryMin, props.memoryMax, props.memoryStep, formatMemoryMark),
)

const cpuMarks = computed(() =>
  buildSliderMarks(props.cpuMin, props.cpuMax, props.cpuStep, (value) => `${formatMarkNumber(value)}核`),
)

function formatCpuLabel(value: number) {
  return `${value} 核`
}

function formatMemoryLabel(value: number) {
  return `${value} MB`
}
</script>

<template>
  <section class="resource-settings">
    <div class="resource-section">
      <div class="resource-label">
        <span>分配内存</span>
        <span class="current-value">{{ memoryMb }} MB</span>
      </div>
      <NSlider
        v-model:value="memoryModel"
        :min="memoryMin"
        :max="memoryMax"
        :step="memoryStep"
        :marks="memoryMarks"
        :disabled="disabled"
        :format-tooltip="formatMemoryLabel"
        class="resource-slider"
      />
      <NInputNumber
        v-model:value="memoryModel"
        :min="memoryMin"
        :max="memoryMax"
        :step="memoryStep"
        :disabled="disabled"
        size="small"
        class="resource-input"
      >
        <template #suffix>MB</template>
      </NInputNumber>
    </div>

    <div class="resource-section">
      <div class="resource-label">
        <span>分配 CPU</span>
        <span class="current-value">{{ cpuCores }} 核</span>
      </div>
      <NSlider
        v-model:value="cpuModel"
        :min="cpuMin"
        :max="cpuMax"
        :step="cpuStep"
        :marks="cpuMarks"
        :disabled="disabled"
        :format-tooltip="formatCpuLabel"
        class="resource-slider"
      />
      <NInputNumber
        v-model:value="cpuModel"
        :min="cpuMin"
        :max="cpuMax"
        :step="cpuStep"
        :disabled="disabled"
        size="small"
        class="resource-input"
      >
        <template #suffix>核</template>
      </NInputNumber>
    </div>
  </section>
</template>

<style scoped>
.resource-settings {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.resource-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.resource-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}

.current-value {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 6px;
  background: #e8eeff;
  color: #2e5bff;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.resource-input {
  width: 120px;
  align-self: flex-end;
}

.resource-slider {
  --n-rail-height: 6px;
  --n-fill-color: #2e5bff;
  --n-fill-color-hover: #2e5bff;
  --n-rail-color: #e5e7eb;
  --n-rail-color-hover: #e5e7eb;
  --n-handle-size: 18px;
  --n-handle-color: #fff;
  --n-handle-box-shadow: 0 0 0 2px #2e5bff, 0 2px 6px rgba(46, 91, 255, 0.25);
  --n-handle-box-shadow-hover: 0 0 0 2px #2e5bff, 0 4px 10px rgba(46, 91, 255, 0.3);
}

:deep(.n-slider-mark) {
  margin-top: 7px;
  color: #6b7280;
  font-size: 11px;
}

:deep(.n-slider-mark::before) {
  content: '';
  display: block;
  width: 1px;
  height: 5px;
  margin: 0 auto 4px;
  background: #d1d5db;
}
</style>
