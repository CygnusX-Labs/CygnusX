<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NIcon, NInput, NStatistic, NTag, useMessage,
} from 'naive-ui'
import {
  ArrowBackOutline, BarChartOutline, BrushOutline, CalculatorOutline,
  CopyOutline, DownloadOutline, RefreshOutline, SparklesOutline,
  SwapHorizontalOutline, TrashOutline,
} from '@vicons/ionicons5'
import {
  AA_COLORS, analyzeGC, cleanSequence, detectSeqType, dnaToRna, formatWithLineNumbers,
  genSampleSeq, parseFasta, reverseComplement, rnaToDna, sixFrameTranslate,
  type SeqStats, type SeqType, type SixFrameResult,
} from '@/utils/seqManipulatorProcessor'

const router = useRouter()
const message = useMessage()

type ResultMode = 'text' | 'sixframe' | 'gc'

const inputText = ref('')
const result = ref('')
const resultTitle = ref('运算结果')
const resultMode = ref<ResultMode>('text')
const sixFrames = ref<SixFrameResult[] | null>(null)
const gcStats = ref<SeqStats | null>(null)

const parsedSeq = computed(() => parseFasta(inputText.value))
const seqType = computed<SeqType>(() => detectSeqType(parsedSeq.value))
const seqLen = computed(() => parsedSeq.value.length)

const typeTag = computed(() => {
  const map: Record<SeqType, { text: string; type: 'error' | 'success' | 'warning' }> = {
    dna: { text: 'DNA', type: 'success' },
    rna: { text: 'RNA', type: 'warning' },
    protein: { text: 'Protein', type: 'error' },
  }
  return map[seqType.value]
})

function setTextResult(title: string, text: string) {
  resultTitle.value = title
  result.value = formatWithLineNumbers(text)
  resultMode.value = 'text'
  sixFrames.value = null
  gcStats.value = null
}

function runReverseComplement() {
  if (!requireSeq()) return
  setTextResult('反向互补序列', reverseComplement(parsedSeq.value))
  message.success(`搞定！共处理 ${seqLen.value} 个碱基`)
}

function runDnaToRna() {
  if (!requireSeq()) return
  setTextResult('DNA → RNA', dnaToRna(parsedSeq.value))
  message.success('已将所有 T 替换为 U')
}

function runRnaToDna() {
  if (!requireSeq()) return
  setTextResult('RNA → DNA', rnaToDna(parsedSeq.value))
  message.success('已将所有 U 替换为 T')
}

function runSixFrame() {
  if (!requireSeq()) return
  sixFrames.value = sixFrameTranslate(parsedSeq.value)
  resultTitle.value = '六框翻译结果'
  resultMode.value = 'sixframe'
  gcStats.value = null
  result.value = sixFrames.value.map((f) => `Frame ${f.label}:\n${f.protein}`).join('\n\n')
  message.success('已生成 6 个阅读框的氨基酸序列')
}

function runGC() {
  if (!requireSeq()) return
  gcStats.value = analyzeGC(parsedSeq.value)
  resultTitle.value = 'GC 含量分析'
  resultMode.value = 'gc'
  sixFrames.value = null
  result.value = formatWithLineNumbers(parsedSeq.value)
  message.success(`GC% = ${gcStats.value.gc}%`)
}

function runClean() {
  if (!inputText.value.trim()) {
    message.warning('序列为空')
    return
  }
  setTextResult('清理后序列', cleanSequence(inputText.value))
  message.success('已去除数字、空格与换行')
}

function requireSeq(): boolean {
  if (!seqLen.value) {
    message.warning('把你的序列丢进来，我才能帮你变魔术 🪄')
    return false
  }
  return true
}

function colorizeProtein(protein: string): string {
  return protein
    .split('')
    .map((aa) => `<span style="color:${AA_COLORS[aa] || '#fff'}">${aa}</span>`)
    .join('')
}

async function copyResult() {
  if (!result.value) {
    message.warning('暂无结果可复制')
    return
  }
  try {
    await navigator.clipboard.writeText(result.value)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动选择文本')
  }
}

