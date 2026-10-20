<template>
  <section class="memory-management" :aria-busy="loading">
    <div class="memory-management__toolbar">
      <div>
        <p class="memory-management__eyebrow">跨会话上下文</p>
        <h3>记忆管理 <span>· {{ overview?.mode === 'v2' ? 'v2 语义记忆' : '兼容模式' }}</span></h3>
        <p class="memory-management__hint">
          管理该 Agent 会在后续对话中参考的稳定偏好与项目事实。记忆只作为用户上下文，不会覆盖系统规则。
        </p>
      </div>
      <NSpace>
        <NButton secondary :loading="refreshing" @click="loadOverview(true)">
          <template #icon><NIcon :component="RefreshOutline" /></template>
          刷新
        </NButton>
        <NButton v-if="facts.length" secondary type="error" @click="clearFacts">
          清空事实
        </NButton>
      </NSpace>
    </div>

    <NAlert v-if="overview?.mode === 'legacy'" type="warning" :show-icon="false" class="memory-management__alert">
      当前平台仍处于旧记忆模式，本页会显示旧记忆；启用 v2 后将使用命名记忆块和语义事实库。
    </NAlert>

    <NSpin :show="loading">
      <div class="memory-metrics" aria-label="记忆概览">
        <div class="memory-metric">
          <span class="memory-metric__icon memory-metric__icon--primary"><NIcon :component="LayersOutline" /></span>
          <span><small>命名记忆块</small><strong>{{ blocks.length }}</strong></span>
          <em>稳定偏好</em>
        </div>
        <div class="memory-metric">
          <span class="memory-metric__icon memory-metric__icon--violet"><NIcon :component="SparklesOutline" /></span>
          <span><small>语义事实</small><strong>{{ facts.length }}</strong></span>
          <em>自动召回</em>
        </div>
        <div class="memory-metric">
          <span class="memory-metric__icon memory-metric__icon--orange"><NIcon :component="TimeOutline" /></span>
          <span><small>管理方式</small><strong>可控</strong></span>
          <em>可编辑 / 可归档</em>
        </div>
      </div>

      <section v-if="residualReport" class="memory-section memory-residuals" aria-label="遗忘残留提示">
        <header class="memory-section__header">
          <div><h4>已归档指定事实</h4><p>{{ residualStatusText }}</p></div>
          <NButton v-if="residualReport.scan_status !== 'disabled'" text :loading="scanning" @click="refreshResidualReport">重新检查</NButton>
        </header>
        <p class="memory-management__hint">仅检查当前范围内的词面匹配，可能漏掉换种说法的复述；不会自动改写画像或摘要。</p>
        <ul v-if="residualReport.residual_hints.length" class="memory-residual-list">
          <li v-for="hint in residualReport.residual_hints" :key="`${hint.kind}:${hint.id}`">
            <div><strong>{{ hint.kind === 'block' ? (blockLabels[hint.block_name || ''] || '记忆块') : hint.kind === 'episode' ? '会话进展' : '其他事实' }}</strong><p>{{ hint.excerpt }}</p></div>
            <NButton size="small" :disabled="hint.kind === 'block' && !editableResidualBlock(hint)" @click="handleResidual(hint)">
              {{ hint.kind === 'block' ? '编辑相关块' : '一并归档' }}
            </NButton>
          </li>
        </ul>
      </section>

      <section class="memory-section" aria-labelledby="memory-blocks-title">
        <header class="memory-section__header">
          <div><h4 id="memory-blocks-title">命名记忆块</h4><p>Agent 每轮优先参考的稳定上下文。</p></div>
          <NTag size="small" round>{{ blocks.length }} 个</NTag>
        </header>
        <div v-if="blocks.length">
          <div v-for="group in blockGroups" :key="group.key" class="memory-block-group">
            <h5>{{ group.label }}</h5>
            <p v-if="group.key !== 'personal' && group.key !== 'general' && !overview?.focus_per_project_enabled">项目焦点暂未启用，已保存内容保留为只读。</p>
            <div class="memory-block-grid">
          <article v-for="block in group.blocks" :key="block.id" class="memory-block-card">
            <div class="memory-block-card__header">
              <span class="memory-block-card__icon"><NIcon :component="blockIcons[block.block_name] || LayersOutline" /></span>
              <div><strong>{{ blockLabels[block.block_name] || block.block_name }}</strong><small>{{ block.status === 'archived' ? '历史归档 · ' : '' }}版本 v{{ block.version }}</small></div>
              <NButton text size="small" :disabled="!canEditBlock(block)" @click="openBlockEditor(block)">编辑</NButton>
            </div>
            <p v-if="block.content" class="memory-block-card__content">{{ block.content }}</p>
            <div v-else class="memory-block-card__empty"><NIcon :component="DocumentTextOutline" /><span>还没有内容</span></div>
            <div class="memory-block-card__meter"><span :style="{ width: `${Math.min(100, (block.content.length / block.char_limit) * 100)}%` }" /><small>{{ block.content.length }} / {{ block.char_limit }} 字符</small></div>
          </article>
            </div>
          </div>
        </div>
        <div v-else class="memory-empty-state memory-empty-state--compact">
          <span class="memory-empty-state__icon"><NIcon :component="LayersOutline" /></span>
          <div><strong>命名记忆块尚未初始化</strong><p>首次保存记忆或更新命名块后会自动初始化。</p></div>
        </div>
      </section>

      <section class="memory-section" aria-labelledby="memory-facts-title">
        <header class="memory-section__header">
          <div><h4 id="memory-facts-title">语义事实</h4><p>根据当前问题，并结合相似度与时间衰减参与召回。</p></div>
          <NSpace align="center"><NTag size="small" round>{{ facts.length }} 条</NTag><NButton v-if="facts.length" text type="error" size="small" @click="clearFacts">清空</NButton></NSpace>
        </header>
        <NDataTable v-if="facts.length" :columns="factColumns" :data="facts" :bordered="false" :row-key="(row: MemoryFact) => row.id" :pagination="{ pageSize: 8, showSizePicker: true, pageSizes: [8, 20, 50] }" :scroll-x="730" size="small" />
        <div v-else class="memory-empty-state">
          <span class="memory-empty-state__icon"><NIcon :component="SparklesOutline" /></span>
          <div><strong>还没有语义事实</strong><p>在对话中明确告诉助手需要长期记住的偏好或项目事实，它们会在符合条件时自动沉淀。</p></div>
        </div>
      </section>

      <section v-if="legacyMemories.length" class="memory-section" aria-labelledby="legacy-memory-title">
        <header class="memory-section__header"><div><h4 id="legacy-memory-title">兼容记忆</h4><p>迁移完成前保留的旧版记忆。</p></div><NTag size="small" round>{{ legacyMemories.length }} 条</NTag></header>
        <div class="legacy-memory-list">
          <div v-for="memory in legacyMemories" :key="memory.id" class="legacy-memory-row"><div><NTag size="tiny" round>{{ scopeLabels[memory.scope] || memory.scope }}</NTag><span>{{ memory.content }}</span></div><NButton text type="error" size="small" @click="deleteLegacyMemory(memory.id)">归档</NButton></div>
        </div>
      </section>
    </NSpin>

    <NModal v-model:show="editorVisible" preset="card" title="编辑命名记忆块" :style="{ width: 'min(640px, calc(100vw - 32px))' }">
      <NForm label-placement="top">
        <NFormItem :label="editingBlock ? blockLabels[editingBlock.block_name] || editingBlock.block_name : ''">
          <NInput
            v-model:value="editingContent"
            type="textarea"
            :maxlength="editingBlock?.char_limit"
            show-count
            :autosize="{ minRows: 8, maxRows: 16 }"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="editorVisible = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="saveBlock">保存记忆块</NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NSpin,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { DocumentTextOutline, LayersOutline, RefreshOutline, SparklesOutline, TimeOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import { forgetMemory, recordMemoryResidualAction, updateMemoryBlock } from '@/api/memory'
