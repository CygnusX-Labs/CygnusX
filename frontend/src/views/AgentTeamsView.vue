<script setup lang="ts">
import { h, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NPagination,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  ChatbubbleEllipsesOutline,
  GitNetworkOutline,
  RefreshOutline,
  SendOutline,
} from '@vicons/ionicons5'
import PageHeader from '@/components/PageHeader.vue'
import {
  agentTeamsApi,
  type AgentTeamsCase,
  type AgentTeamsCaseStatus,
} from '@/api/agentTeams'

type ConversationMessage = {
  role: 'assistant' | 'user'
  content: string
}

const PAGE_SIZE = 20
const message = useMessage()
const router = useRouter()
const loading = ref(false)
const available = ref(false)
const cases = ref<AgentTeamsCase[]>([])
const total = ref(0)
const nextCursor = ref<string | null>(null)
const cursorHistory = ref<(string | undefined)[]>([undefined])
const page = ref(1)
const error = ref('')
const selectedStatus = ref<AgentTeamsCaseStatus | null>(null)
const projectId = ref('')
const creating = ref(false)
const draftReady = ref(false)
const conversationPanel = ref<HTMLElement | null>(null)
const createForm = ref({
  project_id: '',
  intent: '',
  sample_sheet: '[\n  { "sample": "S01", "group": "control" },\n  { "sample": "S02", "group": "treatment" }\n]',
  comparisons: '[\n  { "control": "control", "treatment": "treatment" }\n]',
})
const conversation = ref<ConversationMessage[]>([
  {
    role: 'assistant' as const,
    content: '描述你希望完成的分析目标。我会先整理为协作 Case 草案；真实计算任务仍必须通过预检与人工审批。',
  },
])

const statusLabel: Record<AgentTeamsCaseStatus, string> = {
  received: '已接收', preflight_running: '预检中', preflight_blocked: '预检阻断', waiting_for_correction: '等待修正',
  approval_pending: '待审批', approved: '已批准', executing: '执行中', execution_failed: '执行失败',
  quality_running: '质量检查中', quality_blocked: '质量阻断', remediation_pending: '等待修复', delivery_ready: '可交付', closed: '已关闭', cancelled: '已取消',
}
const statusOptions = Object.entries(statusLabel).map(([value, label]) => ({ value, label }))
const tagType = (status: AgentTeamsCaseStatus) => {
  if (['closed', 'delivery_ready'].includes(status)) return 'success'
  if (['preflight_blocked', 'quality_blocked', 'execution_failed'].includes(status)) return 'error'
  if (['approval_pending', 'waiting_for_correction', 'remediation_pending'].includes(status)) return 'warning'
  return 'info'
}
const columns = [
  {
    title: 'Case',
    key: 'case_id',
    width: 330,
    render: (row: AgentTeamsCase) => h(
      RouterLink,
      { to: `/agent-teams/cases/${row.case_id}`, class: 'case-link' },
      { default: () => [h('strong', row.intent), h('small', row.case_id)] },
    ),
  },
  {
    title: '当前阶段',
    key: 'status',
    width: 150,
    render: (row: AgentTeamsCase) => h(
      NTag,
      { type: tagType(row.status), bordered: false },
      { default: () => statusLabel[row.status] },
    ),
  },
  { title: '关联执行', key: 'tasks', width: 140, render: (row: AgentTeamsCase) => row.omic_task_ids.length ? `${row.omic_task_ids.length} 个任务` : '尚未提交' },
  { title: '最近更新', key: 'updated_at', width: 180, render: (row: AgentTeamsCase) => new Date(row.updated_at).toLocaleString('zh-CN') },
]

