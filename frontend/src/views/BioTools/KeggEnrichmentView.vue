<script setup lang="ts">
import { computed, h, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NUpload,
  useMessage,
  type UploadFileInfo,
} from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import * as Plotly from 'plotly.js-dist-min'
import { fetchSpeciesOptions, submitEnrichment } from '@/api/enrichment'
import type { EnrichmentResult, EnrichmentRow, SpeciesOption } from '@/types/enrichment'

const router = useRouter()
const message = useMessage()

const form = reactive({
  speciesId: '',
  keggCode: '',
  orgDb: '',
  idType: '',
  geneText: '',
  geneFile: null as File | null,
})

const inputMode = ref<'text' | 'file'>('text')
const speciesOptions = ref<SpeciesOption[]>([])
const speciesLoading = ref(false)
const submitting = ref(false)
const result = ref<EnrichmentResult | null>(null)
const fileList = ref<UploadFileInfo[]>([])

const speciesSelectOptions = computed(() =>
  speciesOptions.value.map((s) => ({ label: s.label, value: s.id })),
)

const columns = [
  { title: '通路 ID', key: 'id', width: 120, fixed: 'left' as const },
  { title: '通路描述', key: 'description', ellipsis: { tooltip: true }, minWidth: 220 },
  { title: 'GeneRatio', key: 'gene_ratio', width: 110 },
  { title: 'pvalue', key: 'pvalue', width: 110, render: (row: EnrichmentRow) => formatScientific(row.pvalue) },
  { title: 'p.adjust', key: 'p_adjust', width: 110, render: (row: EnrichmentRow) => formatScientific(row.p_adjust) },
  { title: 'Count', key: 'count', width: 90 },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row: EnrichmentRow) =>
      h('a', { href: `https://www.kegg.jp/pathway/${row.id}`, target: '_blank', rel: 'noopener noreferrer', class: 'kegg-link' }, 'KEGG'),
  },
]

function formatScientific(n: number) {
  if (n === 0) return '0'
  if (n < 0.001 || n >= 10000) return n.toExponential(2)
  return n.toFixed(n < 0.01 ? 4 : 3)
}

async function loadSpecies() {
  speciesLoading.value = true
  try {
    speciesOptions.value = await fetchSpeciesOptions()
  } catch (err) {
    message.error(err instanceof Error ? err.message : '加载物种配置失败')
  } finally {
    speciesLoading.value = false
  }
}

function handleSpeciesChange(speciesId: string) {
  const species = speciesOptions.value.find((s) => s.id === speciesId)
  if (species) {
    form.keggCode = species.kegg_code
    form.orgDb = species.org_db
    form.idType = species.id_type
  } else {
    form.keggCode = ''
    form.orgDb = ''
    form.idType = ''
  }
}

function handleFileChange({ fileList: list }: { fileList: UploadFileInfo[] }) {
  const latest = list[list.length - 1]
  form.geneFile = latest?.file ?? null
}

async function handleSubmit() {
  if (!form.speciesId) {
    message.warning('请选择物种')
    return
  }
  if (inputMode.value === 'text' && !form.geneText.trim()) {
    message.warning('请输入 Gene ID 列表')
    return
  }
  if (inputMode.value === 'file' && !form.geneFile) {
    message.warning('请上传基因 ID 文件')
    return
  }

  submitting.value = true
  result.value = null
  try {
    const payload = new FormData()
    payload.append('species_id', form.speciesId)
    payload.append('kegg_code', form.keggCode)
    payload.append('org_db', form.orgDb)
    payload.append('id_type', form.idType)
    if (inputMode.value === 'text') {
      payload.append('gene_text', form.geneText)
    } else if (form.geneFile) {
      payload.append('gene_file', form.geneFile)
    }

    result.value = await submitEnrichment(payload)
    await nextTick()
    renderPlot()
  } catch (err) {
    message.error(err instanceof Error ? err.message : '分析任务提交失败')
  } finally {
    submitting.value = false
  }
}

function renderPlot() {
  if (!result.value?.plotly_json) return
  const container = document.getElementById('kegg-enrichment-plot')
  if (!container) return
  const { data, layout } = result.value.plotly_json
  Plotly.newPlot(
    container,
    (data ?? []) as Plotly.Data[],
    (layout ?? {}) as Partial<Plotly.Layout>,
    { responsive: true },
  )
}