import type { MemoryBlock, MemoryForgetContext, MemoryForgetResponse, MemoryResidualHint } from '@/types/memory'
import { groupMemoryBlocks } from '@/utils/memoryBlocks'

const props = defineProps<{ agentId?: string }>()
const message = useMessage()
const dialog = useDialog()

interface MemoryFact {
  project_id?: string | null
  id: number
  agent_id: string
  scope: 'profile' | 'project' | 'preference' | 'summary' | 'episode'
  content: string
  keywords: string[]
  confidence: number
  status: string
  created_at: string | null
  last_recalled_at: string | null
}
interface LegacyMemory {
  id: string
  scope: string
  content: string
}
interface MemoryOverview {
  focus_per_project_enabled: boolean
  mode: 'legacy' | 'v2'
  agent_ids: string[]
  blocks: MemoryBlock[]
  facts: MemoryFact[]
  legacy_memories: LegacyMemory[]
}

const overview = ref<MemoryOverview | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const saving = ref(false)
const editorVisible = ref(false)
const editingBlock = ref<MemoryBlock | null>(null)
const editingContent = ref('')
const residualReport = ref<MemoryForgetResponse | null>(null)
const residualContext = ref<MemoryForgetContext>({})
const scanning = ref(false)
const residualStatusText = computed(() => {
  const report = residualReport.value
  if (!report) return ''
  if (report.scan_status === 'disabled') return '残留检查尚未启用，其他载体可能仍有相关表述。'
  if (report.scan_status === 'failed') return '归档已完成，残留检查失败，请重试。'
  if (report.scan_status === 'partial') return '当前仅显示部分可能残留的位置，仍可能有更多相关表述。'
  return report.residual_hints.length ? '以下位置可能仍有相关表述，请逐项确认是否清理。' : '当前范围内未发现词面命中；这不代表所有复述已清除。'
})
const blocks = computed(() => overview.value?.blocks || [])
const blockGroups = computed(() => groupMemoryBlocks(blocks.value))
const facts = computed(() => overview.value?.facts || [])
const legacyMemories = computed(() => overview.value?.legacy_memories || [])
const blockLabels: Record<string, string> = { profile: '用户画像', preferences: '长期偏好', current_focus: '当前焦点' }
const blockIcons: Record<string, any> = { profile: DocumentTextOutline, preferences: SparklesOutline, current_focus: TimeOutline }
const memoryStatusLabels: Record<string, string> = { active: '有效', superseded: '已替换', archived: '已归档' }
const scopeLabels: Record<string, string> = { profile: '用户画像', preference: '偏好', project: '项目', summary: '摘要', episode: '会话进展' }