async function loadCases(targetPage = 1) {
  loading.value = true
  error.value = ''
  try {
    const state = await agentTeamsApi.status()
    available.value = state.available
    if (!state.available) {
      cases.value = []
      total.value = 0
      return
    }
    for (let pageToResolve = 1; pageToResolve < targetPage; pageToResolve += 1) {
      if (cursorHistory.value[pageToResolve] !== undefined) continue
      const cursorForPage = cursorHistory.value[pageToResolve - 1]
      if (cursorForPage === undefined) return
      const intermediate = await agentTeamsApi.listCases({
        status: selectedStatus.value ?? undefined,
        project_id: projectId.value.trim() || undefined,
        cursor: cursorForPage,
        limit: PAGE_SIZE,
      })
      if (!intermediate.next_cursor) return
      cursorHistory.value[pageToResolve] = intermediate.next_cursor
    }
    const cursor = cursorHistory.value[targetPage - 1]
    if (targetPage > 1 && cursor === undefined) return
    const result = await agentTeamsApi.listCases({
      status: selectedStatus.value ?? undefined,
      project_id: projectId.value.trim() || undefined,
      cursor,
      limit: PAGE_SIZE,
    })
    cases.value = result.items
    total.value = result.total
    nextCursor.value = result.next_cursor ?? null
    page.value = targetPage
    cursorHistory.value = cursorHistory.value.slice(0, targetPage)
    if (nextCursor.value) cursorHistory.value[targetPage] = nextCursor.value
  } catch (cause: any) {
    error.value = cause?.response?.data?.detail || '无法获取协作案例，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function resetAndLoad() {
  cursorHistory.value = [undefined]
  void loadCases(1)
}

function openConversation() {
  if (!available.value) {
    message.info('请先完成独立 AgentTeams Bridge 的接入配置。')
    return
  }
  void nextTick(() => conversationPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

function parseCaseContext(): { sampleSheet: Array<Record<string, unknown>>; comparisons?: Array<Record<string, unknown>> } | null {
  if (!createForm.value.project_id.trim() || !createForm.value.intent.trim()) {
    message.warning('请填写项目引用和协作目标后继续。')
    return null
  }
  try {
    const sampleSheet = JSON.parse(createForm.value.sample_sheet)
    const comparisons = createForm.value.comparisons.trim()
      ? JSON.parse(createForm.value.comparisons)
      : undefined
    if (!Array.isArray(sampleSheet) || !sampleSheet.length || (comparisons && !Array.isArray(comparisons))) {
      throw new Error('invalid structure')
    }
    return { sampleSheet, comparisons }
  } catch {
    message.warning('样本表与分组对比必须是有效的 JSON 数组。')
    return null
  }
}

function prepareDraft() {
  if (!parseCaseContext()) return
  conversation.value = [
    ...conversation.value,
    { role: 'user', content: createForm.value.intent.trim() },
    {
      role: 'assistant',
      content: '已整理为 RNA-seq 协作 Case 草案。创建后将由 Data Steward 只读预检；预检通过后，只有你在审批卡片中确认，Workflow Operator 才能提交真实计算。',
    },
  ]
  draftReady.value = true
}

async function createCase() {
  const context = parseCaseContext()
  if (!context) return
  creating.value = true
  try {
    const created = await agentTeamsApi.createCase({
      project_id: createForm.value.project_id.trim(),
      intent: createForm.value.intent.trim(),
      flow_id: 'rna_seq',
      sample_sheet: context.sampleSheet,
      comparisons: context.comparisons,
    })
    message.success('协作 Case 已创建，Data Steward 正在完成只读预检。')
    await router.push(`/agent-teams/cases/${created.case_id}`)
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '创建协作 Case 失败。')
  } finally {
    creating.value = false
  }
}

onMounted(() => { void loadCases() })
</script>

<template>
  <main class="page-container agent-teams-page">
    <PageHeader title="Agent 协作中心" subtitle="追踪多 Agent 的任务拆解、审批、执行证据与交付闭环">
      <template #leading><NIcon size="25"><GitNetworkOutline /></NIcon></template>
      <template #actions>
        <NButton secondary :loading="loading" @click="resetAndLoad">
          <template #icon><NIcon><RefreshOutline /></NIcon></template>刷新
        </NButton>
        <NButton type="primary" @click="openConversation">
          <template #icon><NIcon><ChatbubbleEllipsesOutline /></NIcon></template>发起协作对话
        </NButton>
      </template>
    </PageHeader>

    <NAlert v-if="!loading && !available && !error" type="info" title="AgentTeams 尚未接通" :show-icon="true">
      协作中心不会展示模拟运行数据。配置独立 Bridge 后，这里将只显示当前用户的真实 Case。
    </NAlert>
    <template v-else-if="error">
      <NAlert type="error" title="无法加载协作中心" :show-icon="true">{{ error }}</NAlert>
      <NButton class="alert-retry" size="small" @click="resetAndLoad">重试</NButton>
    </template>
    <template v-else-if="available">
      <NAlert type="info" :show-icon="true" class="collaboration-guide">
        使用方式：发起协作对话并创建 Case → Data Steward 自动只读预检 → 人工审批 → Workflow Operator 受令牌约束提交任务 → Quality Auditor 质量核验 → Delivery Reporter 输出交付证据。
      </NAlert>

      <section ref="conversationPanel" class="conversation-section" aria-labelledby="conversation-title">
        <NCard class="conversation-card" :segmented="{ content: true }">
          <template #header>
            <div>
              <strong id="conversation-title">协作对话</strong>
              <p>先描述目标，再审阅 Case 草案。这里不会直接启动计算。</p>
            </div>
          </template>
          <div class="conversation-layout">
            <div class="conversation-log" aria-live="polite">
              <div v-for="(item, index) in conversation" :key="`${item.role}-${index}`" class="chat-message" :class="`is-${item.role}`">
                <span class="chat-speaker">{{ item.role === 'assistant' ? 'AgentTeams Manager' : '你' }}</span>
                <p>{{ item.content }}</p>
              </div>
            </div>
            <NForm class="case-context" label-placement="top" @submit.prevent="prepareDraft">
              <NFormItem label="项目引用" required>
                <NInput v-model:value="createForm.project_id" placeholder="例如 project_rnaseq_202608" @update:value="draftReady = false" />
              </NFormItem>
              <NFormItem label="协作目标" required>
                <NInput v-model:value="createForm.intent" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" placeholder="例如：比较处理组与对照组的 RNA-seq 差异，并交付质控与结果报告。" @update:value="draftReady = false" />
              </NFormItem>
              <NFormItem label="样本表（JSON 数组）" required>
                <NInput v-model:value="createForm.sample_sheet" type="textarea" :autosize="{ minRows: 4, maxRows: 7 }" spellcheck="false" @update:value="draftReady = false" />
              </NFormItem>
              <NFormItem label="分组对比（JSON 数组，可选）">
                <NInput v-model:value="createForm.comparisons" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" spellcheck="false" @update:value="draftReady = false" />
              </NFormItem>
              <div class="conversation-actions">
                <NButton secondary attr-type="submit">
                  <template #icon><NIcon><SendOutline /></NIcon></template>整理 Case 草案
                </NButton>
                <NButton type="primary" :disabled="!draftReady" :loading="creating" @click="createCase">创建并进入预检</NButton>
              </div>
            </NForm>
          </div>
          <NAlert v-if="draftReady" class="draft-notice" type="warning" title="草案已就绪，尚未执行" :show-icon="true">
            创建 Case 只会启动只读预检。预检通过后会在 Case 详情展示带影响范围的人工审批卡片。
          </NAlert>
        </NCard>
      </section>

      <NCard class="case-card" title="协作 Case" :segmented="{ content: true }">
        <div class="case-filters" aria-label="协作 Case 筛选">
          <NSelect
            v-model:value="selectedStatus"
            clearable
            :options="statusOptions"
            placeholder="全部阶段"
            @update:value="resetAndLoad"
          />
          <NInput
            v-model:value="projectId"
            clearable
            placeholder="按项目引用筛选"
            @keyup.enter="resetAndLoad"
            @clear="resetAndLoad"
          />
          <NButton secondary @click="resetAndLoad">应用筛选</NButton>
        </div>
        <NSpin :show="loading">
          <NDataTable v-if="cases.length" :columns="columns" :data="cases" :bordered="false" :scroll-x="800" />
          <NEmpty v-else description="当前筛选条件下没有可见的协作 Case" />
        </NSpin>
        <div v-if="total > PAGE_SIZE" class="case-pagination">
          <NPagination
            :page="page"
            :page-size="PAGE_SIZE"
            :item-count="total"
            :page-slot="5"
            :disabled="loading"
            @update:page="loadCases"
          />
        </div>
      </NCard>
    </template>
  </main>
</template>

<style scoped>
.agent-teams-page { min-height: 100%; }
.collaboration-guide, .conversation-section { margin-bottom: 24px; }
.conversation-section { scroll-margin-top: 20px; }
.conversation-card :deep(.n-card-header__main) { min-width: 0; }
.conversation-card :deep(.n-card-header p) { margin: 4px 0 0; color: var(--text-secondary); font-size: 13px; font-weight: 400; }
.conversation-layout { display: grid; grid-template-columns: minmax(280px, .85fr) minmax(360px, 1.15fr); gap: 20px; }
.conversation-log { display: grid; align-content: start; gap: 12px; min-height: 220px; padding: 4px; }
.chat-message { display: grid; gap: 4px; max-width: min(100%, 560px); padding: 12px 14px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-color, var(--bg-card)); }
.chat-message.is-user { justify-self: end; border-color: color-mix(in srgb, var(--primary-color) 35%, var(--border-color)); background: color-mix(in srgb, var(--primary-color) 9%, var(--card-color, var(--bg-card))); }
.chat-speaker { color: var(--text-tertiary); font-size: 12px; font-weight: 600; }
.chat-message p { margin: 0; color: var(--text-secondary); font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.case-context { min-width: 0; }
.conversation-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
.draft-notice { margin-top: 16px; }
.case-card { background: var(--card-color, var(--bg-card)); }
.case-filters { display: grid; grid-template-columns: minmax(150px, 210px) minmax(180px, 320px) auto; gap: 10px; margin-bottom: 16px; }
.case-link { display: flex; flex-direction: column; gap: 3px; color: var(--primary-color); text-decoration: none; }
.case-link small { color: var(--text-tertiary); }
.case-pagination { display: flex; justify-content: flex-end; margin-top: 16px; }
.alert-retry { margin-left: 10px; }
@media (max-width: 900px) { .conversation-layout { grid-template-columns: 1fr; } }
@media (max-width: 768px) { .case-filters { grid-template-columns: 1fr; } .conversation-actions { flex-direction: column; } .conversation-actions :deep(.n-button) { width: 100%; } .case-pagination { justify-content: center; } }
</style>
