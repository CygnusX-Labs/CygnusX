<script setup lang="ts">
import { computed } from 'vue'
import { NCard, NSlider, NInputNumber, NSpace } from 'naive-ui'

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

const memoryMarks = computed(() => {
  const marks: Record<number, string> = {}
  for (let v = props.memoryMin; v <= props.memoryMax; v += 512) {
    marks[v] = `${v}M`
  }
  return marks
})

const cpuMarks = computed(() => {
  const marks: Record<number, string> = {}
  for (let v = props.cpuMin; v <= props.cpuMax; v += 0.5) {
    marks[Math.round(v * 10) / 10] = `${v}核`
  }
  return marks
})

function formatCpuLabel(value: number) {
  return `${value} 核`
}

function formatMemoryLabel(value: number) {
  return `${value} MB`
}
</script>

<template>
  <NCard title="资源设置" size="small" class="resource-settings">
    <div class="resource-row">
      <div class="resource-label">
        <span>内存</span>
        <NInputNumber
          v-model:value="memoryModel"
          :min="memoryMin"
          :max="memoryMax"
          :step="memoryStep"
          :disabled="disabled"
          size="small"
          style="width: 100px"
        >
          <template #suffix>MB</template>
        </NInputNumber>
      </div>
      <NSlider
        v-model:value="memoryModel"
        :min="memoryMin"
        :max="memoryMax"
        :step="memoryStep"
        :marks="memoryMarks"
        :disabled="disabled"
        :format-tooltip="formatMemoryLabel"
      />
    </div>

    <div class="resource-row">
      <div class="resource-label">
        <span>CPU</span>
        <NInputNumber
          v-model:value="cpuModel"
          :min="cpuMin"
          :max="cpuMax"
          :step="cpuStep"
          :disabled="disabled"
          size="small"
          style="width: 100px"
        >
          <template #suffix>核</template>
        </NInputNumber>
      </div>
      <NSlider
        v-model:value="cpuModel"
        :min="cpuMin"
        :max="cpuMax"
        :step="cpuStep"
        :marks="cpuMarks"
        :disabled="disabled"
        :format-tooltip="formatCpuLabel"
      />
    </div>
  </NCard>
</template>

<style scoped>
.resource-settings {
  margin-top: 16px;
}

.resource-row {
  margin-bottom: 20px;
}

.resource-row:last-child {
  margin-bottom: 0;
}

.resource-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 14px;
  color: var(--n-text-color-base);
  font-weight: 500;
}

:deep(.n-slider-mark) {
  font-size: 11px;
}
</style>