function formatDate(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('zh-CN')
}

const factColumns: DataTableColumns<MemoryFact> = [
  { title: '范围', key: 'scope', width: 100, align: 'center', render: (row) => h(NTag, { size: 'small', round: true }, { default: () => scopeLabels[row.scope] || row.scope }) },
  { title: '事实内容', key: 'content', width: 330, ellipsis: { tooltip: true } },
  { title: '状态', key: 'status', width: 90, align: 'center', render: (row) => (memoryStatusLabels[row.status] || row.status) },
  { title: '置信度', key: 'confidence', width: 90, align: 'center', render: (row) => `${Math.round(row.confidence * 100)}%` },
  { title: '记录时间', key: 'created_at', width: 120, align: 'center', render: (row) => formatDate(row.created_at) },
  {
    title: '操作', key: 'actions', width: 90, align: 'center', fixed: 'right', render: (row) => h(NButton, {
      size: 'small', text: true, type: 'error', onClick: () => archiveFact(row.id),
    }, { default: () => '归档' }),
  },
]

async function loadOverview(refresh = false) {
  const agentAtStart = props.agentId
  if (refresh) refreshing.value = true
  else loading.value = true
  try {
    const params = props.agentId ? { agent_id: props.agentId } : undefined
    const { data } = await apiClient.get<MemoryOverview>('/users/me/memory-overview', { params })
    if (agentAtStart === props.agentId) overview.value = data
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '记忆加载失败')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function canEditBlock(block: MemoryBlock) {
  return block.status !== 'archived' && (!block.project_id || overview.value?.focus_per_project_enabled === true)
}

function openBlockEditor(block: MemoryBlock) {
  if (!canEditBlock(block)) return
  editingBlock.value = block
  editingContent.value = block.content
  editorVisible.value = true
}

async function saveBlock() {
  const block = editingBlock.value
  if (!block) return
  saving.value = true
  try {
    const data = await updateMemoryBlock(block, editingContent.value)
    if (overview.value) overview.value.blocks = overview.value.blocks.map((item) => item.id === data.id ? data : item)
    editorVisible.value = false
    message.success('记忆块已更新')
    await refreshResidualReport()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '记忆块更新失败，请刷新后重试')
  } finally {
    saving.value = false
  }
}

async function refreshResidualReport() {
  const source = residualReport.value
  if (!source || source.scan_status === 'disabled') return
  const agentAtStart = props.agentId
  scanning.value = true
  try {
    const result = await forgetMemory(Number(source.memory_id), residualContext.value)
    if (agentAtStart === props.agentId && residualReport.value?.memory_id === source.memory_id) residualReport.value = result
  } catch {
    message.error('残留检查未完成，请重试')
  } finally {
    scanning.value = false
  }
}

function editableResidualBlock(hint: MemoryResidualHint) {
  const block = blocks.value.find((item) => item.id === hint.id)
  return block && canEditBlock(block) ? block : undefined
}

