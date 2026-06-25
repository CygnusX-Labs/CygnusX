<script setup lang="ts">
import type { FormValues, Parameter } from '@/types/schema'
import { useConditionEvaluator } from '@/composables/useConditionEvaluator'
import { NForm, NFormItem } from 'naive-ui'
import { computed } from 'vue'
import CollapsibleSection from './CollapsibleSection.vue'
import FormField from './FormField.vue'
import RepeatableGroup from './RepeatableGroup.vue'

const props = defineProps<{
  parameters: Parameter[]
  modelValue: FormValues
}>()

const emit = defineEmits<{
  'update:modelValue': [value: FormValues]
}>()

const { evaluate } = useConditionEvaluator()

const values = computed({
  get: () => props.modelValue || {},
  set: (v) => emit('update:modelValue', v),
})

const sortedParameters = computed(() => {
  return [...props.parameters].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
})

function isVisible(parameter: Parameter): boolean {
  return evaluate(parameter.condition, values.value)
}

function updateField(name: string, value: unknown) {
  values.value = { ...values.value, [name]: value }
}

function getFieldValue(parameter: Parameter): unknown {
  const current = values.value[parameter.name]
  if (current !== undefined) {
    return current
  }
  if (parameter.default !== undefined) {
    return parameter.default
  }
  if (parameter.type === 'boolean') {
    return false
  }
  if (parameter.type === 'group') {
    return []
  }
  if (parameter.type === 'section') {
    return {}
  }
  return undefined
}

function buildRules(parameter: Parameter) {
  const rules: { required?: boolean; message?: string; trigger?: string[] }[] = []
  if (parameter.required && isVisible(parameter)) {
    rules.push({
      required: true,
      message: `请填写 ${parameter.label}`,
      trigger: ['blur', 'change'],
    })
  }
  return rules
}
</script>

<template>
  <NForm :model="values" label-placement="left" label-width="auto">
    <template v-for="parameter in sortedParameters" :key="parameter.name">
      <NFormItem
        v-if="isVisible(parameter)"
        :label="parameter.label"
        :path="parameter.name"
        :rule="buildRules(parameter)"
      >
        <template v-if="parameter.help_text" #feedback>
          <span class="help-text">{{ parameter.help_text }}</span>
        </template>

        <!-- 可重复组 -->
        <RepeatableGroup
          v-if="parameter.type === 'group'"
          :parameter="parameter"
          :model-value="getFieldValue(parameter)"
          @update:model-value="(v) => updateField(parameter.name, v)"
        />

        <!-- 折叠区域 -->
        <CollapsibleSection
          v-else-if="parameter.type === 'section'"
          :parameter="parameter"
          :model-value="getFieldValue(parameter)"
          @update:model-value="(v) => updateField(parameter.name, v)"
        />

        <!-- 普通字段 -->
        <FormField
          v-else
          :parameter="parameter"
          :model-value="getFieldValue(parameter)"
          @update:model-value="(v) => updateField(parameter.name, v)"
        />
      </NFormItem>
    </template>
  </NForm>
</template>

<style scoped>
.help-text {
  color: var(--n-text-color-disabled);
  font-size: 12px;
}
</style>
