<script setup lang="ts">
import type { FlowConfig, FormValues, Parameter } from '@/types/schema'
import type { Task } from '@/types'
import type { CostEstimate } from '@/types'
import { apiClient } from '@/api'
import DynamicForm from '@/components/dynamic-form/DynamicForm.vue'
import {
  NAlert,
  NButton,
  NCard,
  NDivider,
  NInput,
  NSpin,
  NSpace,
  NTable,
  NTag,
} from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCookieStore } from '@/stores/cookie'

const route = useRoute()
const router = useRouter()
const cookieStore = useCookieStore()
const flowId = computed(() => route.params.flowId as string)

const flow = ref<FlowConfig | null>(null)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const taskName = ref('')

const parameters = computed(() => flow.value?.parameters || [])
const sampleSheetConfig = computed(() => flow.value?.sample_sheet)

const formValues = ref<FormValues>({})
const sampleSheet = ref<Record<string, string>[]>([
  { sample: '', sample_name: '', group: '' },
])

// 饼干预估
const costEstimate = ref<CostEstimate | null>(null)
const estimating = ref(false)
let estimateTimer: ReturnType<typeof setTimeout> | null = null

async function fetchEstimate() {
  if (!flowId.value) return
  estimating.value = true
  try {
    costEstimate.value = await cookieStore.estimateCost(flowId.value)
  } catch {
    costEstimate.value = null
  } finally {
    estimating.value = false
  }
}

function debouncedEstimate() {
  if (estimateTimer) clearTimeout(estimateTimer)
  estimateTimer = setTimeout(fetchEstimate, 500)
}

// flow 加载后 + 参数变更时防抖预估
watch(flowId, fetchEstimate, { immediate: false })
watch(() => formValues.value, debouncedEstimate, { deep: true })

async function fetchFlow() {
  loading.value = true
  try {
    const res = await apiClient.get<FlowConfig>(`/flows/${flowId.value}`)
    flow.value = res.data
    // 初始化默认值
    const defaults: FormValues = {}
    for (const p of res.data.parameters) {
      if (p.default !== undefined) {
        defaults[p.name] = p.default
      }
    }
    formValues.value = defaults
  } catch (e: any) {
    error.value = e.response?.data?.detail || '获取流程详情失败'
  } finally {
    loading.value = false
  }
}

function addSampleRow() {
  const empty: Record<string, string> = {}
  for (const col of sampleSheetConfig.value?.columns || []) {
    empty[col.name] = ''
  }
  sampleSheet.value.push(empty)
}

function removeSampleRow(index: number) {
  if (sampleSheet.value.length > 1) {
    sampleSheet.value.splice(index, 1)
  }
}

function buildComparisons(): Record<string, string>[] | undefined {
  const comparisons = formValues.value.comparisons
  if (Array.isArray(comparisons) && comparisons.length > 0) {
    return comparisons.map((c: Record<string, unknown>) => ({
      Control: String(c.Control || ''),
      Treat: String(c.Treat || ''),
    }))
  }
  return undefined
}

async function submitTask() {
  submitting.value = true
  error.value = ''
  try {
    // 饼干预估：余额不足时拦截
    if (cookieStore.isLoggedIn && costEstimate.value && !costEstimate.value.affordable) {
      error.value = `饼干余额不足: 需要 ${costEstimate.value.estimated_cost} 🍪, 当前可用 ${costEstimate.value.current_balance} 🍪`
      return
    }
    const comparisons = buildComparisons()
    const payload: Record<string, unknown> = {
      flow_id: flowId.value,
      name: taskName.value || undefined,
      parameters: formValues.value,
      sample_sheet: sampleSheet.value,
      execution_mode: 'local',
    }
    if (comparisons) {
      payload.comparisons = comparisons
    }
    const res = await apiClient.post<Task>('/tasks', payload)
    router.push({ name: 'task-detail', params: { taskId: res.data.id } })
  } catch (e: any) {
    error.value = e.response?.data?.detail || '提交任务失败'
  } finally {
    submitting.value = false
  }
}

onMounted(fetchFlow)
</script>

<template>
  <div class="flow-submit-view">
    <h2>{{ flow?.meta.name || '提交任务' }}</h2>
    <NAlert v-if="error" type="error" :title="error" />

    <NSpin :show="loading">
      <NCard v-if="flow" title="任务参数">
        <NSpace vertical>
          <NInput v-model:value="taskName" placeholder="任务名称（可选）" />
          <DynamicForm v-model="formValues" :parameters="parameters" />
        </NSpace>
      </NCard>

      <NCard v-if="sampleSheetConfig" title="样本表" class="sample-card">
        <NTable>
          <thead>
            <tr>
              <th v-for="col in sampleSheetConfig.columns" :key="col.name">
                {{ col.name }}
                <NTag v-if="col.required" type="error" size="small">必填</NTag>
              </th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in sampleSheet" :key="index">
              <td v-for="col in sampleSheetConfig.columns" :key="col.name">
                <NInput v-model:value="row[col.name]" />
              </td>
              <td>
                <NButton text type="error" @click="removeSampleRow(index)">删除</NButton>
              </td>
            </tr>
          </tbody>
        </NTable>
        <NButton class="add-row-btn" dashed @click="addSampleRow">+ 添加样本</NButton>
      </NCard>

      <NDivider />

      <NCard v-if="cookieStore.isLoggedIn && costEstimate" size="small" :bordered="true">
        <NSpace align="center" justify="space-between">
          <NSpace align="center" :size="24">
            <div>
              <span style="color: #666">预估费用: </span>
              <span style="font-weight: bold; font-size: 18px">{{ Number(costEstimate.estimated_cost).toFixed(2) }} 🍪</span>
            </div>
            <div>
              <span style="color: #666">当前余额: </span>
              <span :style="{ fontWeight: 'bold', color: costEstimate.affordable ? '#18a058' : '#d03050' }">
                {{ Number(costEstimate.current_balance).toFixed(1) }} 🍪
              </span>
            </div>
          </NSpace>
          <NTag :type="costEstimate.affordable ? 'success' : 'error'" size="small">
            {{ costEstimate.affordable ? '余额充足' : '余额不足' }}
          </NTag>
        </NSpace>
      </NCard>

      <NButton type="primary" size="large" :loading="submitting" :disabled="!!costEstimate && !costEstimate.affordable" @click="submitTask">
        提交任务
      </NButton>
    </NSpin>
  </div>
</template>

<style scoped>
.flow-submit-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sample-card {
  margin-top: 16px;
}
.add-row-btn {
  margin-top: 12px;
}
</style>