function handleResidual(hint: MemoryResidualHint) {
  const source = residualReport.value
  if (!source) return
  if (hint.kind === 'block') {
    const block = editableResidualBlock(hint)
    if (!block) return
    void recordMemoryResidualAction(source.memory_id, hint).catch(() => undefined)
    openBlockEditor(block)
  } else {
    void recordMemoryResidualAction(source.memory_id, hint).catch(() => undefined)
    archiveFact(hint.id, { agent_id: hint.agent_id || props.agentId, project_id: hint.project_id || undefined }, true)
  }
}

function archiveFact(id: number, context?: MemoryForgetContext, residualCleanup = false) {
  const fact = facts.value.find((item) => item.id === id)
  const partition = context || { agent_id: props.agentId || fact?.agent_id || undefined, project_id: fact?.project_id || undefined }
  const agentAtStart = props.agentId
  dialog.warning({
    title: '归档这条事实？',
    content: '归档后该条不会再参与召回；画像、摘要或其他事实中可能仍有相关表述。',
    positiveText: '归档',
    negativeText: '取消',
    onPositiveClick: async () => {
      const result = await forgetMemory(id, partition)
      if (agentAtStart !== props.agentId) return
      if (!residualCleanup) {
        residualReport.value = result
        residualContext.value = partition
      }
      await loadOverview(true)
      if (residualCleanup) await refreshResidualReport()
      message.success('指定事实已归档，请查看残留检查结果')
    },
  })
}

function deleteLegacyMemory(id: string) {
  dialog.warning({
    title: '归档这条旧记忆？',
    content: '归档后它不会再参与旧版记忆召回。',
    positiveText: '归档',
    negativeText: '取消',
    onPositiveClick: async () => {
      await apiClient.delete(`/users/me/memories/${id}`)
      await loadOverview(true)
      message.success('记忆已归档')
    },
  })
}

function clearFacts() {
  dialog.warning({
    title: '清空当前 Agent 的事实？',
    content: '所有当前 Agent 的 active 事实都会归档，命名记忆块不会被删除。',
    positiveText: '确认清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      await apiClient.delete('/users/me/memories', { params: props.agentId ? { agent_id: props.agentId } : undefined })
      await loadOverview(true)
      message.success('事实已归档')
    },
  })
}

watch(() => props.agentId, () => {
  residualReport.value = null
  editorVisible.value = false
  void loadOverview()
})
onMounted(() => loadOverview())
</script>

