<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NIcon, NInput, NInputNumber, NSelect, NDataTable, NUpload, NSpace, NTag,
} from 'naive-ui'
import type { DataTableColumns, UploadFileInfo } from 'naive-ui'
import { ArrowBackOutline, SearchOutline } from '@vicons/ionicons5'

const router = useRouter()

const fastaInput = ref('')
const selectedDb = ref('rice-pan')
const evalueThreshold = ref(1e-5)
const isSearching = ref(false)
const showResults = ref(true)

const dbOptions = [
  { label: '水稻泛基因组 ( Rice Pan-Genome )', value: 'rice-pan' },
  { label: '生菜转录本 ( Lettuce Transcriptome )', value: 'lettuce-tr' },
  { label: '拟南芥蛋白库 ( Arabidopsis Proteins )', value: 'arabidopsis' },
  { label: 'NCBI nt 核酸库', value: 'ncbi-nt' },
]

function handleFileUpload({ file }: { file: UploadFileInfo }) {
  if (file.file) {
    const reader = new FileReader()
    reader.onload = () => {
      fastaInput.value = (reader.result as string).slice(0, 5000)
    }
    reader.readAsText(file.file)
  }
  return false
}

interface BlastHit {
  query: string
  subject: string
  identity: number
  evalue: string
  bitScore: number
  alignLen: number
  qStart: number
  qEnd: number
  sStart: number
  sEnd: number
}

const mockResults = ref<BlastHit[]>([
  { query: 'OsNAC14', subject: 'Chr3:28,451,200-28,453,800', identity: 98.7, evalue: '2.1e-142', bitScore: 487, alignLen: 260, qStart: 1, qEnd: 260, sStart: 28451200, sEnd: 28453800 },
  { query: 'OsNAC14', subject: 'Chr7:12,088,400-12,090,100', identity: 85.3, evalue: '3.4e-89', bitScore: 312, alignLen: 248, qStart: 8, qEnd: 255, sStart: 12088400, sEnd: 12090100 },
  { query: 'OsNAC14', subject: 'Chr1:5,672,300-5,674,000', identity: 72.1, evalue: '1.8e-54', bitScore: 198, alignLen: 230, qStart: 22, qEnd: 251, sStart: 5672300, sEnd: 5674000 },
  { query: 'OsNAC14', subject: 'Chr11:33,210,500-33,212,200', identity: 64.5, evalue: '5.6e-38', bitScore: 145, alignLen: 210, qStart: 40, qEnd: 249, sStart: 33210500, sEnd: 33212200 },
  { query: 'OsNAC14', subject: 'Chr5:18,940,100-18,941,800', identity: 58.2, evalue: '2.3e-22', bitScore: 98, alignLen: 195, qStart: 55, qEnd: 249, sStart: 18940100, sEnd: 18941800 },
])

const columns: DataTableColumns<BlastHit> = [
  { title: 'Query', key: 'query', width: 100 },
  { title: 'Subject', key: 'subject', ellipsis: { tooltip: true } },
  {
    title: 'Identity %',
    key: 'identity',
    width: 100,
    render: (row) => {
      const color = row.identity >= 90 ? '#00B42A' : row.identity >= 70 ? '#FF7D00' : '#86909c'
      return `${row.identity}%`
    },
  },
  { title: 'E-value', key: 'evalue', width: 110 },
  { title: 'Bit Score', key: 'bitScore', width: 90 },
  { title: '比对长度', key: 'alignLen', width: 90 },
  {
    title: 'Query 范围',
    key: 'qRange',
    width: 110,
    render: (row) => `${row.qStart}-${row.qEnd}`,
  },
]

function handleSearch() {
  isSearching.value = true
  setTimeout(() => {
    isSearching.value = false
    showResults.value = true
  }, 1200)
}

const mockAlignment = `Query  1   ATGGCTGACGCCGACGACGACGACGGCGGCGGCGGCGGCGGCGGCGGC  50
           ||||||||||||||||||||| |||||| |||||||||||| |||| |||
Sbjct  1   ATGGCTGACGCCGACGACGAC AGCGGCGGCGGCGGCGGCAGGCGGCG  48

Query  51  AGCAGCAGCAGCAGCAGCAGCGACGACGACGACGACGGCGGCGGCGGC  100
           |||||||| ||||||||||||| |||||||||||| |||| |||||||||
Sbjct  49  AGCAGCAG AGCAGCAGCAGCGACGACGACGACGA GGCAGGCGGCGGC  96`
</script>

<template>
  <div class="blast-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回工具箱
      </NButton>
      <h1 class="page-title">序列检索 BLAST</h1>
    </div>

    <div class="blast-layout">
      <div class="input-section">
        <div class="input-card">
          <h3 class="section-title">查询序列 (FASTA)</h3>
          <NInput
            v-model:value="fastaInput"
            type="textarea"
            :rows="8"
            placeholder=">OsNAC14&#10;ATGGCTGACGCCGACGACGACGACGGCGGCGGCGGCGGCGGC..."
            class="fasta-textarea"
          />
          <div class="upload-row">
            <NUpload accept=".fasta,.fa,.fna,.txt" :max="1" :default-upload="false" @change="handleFileUpload">
              <NButton size="small">上传 FASTA 文件</NButton>
            </NUpload>
          </div>
        </div>

        <div class="input-card">
          <h3 class="section-title">目标数据库</h3>
          <NSelect v-model:value="selectedDb" :options="dbOptions" />
        </div>

        <div class="input-card params-row">
          <div>
            <h3 class="section-title">E-value 阈值</h3>
            <NInputNumber v-model:value="evalueThreshold" :min="1e-100" :max="10" :show-button="false" placeholder="1e-5" style="width: 160px" />
          </div>
        </div>

        <NButton type="primary" block size="large" :loading="isSearching" @click="handleSearch">
          <template #icon><NIcon :size="18"><SearchOutline /></NIcon></template>
          开始检索
        </NButton>
      </div>

      <div class="results-section" v-if="showResults">
        <div class="results-header">
          <h3 class="section-title">比对结果</h3>
          <NTag size="small" type="success" round>{{ mockResults.length }} 条命中</NTag>
        </div>

        <NDataTable
          :columns="columns"
          :data="mockResults"
          :bordered="false"
          size="small"
          :single-line="false"
          class="results-table"
        />

        <div class="alignment-card">
          <h3 class="section-title">序列比对详情 (Top Hit)</h3>
          <pre class="alignment-view">{{ mockAlignment }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.blast-page {
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
  color: var(--neutral-text-1, #1d2129);
  margin: 0;
}
.blast-layout {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 16px;
  align-items: start;
}
.input-card {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0 0 10px;
}
.fasta-textarea :deep(textarea) {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 12px;
}
.upload-row {
  margin-top: 8px;
}
.params-row {
  display: flex;
  gap: 16px;
}
.results-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.results-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.results-header .section-title {
  margin: 0;
}
.results-table {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  overflow: hidden;
}
.results-table :deep(th) {
  font-size: 12px;
  font-weight: 500;
  background: var(--neutral-bg, #f2f3f8);
}
.alignment-card {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 16px;
}
.alignment-view {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--neutral-text-1, #1d2129);
  background: var(--neutral-bg, #f2f3f8);
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0;
  white-space: pre;
}
@media (max-width: 900px) {
  .blast-layout {
    grid-template-columns: 1fr;
  }
}
</style>