function downloadResult(format: 'txt' | 'fasta') {
  if (!result.value) {
    message.warning('暂无结果可下载')
    return
  }
  let content = result.value
  if (format === 'fasta') {
    content = `>seq_manipulator_result\n${result.value.split('\n').map((l) => l.replace(/^\s+\d+\s*/, '')).join('')}`
  }
  const blob = new Blob([content], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `sequence_result.${format}`
  a.click()
  URL.revokeObjectURL(url)
}

function loadSample() {
  inputText.value = genSampleSeq()
  message.info('已载入水稻 ACTB 基因片段示例')
}

function clearAll() {
  inputText.value = ''
  result.value = ''
  sixFrames.value = null
  gcStats.value = null
  resultTitle.value = '运算结果'
  resultMode.value = 'text'
}
</script>

<template>
  <div class="seq-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回工具箱
      </NButton>
      <h1 class="page-title">🧬 序列魔术师</h1>
      <NButton size="small" quaternary @click="loadSample">
        <template #icon><NIcon><SparklesOutline /></NIcon></template>
        示例序列
      </NButton>
    </div>

    <p class="page-subtitle">纯本地运算，你的序列不会离开浏览器，隐私绝对安全 ✨</p>

    <div class="seq-layout">
      <!-- 左：输入与操作 -->
      <aside class="param-panel">
        <div class="panel-header">
          <span class="panel-title">输入序列</span>
          <NTag v-if="seqLen" size="small" :type="typeTag.type">{{ typeTag.text }} · {{ seqLen }} bp/aa</NTag>
        </div>
        <NInput
          v-model:value="inputText"
          type="textarea"
          :autosize="{ minRows: 12, maxRows: 22 }"
          placeholder="粘贴你的序列 here... 支持 FASTA 格式（自动去除 > 标题行）"
          class="seq-input"
        />

        <div class="op-section">
          <span class="panel-title">选择操作</span>
          <div class="op-grid">
            <NButton size="small" type="primary" :disabled="!seqLen" @click="runReverseComplement">
              <template #icon><NIcon><RefreshOutline /></NIcon></template>反向互补
            </NButton>
            <NButton size="small" secondary :disabled="!seqLen" @click="runDnaToRna">
              <template #icon><NIcon><SwapHorizontalOutline /></NIcon></template>DNA → RNA
            </NButton>
            <NButton size="small" secondary :disabled="!seqLen" @click="runRnaToDna">
              <template #icon><NIcon><SwapHorizontalOutline /></NIcon></template>RNA → DNA
            </NButton>
            <NButton size="small" secondary :disabled="!seqLen" @click="runSixFrame">
              <template #icon><NIcon><CalculatorOutline /></NIcon></template>六框翻译
            </NButton>
            <NButton size="small" secondary :disabled="!seqLen" @click="runGC">
              <template #icon><NIcon><BarChartOutline /></NIcon></template>GC 分析
            </NButton>
            <NButton size="small" secondary @click="runClean">
              <template #icon><NIcon><BrushOutline /></NIcon></template>序列清理
            </NButton>
          </div>
        </div>

        <NButton size="small" quaternary block class="clear-btn" @click="clearAll">
          <template #icon><NIcon><TrashOutline /></NIcon></template>清除全部
        </NButton>
      </aside>

      <!-- 右：结果 -->
      <main class="work-area">
        <div class="result-card">
          <div class="result-header">
            <span class="panel-title">{{ resultTitle }}</span>
            <div class="result-actions">
              <NButton size="tiny" tertiary @click="copyResult">
                <template #icon><NIcon><CopyOutline /></NIcon></template>复制
              </NButton>
              <NButton size="tiny" tertiary @click="downloadResult('txt')">TXT</NButton>
              <NButton size="tiny" tertiary @click="downloadResult('fasta')">
                <template #icon><NIcon><DownloadOutline /></NIcon></template>FASTA
              </NButton>
            </div>
          </div>

          <!-- 文本结果 -->
          <pre v-if="resultMode === 'text' && result" class="seq-output">{{ result }}</pre>

          <!-- GC 统计 -->
          <template v-else-if="resultMode === 'gc' && gcStats">
            <div class="stat-grid">
              <div class="stat-item stat-gc"><NStatistic label="GC 含量" :value="gcStats.gc" suffix="%" /></div>
              <div class="stat-item stat-at"><NStatistic label="AT 含量" :value="gcStats.at" suffix="%" /></div>
              <div class="stat-item"><NStatistic label="序列长度" :value="gcStats.length" /></div>
              <div class="stat-item"><NStatistic label="分子量" :value="gcStats.mw" suffix="kDa" /></div>
              <div class="stat-item"><NStatistic label="最长连续片段" :value="gcStats.n50" /></div>
            </div>
            <pre v-if="result" class="seq-output compact">{{ result }}</pre>
          </template>

          <!-- 六框翻译 -->
          <template v-else-if="resultMode === 'sixframe' && sixFrames">
            <div class="frame-list">
              <div v-for="f in sixFrames" :key="f.frame" class="frame-item">
                <NTag size="tiny" :type="f.frame > 0 ? 'success' : 'warning'" class="frame-tag">{{ f.label }}</NTag>
                <pre class="protein-output" v-html="colorizeProtein(f.protein)"></pre>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <div v-else class="empty-state">
            <p>把你的序列丢进来，我帮你变魔术 🪄</p>
            <p class="empty-hint">支持 DNA / RNA / Protein 自动识别，FASTA 格式自动解析</p>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.seq-page {
  padding: 16px;
  min-height: 100%;
}
.page-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0;
  flex: 1;
}
.page-subtitle {
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
  margin: 0 0 12px;
}
.seq-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}
.param-panel,
.result-card {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 12px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
}
.seq-input :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}
.op-section {
  margin-top: 14px;
}
.op-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 8px;
}
.op-grid :deep(.n-button__content) {
  font-size: 12px;
}
.clear-btn {
  margin-top: 12px;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.result-actions {
  display: flex;
  gap: 6px;
}
.seq-output {
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--neutral-text-1, #1d2129);
  background: var(--neutral-bg, #f7f8fa);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 8px;
  padding: 10px;
  margin: 0;
  max-height: calc(100vh - 280px);
  overflow: auto;
  white-space: pre;
}
.seq-output.compact {
  max-height: 240px;
  margin-top: 12px;
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}
.stat-item {
  text-align: center;
  padding: 10px 6px;
  border-radius: 8px;
  background: var(--neutral-bg, #f7f8fa);
}
.stat-gc :deep(.n-statistic-value__content) { color: #00b42a; }
.stat-at :deep(.n-statistic-value__content) { color: #165dff; }
.frame-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 280px);
  overflow: auto;
}
.frame-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  background: var(--neutral-bg, #f7f8fa);
  border-radius: 6px;
}
.frame-tag {
  flex-shrink: 0;
  margin-top: 1px;
}
.protein-output {
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.4;
  margin: 0;
  word-break: break-all;
  white-space: pre-wrap;
}
.empty-state {
  padding: 48px 16px;
  text-align: center;
  color: var(--neutral-text-3, #86909c);
}
.empty-state p { margin: 4px 0; font-size: 14px; }
.empty-hint { font-size: 12px !important; color: var(--neutral-text-3, #c9cdd4); }
@media (max-width: 1200px) {
  .seq-layout { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .seq-page { padding: 12px; }
  .op-grid { grid-template-columns: 1fr; }
}
</style>
