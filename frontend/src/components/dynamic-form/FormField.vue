<script setup lang="ts">
import type { Parameter } from '@/types/schema'
import {
  NButton,
  NIcon,
  NInput,
  NInputNumber,
  NSelect,
  NSlider,
  NSwitch,
  NUpload,
} from 'naive-ui'
import { CloudUploadOutline } from '@vicons/ionicons5'
import { computed } from 'vue'

const props = defineProps<{
  parameter: Parameter
  modelValue: unknown
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const value = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const placeholder = computed(() => props.parameter.placeholder || '')

const isTextarea = computed(() => {
  return props.parameter.type === 'string' && props.parameter.string_config?.multiline
})

const numberConfig = computed(() => props.parameter.number_config)

const selectOptions = computed(() => {
  return (
    props.parameter.select_config?.options.map((opt) => ({
      label: opt.label,
      value: opt.value as string | number,
    })) || []
  )
})

function handleFileChange(options: { fileList: unknown[] }) {
  const config = props.parameter.file_config
  if (config?.multiple) {
    value.value = options.fileList
  } else {
    value.value = options.fileList[0] || null
  }
}
</script>

<template>
  <div class="form-field">
    <!-- 文本输入 -->
    <template v-if="parameter.type === 'string'">
      <NInput
        v-if="isTextarea"
        v-model:value="value as string"
        type="textarea"
        :rows="parameter.string_config?.rows || 3"
        :placeholder="placeholder"
      />
      <NInput v-else v-model:value="value as string" :placeholder="placeholder" />
    </template>

    <!-- 整数 -->
    <NInputNumber
      v-else-if="parameter.type === 'int'"
      v-model:value="value as number | null"
      :min="numberConfig?.min"
      :max="numberConfig?.max"
      :step="numberConfig?.step ?? 1"
      :placeholder="placeholder"
      clearable
    />

    <!-- 浮点数 / 滑块 -->
    <template v-else-if="parameter.type === 'float'">
      <NSlider
        v-if="numberConfig?.use_slider"
        v-model:value="value as number"
        :min="numberConfig?.min ?? 0"
        :max="numberConfig?.max ?? 100"
        :step="numberConfig?.step ?? 0.1"
      />
      <NInputNumber
        v-else
        v-model:value="value as number | null"
        :min="numberConfig?.min"
        :max="numberConfig?.max"
        :step="numberConfig?.step ?? 0.1"
        :precision="numberConfig?.precision ?? 2"
        :placeholder="placeholder"
        clearable
      />
    </template>

    <!-- 下拉选择 -->
    <NSelect
      v-else-if="parameter.type === 'select'"
      v-model:value="value as string | number | string[] | number[] | null"
      :options="selectOptions"
      :multiple="parameter.select_config?.multi"
      :clearable="parameter.select_config?.allow_clear"
      :filterable="parameter.select_config?.searchable"
      :placeholder="placeholder"
    />

    <!-- 布尔开关 -->
    <NSwitch v-else-if="parameter.type === 'boolean'" v-model:value="value as boolean" />

    <!-- 文件上传（简化占位，后续可对接真实上传 API） -->
    <NUpload
      v-else-if="parameter.type === 'file'"
      :multiple="parameter.file_config?.multiple"
      :accept="parameter.file_config?.accept"
      @change="handleFileChange"
    >
      <NButton>
        <template #icon>
          <NIcon><CloudUploadOutline /></NIcon>
        </template>
        上传文件
      </NButton>
    </NUpload>

    <!-- group / section 不在此组件渲染 -->
  </div>
</template>

<style scoped>
.form-field {
  width: 100%;
}
</style>
