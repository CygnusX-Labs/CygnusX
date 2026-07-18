<script setup lang="ts">
import type { FlowConfig, FormValues, Parameter } from '@/types/schema'
import type { Task } from '@/types'
import type { CostEstimate } from '@/types'
import { apiClient } from '@/api'
import DynamicForm from '@/components/dynamic-form/DynamicForm.vue'
import FilePickerModal from '@/components/FilePickerModal.vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  NAlert,
  NButton,
  NCard,
  NDivider,
  NIcon,
  NInput,
  NSpin,
  NSpace,
  NTable,
  NTag,
} from 'naive-ui'
import { FolderOpenOutline, LogoGithub } from '@vicons/ionicons5'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCookieStore } from '@/stores/cookie'
import type { FilePickerItem } from '@/types'

const route = useRoute()
const router = useRouter()
const cookieStore = useCookieStore()
const flowId = computed(() => route.params.flowId as string)

const flow = ref<FlowConfig | null>(null)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const taskName = ref('')

// 文件选择器状态：当前正在编辑的单元格 { rowIndex, colName }
const pickerVisible = ref(false)
const pickerFileType = ref<string | undefined>(undefined)
const pickerTarget = ref<{ rowIndex: number; colName: string } | null>(null)

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
    const comparisons = buildComparisons() || []
    costEstimate.value = await cookieStore.estimateCost(
      flowId.value,
      sampleSheet.value.length,
      comparisons.length,
    )
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

// flow 加载后 + 参数/样本表变更时防抖预估
watch(flowId, fetchEstimate, { immediate: false })
watch(() => formValues.value, debouncedEstimate, { deep: true })
watch(() => sampleSheet.value, debouncedEstimate, { deep: true })

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

/** 判断列是否为文件路径列（fastq/bam/vc/file 等） */
function isFileColumn(colName: string): boolean {
  const n = (colName || '').toLowerCase()
  return ['fastq', 'fastq_1', 'fastq_2', 'fq', 'bam', 'vcf', 'file', 'filepath', 'r1', 'r2'].some(
    (k) => n.includes(k),
  )
}

/** 打开文件选择器，记录当前编辑的单元格 */
function openPicker(rowIndex: number, colName: string) {
  // 根据列名推断文件类型过滤
  const n = colName.toLowerCase()
  let ft: string | undefined
  if (n.includes('fastq') || n.includes('fq') || n.includes('r1') || n.includes('r2')) ft = 'fastq'
  else if (n.includes('bam')) ft = 'bam'
  else if (n.includes('vcf')) ft = 'vcf'
  pickerFileType.value = ft
  pickerTarget.value = { rowIndex, colName }
  pickerVisible.value = true
}

/** 选择器确认：回填绝对路径到样本表单元格 */
function handlePickerSelect(items: FilePickerItem[]) {
  if (!pickerTarget.value) return
  const { rowIndex, colName } = pickerTarget.value
  if (items.length > 0) {
    sampleSheet.value[rowIndex][colName] = items[0].abs_path
  }
  pickerTarget.value = null
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
      error.value = `饼干余额不足: 需要 ${costEstimate.value.estimated_cost} 🥫, 当前可用 ${costEstimate.value.current_balance} 🥫`
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
    <PageHeader :title="flow?.meta.name || '提交任务'" subtitle="配置分析参数与样本表后提交运行任务">
      <template v-if="flow?.meta.docs_url" #actions>
        <a
          :href="flow.meta.docs_url"
          target="_blank"
          rel="noopener noreferrer"
          class="github-link focus-ring"
        >
          <NIcon :size="18"><LogoGithub /></NIcon>
          查看源码
        </a>
      </template>
    </PageHeader>
    <NAlert v-if="error" type="error" :title="error" role="alert" />

    <NSpin :show="loading" :aria-busy="loading">
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
                <div class="file-col-cell">
                  <NInput v-model:value="row[col.name]" :placeholder="isFileColumn(col.name) ? '可手填或点右侧选择' : ''" />
                  <NButton
                    v-if="isFileColumn(col.name)"
                    size="small"
                    quaternary
                    title="从数据管理选择文件"
                    @click="openPicker(index, col.name)"
                  >
                    <template #icon><NIcon><FolderOpenOutline /></NIcon></template>
                  </NButton>
                </div>
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
              <span class="cost-label">预估费用: </span>
              <span style="font-weight: bold; font-size: 18px">{{ Number(costEstimate.estimated_cost).toFixed(2) }} 🥫</span>
            </div>
            <div>
              <span class="cost-label">当前余额: </span>
              <span :class="['cost-value', { 'cost-value--unaffordable': !costEstimate.affordable }]">
                {{ Number(costEstimate.current_balance).toFixed(1) }} 🥫
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

    <!-- 文件选择器：样本表文件列从用户已上传数据选 -->
    <FilePickerModal
      v-model:show="pickerVisible"
      :file-type="pickerFileType"
      @select="handlePickerSelect"
    />
  </div>
</template>

<style scoped>
.flow-submit-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.github-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 8px;
  background: var(--neutral-hover);
  color: var(--neutral-text-2);
  font-size: 13px;
  text-decoration: none;
  transition: all 0.2s;
}
.github-link:hover {
  color: var(--neutral-text-1);
  background: var(--neutral-border);
}
.sample-card {
  margin-top: 16px;
}
.add-row-btn {
  margin-top: 12px;
}
.file-col-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 240px;
}
.file-col-cell :deep(.n-input) {
  flex: 1;
}
.cost-label {
  color: var(--neutral-text-2);
}
.cost-value {
  color: var(--arco-success);
  font-size: 18px;
  font-weight: 700;
}
.cost-value--unaffordable {
  color: var(--arco-danger);
}
@media (max-width: 768px) {
  .flow-submit-view {
    padding: 16px;
  }
  .file-col-cell {
    min-width: 200px;
  }
}
</style>