function exportCsv() {
  if (!result.value?.table_data.length) return
  const header = ['ID', 'Description', 'GeneRatio', 'pvalue', 'p.adjust', 'Count']
  const rows = result.value.table_data.map((r) =>
    [r.id, `"${r.description.replace(/"/g, '""')}"`, r.gene_ratio, r.pvalue, r.p_adjust, r.count].join(','),
  )
  const blob = new Blob(['\uFEFF' + [header.join(','), ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `kegg_enrichment_${result.value.task_id}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function handleReset() {
  form.speciesId = ''
  form.keggCode = ''
  form.orgDb = ''
  form.idType = ''
  form.geneText = ''
  form.geneFile = null
  fileList.value = []
  inputMode.value = 'text'
  result.value = null
}

onMounted(() => {
  loadSpecies()
})
</script>

<template>
  <div class="kegg-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon>
          <NIcon :size="18"><ArrowBackOutline /></NIcon>
        </template>
        返回工具箱
      </NButton>
      <h1 class="page-title">KEGG 通路富集分析</h1>
    </div>

    <div class="kegg-layout">
      <aside class="param-panel">
        <NForm label-placement="top" :show-feedback="false">
          <NFormItem label="物种（Species）">
            <NSelect
              v-model:value="form.speciesId"
              :options="speciesSelectOptions"
              placeholder="请选择物种"
              :loading="speciesLoading"
              @update:value="handleSpeciesChange"
            />
          </NFormItem>

          <NFormItem label="KEGG Code">
            <NInput v-model:value="form.keggCode" placeholder="如 hsa" disabled />
          </NFormItem>
          <NFormItem label="OrgDB">
            <NInput v-model:value="form.orgDb" placeholder="如 org.Hs.eg.db" disabled />
          </NFormItem>
          <NFormItem label="ID 类型">
            <NInput v-model:value="form.idType" placeholder="如 SYMBOL" disabled />
          </NFormItem>

          <NFormItem label="基因 ID 列表">
            <NTabs v-model:value="inputMode" type="line">
              <NTabPane name="text" tab="手动输入">
                <NInput
                  v-model:value="form.geneText"
                  type="textarea"
                  :rows="8"
                  placeholder="请输入 Gene ID，每行一个，例如：&#10;TP53&#10;BRCA1&#10;EGFR"
                />
              </NTabPane>
              <NTabPane name="file" tab="上传文件">
                <NUpload
                  v-model:file-list="fileList"
                  :default-upload="false"
                  :max="1"
                  accept=".txt,.csv,.tsv"
                  @change="handleFileChange"
                >
                  <NButton block>选择基因列表文件</NButton>
                </NUpload>
                <p class="upload-hint">支持 .txt / .csv / .tsv，每行一个 Gene ID</p>
              </NTabPane>
            </NTabs>
          </NFormItem>

          <NSpace>
            <NButton type="primary" :loading="submitting" @click="handleSubmit">提交分析</NButton>
            <NButton @click="handleReset">重置</NButton>
          </NSpace>
        </NForm>
      </aside>

      <main class="result-area">
        <NCard class="result-card" :bordered="true">
          <template #header>
            <div class="result-header">
              <span>分析结果</span>
              <NButton v-if="result" size="small" @click="exportCsv">导出 CSV</NButton>
            </div>
          </template>

          <NSpin v-if="submitting" class="result-placeholder" description="分析中，请稍候..." />

          <template v-else-if="!result">
            <NEmpty class="result-placeholder" description="提交分析后，将在此展示 Top 20 富集通路气泡图与完整结果表。" />
          </template>

          <template v-else>
            <div id="kegg-enrichment-plot" class="plot-container" />

            <div class="table-section">
              <div class="table-title">
                <span>富集结果明细</span>
                <NTag size="small" type="info">共 {{ result.table_data.length }} 条</NTag>
              </div>
              <NDataTable
                :columns="columns"
                :data="result.table_data"
                :pagination="{ pageSize: 10 }"
                :bordered="true"
                size="small"
                :scroll-x="800"
              />
            </div>
          </template>
        </NCard>
      </main>
    </div>
  </div>
</template>

<style scoped>
.kegg-page {
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
.kegg-layout {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 16px;
  align-items: start;
}
.param-panel {
  background: var(--neutral-card);
  border: 1px solid var(--neutral-border);
  border-radius: 12px;
  padding: 20px;
}
.upload-hint {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin: 8px 0 0;
}
.result-area {
  min-height: 640px;
}
.result-card {
  border-radius: 12px;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.result-placeholder {
  height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.plot-container {
  width: 100%;
  height: 460px;
  margin-bottom: 20px;
}
.table-section {
  margin-top: 16px;
}
.table-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-text-1);
}
.kegg-link {
  color: var(--arco-primary, #165dff);
  font-size: 13px;
}
.kegg-link:hover {
  text-decoration: underline;
}
@media (max-width: 900px) {
  .kegg-layout {
    grid-template-columns: 1fr;
  }
}
</style>