<style scoped>
.memory-management { display: grid; gap: var(--space-lg); padding: var(--space-xl) var(--card-padding) var(--card-padding); }
.memory-management__toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-lg); }
.memory-management__eyebrow { margin: 0 0 4px; color: var(--arco-primary); font-size: 11px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.memory-management h3 { margin: 0; color: var(--neutral-text-1); font-size: 22px; letter-spacing: -.02em; }
.memory-management h3 span { color: var(--neutral-text-3); font-size: 13px; font-weight: 500; letter-spacing: 0; }
.memory-management__hint { max-width: 680px; margin: 6px 0 0; color: var(--neutral-text-2); font-size: 13px; line-height: 1.65; }
.memory-management__alert { margin: 0; }
.memory-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-md); }
.memory-metric { display: flex; align-items: center; gap: var(--space-md); min-width: 0; padding: var(--space-md) var(--space-lg); border: 1px solid var(--neutral-border); border-radius: var(--radius-card); background: var(--neutral-fill-2); }
.memory-metric > span:nth-child(2) { min-width: 0; display: grid; gap: 2px; }
.memory-metric small, .memory-metric em { color: var(--neutral-text-3); font-size: 12px; font-style: normal; }
.memory-metric strong { color: var(--neutral-text-1); font-size: 20px; line-height: 1.1; }
.memory-metric em { margin-left: auto; white-space: nowrap; }
.memory-metric__icon { width: 34px; height: 34px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 10px; font-size: 18px; }
.memory-metric__icon--primary { color: var(--arco-primary); background: var(--arco-primary-light); }
.memory-metric__icon--violet { color: #7c5cff; background: color-mix(in srgb, #7c5cff 10%, var(--neutral-card)); }
.memory-metric__icon--orange { color: #d88922; background: color-mix(in srgb, #d88922 12%, var(--neutral-card)); }
.memory-residuals > .memory-management__hint { padding: 0 var(--space-lg); }
.memory-residual-list { list-style: none; margin: 0; padding: var(--space-lg); }
.memory-residual-list li { display: flex; justify-content: space-between; gap: var(--space-md); padding: var(--space-md) 0; border-bottom: 1px solid var(--neutral-border); }
.memory-residual-list p { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--neutral-text-2); }
.memory-section { overflow: hidden; border: 1px solid var(--neutral-border); border-radius: var(--radius-card); background: var(--neutral-card); }
.memory-section__header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-lg); padding: var(--space-lg) var(--space-xl); border-bottom: 1px solid var(--neutral-border); }
.memory-section__header h4 { margin: 0; color: var(--neutral-text-1); font-size: 15px; font-weight: 650; }
.memory-section__header p { margin: 4px 0 0; color: var(--neutral-text-3); font-size: 12px; line-height: 1.5; }
.memory-block-group > h5 { margin: var(--space-lg) var(--space-lg) 0; font-size: 13px; overflow-wrap: anywhere; }
.memory-block-group > p { margin: var(--space-sm) var(--space-lg); color: var(--neutral-text-3); font-size: 12px; }
.memory-block-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-md); padding: var(--space-lg); }
.memory-block-card { min-width: 0; padding: var(--space-lg); border: 1px solid var(--neutral-border); border-radius: var(--radius-card); background: var(--neutral-fill-2); transition: border-color var(--motion-quick) ease-out, box-shadow var(--motion-quick) ease-out; }
.memory-block-card:hover { border-color: color-mix(in srgb, var(--arco-primary) 30%, var(--neutral-border)); box-shadow: var(--shadow-card); }
.memory-block-card__header { display: flex; align-items: center; gap: var(--space-sm); }
.memory-block-card__header > div { min-width: 0; flex: 1; display: grid; gap: 2px; }
.memory-block-card__header strong { color: var(--neutral-text-1); font-size: 14px; }
.memory-block-card__header small { color: var(--neutral-text-3); font-size: 11px; }
.memory-block-card__icon { width: 30px; height: 30px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 9px; color: var(--arco-primary); background: var(--arco-primary-light); }
.memory-block-card__content { min-height: 76px; margin: var(--space-lg) 0; color: var(--neutral-text-2); font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.memory-block-card__empty { min-height: 76px; display: flex; align-items: center; gap: 6px; margin: var(--space-lg) 0; color: var(--neutral-text-3); font-size: 13px; }
.memory-block-card__meter { display: flex; align-items: center; gap: var(--space-sm); }
.memory-block-card__meter > span { height: 4px; min-width: 4px; flex: 1; overflow: hidden; border-radius: 999px; background: var(--arco-primary); }
.memory-block-card__meter > span:after { content: ''; display: block; width: 100%; height: 100%; background: var(--neutral-border); transform: translateX(100%); }
.memory-block-card__meter small { color: var(--neutral-text-3); font-size: 11px; white-space: nowrap; }
.memory-empty-state { display: flex; align-items: center; justify-content: center; gap: var(--space-md); min-height: 190px; padding: var(--space-xl); color: var(--neutral-text-3); text-align: left; }
.memory-empty-state--compact { justify-content: flex-start; min-height: 110px; padding: var(--space-lg) var(--space-xl); }
.memory-empty-state__icon { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 12px; color: var(--neutral-text-3); background: var(--neutral-fill-2); font-size: 20px; }
.memory-empty-state strong { display: block; color: var(--neutral-text-2); font-size: 13px; }
.memory-empty-state p { max-width: 520px; margin: 4px 0 0; color: var(--neutral-text-3); font-size: 12px; line-height: 1.6; }
.legacy-memory-list { display: grid; }
.legacy-memory-row { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-md); padding: var(--space-md) 0; border-bottom: 1px solid var(--neutral-border); }
.legacy-memory-row:last-child { border-bottom: 0; }
.legacy-memory-row > div { display: flex; align-items: flex-start; gap: var(--space-sm); color: var(--neutral-text-2); line-height: 1.6; }
@media (max-width: 900px) {
  .memory-block-grid { grid-template-columns: 1fr; }
  .memory-management__toolbar { flex-direction: column; }
  .memory-metrics { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .memory-management { padding: var(--space-lg); }
  .memory-section__header { align-items: flex-start; flex-direction: column; }
  .memory-empty-state { align-items: flex-start; flex-direction: column; text-align: center; }
  .memory-empty-state > div { width: 100%; }
  .memory-empty-state__icon { margin: 0 auto; }
  .legacy-memory-row { align-items: flex-start; flex-direction: column; }
}

@media (prefers-reduced-motion: reduce) {
  .memory-block-card { transition: none; }
}
</style>
