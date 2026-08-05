<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputNumber,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpin,
  NTag,
  NSwitch,
  useMessage,
} from 'naive-ui'
import { CopyOutline, RefreshOutline, SaveOutline } from '@vicons/ionicons5'
import AdminTOTPConfirmModal from '@/components/AdminTOTPConfirmModal.vue'
import {
  agentTeamsBridgeAdminApi,
  type AgentTeamsBridgeConfig,
  type AgentTeamsBridgeHealth,
  type AgentTeamsBridgeResourceSnapshot,
  type AgentTeamsBridgeTokenBundle,
} from '@/api/admin/agentTeamsBridge'
import apiClient from '@/api/client'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const confirmVisible = ref(false)
const tokenConfirmVisible = ref(false)
const tokenGenerating = ref(false)
const generatedTokens = ref<AgentTeamsBridgeTokenBundle | null>(null)
const resources = ref<AgentTeamsBridgeResourceSnapshot | null>(null)
const resourceLoading = ref(false)
const reconcileCaseId = ref('')
const reconcileConfirmVisible = ref(false)
const reconciling = ref(false)
const config = ref<AgentTeamsBridgeConfig>({
  enabled: false,
  bridge_url: '',
  timeout_seconds: 10,
  manager_token: '',
  data_steward_token: '',
  approval_token: '',
  workflow_operator_token: '',
  element_url: '',
  source: 'database',
  configured: false,
  connected: false,
})
type CollaborationPreset = 'custom' | 'light' | 'parallel' | 'full'
const preset = ref<CollaborationPreset>('custom')
const presetSaving = ref(false)
const presetConfirmVisible = ref(false)
const health = ref<AgentTeamsBridgeHealth | null>(null)
const degradationCounts = ref<Record<string, number>>({ fanout: 0, consult: 0, case: 0, dag: 0 })
const degradationLocale = ref<'zh-CN' | 'en'>('zh-CN')
const degradationTemplateZh = ref('')
const degradationTemplateEn = ref('')
const templateSaving = ref(false)
const presetDescription = computed(() => ({
  light: '轻量协作：专家转交与多专家会诊。',
  parallel: '并行增强：轻量协作 + 对话内 Fan-out。',
  full: '全流程闭环：并行增强 + AgentTeams Case 入口；仍需保存并接通 Bridge。',
  custom: '自定义：保留当前各项开关组合。',
})[preset.value])
const presetDiff = computed(() => ({
  light: ['统一意图路由：开启', '多专家会诊：开启', '并行 Fan-out：关闭', '协作 Case 入口：关闭'],
  parallel: ['统一意图路由：开启', '多专家会诊：开启', '并行 Fan-out：开启', '协作 Case 入口：关闭'],
  full: ['统一意图路由：开启', '多专家会诊：开启', '并行 Fan-out：开启', '协作 Case 入口：开启'],
  custom: ['不改动现有功能开关，仅将档位标记为“自定义”。'],
})[preset.value])
const inactiveWorkers = computed(() => health.value?.workers.filter((worker) => !worker.active) || [])
const onboardingSteps = computed(() => [
  { title: '填写 Bridge 地址', complete: Boolean(config.value.bridge_url.trim()) },
  { title: '配置四个 Worker 令牌', complete: config.value.configured },
  { title: '保存并启用配置', complete: config.value.enabled },
  { title: '验证 Bridge 连接', complete: config.value.connected },
  { title: '确认 Worker 心跳', complete: Boolean(health.value?.workers.length) && !inactiveWorkers.value.length },
])

async function load() {
  loading.value = true
  try {
    config.value = await agentTeamsBridgeAdminApi.get()
    const [platform, healthResponse, observability, resourceSnapshot] = await Promise.all([
      apiClient.get<{
        collaboration_preset?: CollaborationPreset
        collaboration_degradation_locale?: 'zh-CN' | 'en'
        collaboration_degradation_template_zh?: string
        collaboration_degradation_template_en?: string
      }>('/platform/config'),
      agentTeamsBridgeAdminApi.health(),
      apiClient.get<{ degradation_counts?: Record<string, number> }>('/admin/platform-config/collaboration-observability'),
      agentTeamsBridgeAdminApi.resources(),
    ])
    preset.value = platform.data.collaboration_preset || 'custom'
    degradationLocale.value = platform.data.collaboration_degradation_locale || 'zh-CN'
    degradationTemplateZh.value = platform.data.collaboration_degradation_template_zh || ''
    degradationTemplateEn.value = platform.data.collaboration_degradation_template_en || ''
    health.value = healthResponse
    resources.value = resourceSnapshot
    degradationCounts.value = { ...degradationCounts.value, ...(observability.data.degradation_counts || {}) }
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '无法读取 AgentTeams Bridge 配置。')
  } finally {
    loading.value = false
  }
}

async function loadResources() {
  resourceLoading.value = true
  try {
    resources.value = await agentTeamsBridgeAdminApi.resources()
    health.value = resources.value.health
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '读取 AgentTeams 资源失败。')
  } finally {
    resourceLoading.value = false
  }
}

async function saveDegradationTemplates() {
  templateSaving.value = true
  try {
    await apiClient.patch('/admin/platform-config', {
      collaboration_degradation_locale: degradationLocale.value,
      collaboration_degradation_template_zh: degradationTemplateZh.value,
      collaboration_degradation_template_en: degradationTemplateEn.value,
    })
    message.success('协作降级文案已保存。')
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '保存协作降级文案失败。')
  } finally {
    templateSaving.value = false
  }
}

function requestApplyPreset() {
  presetConfirmVisible.value = true
}

async function applyPreset() {
  presetSaving.value = true
  try {
    await apiClient.patch('/admin/platform-config', { collaboration_preset: preset.value })
    presetConfirmVisible.value = false
    message.success(`已应用“${presetDescription.value.split('：')[0]}”档位。`)
    if (preset.value === 'full' && !config.value.connected) {
      message.warning('全流程闭环还需要保存并接通下方 Bridge 配置。')
    }
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '应用协作档位失败。')
  } finally {
    presetSaving.value = false
  }
}

function requestSave() {
  if (config.value.enabled && !config.value.bridge_url.trim()) {
    message.warning('启用前请填写 Bridge 地址。')
    return
  }
  confirmVisible.value = true
}

async function save(totpCode: string) {
  saving.value = true
  try {
    config.value = await agentTeamsBridgeAdminApi.update(config.value, totpCode)
    confirmVisible.value = false
    message.success(config.value.connected ? 'Bridge 已保存并接通。' : 'Bridge 配置已保存，当前尚未接通。')
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '保存 AgentTeams Bridge 配置失败。')
  } finally {
    saving.value = false
  }
}

async function generateTokens(totpCode: string) {
  tokenGenerating.value = true
  try {
    const tokens = await agentTeamsBridgeAdminApi.generateTokens(totpCode)
    generatedTokens.value = tokens
    config.value = { ...config.value, ...tokens }
    tokenConfirmVisible.value = false
    message.success('已生成新令牌并填入表单；请复制到 Worker 部署配置后保存。')
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '生成 Worker 令牌失败。')
  } finally {
    tokenGenerating.value = false
  }
}

async function copyGeneratedTokens() {
  if (!generatedTokens.value) return
  const content = [
    `bioops-manager:${generatedTokens.value.manager_token}`,
    `data-steward:${generatedTokens.value.data_steward_token}`,
    `approval-authority:${generatedTokens.value.approval_token}`,
    `workflow-operator:${generatedTokens.value.workflow_operator_token}`,
  ].join('\n')
  try {
    await navigator.clipboard.writeText(content)
    message.success('已复制 Worker 身份令牌清单。')
  } catch {
    message.error('复制失败，请手动复制。')
  }
}

function requestReconcile(caseId: string) {
  reconcileCaseId.value = caseId
  reconcileConfirmVisible.value = true
}

async function reconcileCase(totpCode: string) {
  if (!reconcileCaseId.value) return
  reconciling.value = true
  try {
    await agentTeamsBridgeAdminApi.reconcileCase(reconcileCaseId.value, totpCode)
    reconcileConfirmVisible.value = false
    message.success(`已重协调 Case ${reconcileCaseId.value}。`)
    await loadResources()
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '重协调协作 Case 失败。')
  } finally {
    reconciling.value = false
  }
}

const resourceColumns = [
  { title: 'Case', key: 'case_id', width: 220 },
  { title: 'Team', key: 'team_id', width: 170 },
  { title: '状态', key: 'status', width: 130 },
  { title: '项目', key: 'project', width: 150, render: (row: { project_ref: { id: string } }) => row.project_ref?.id || '-' },
  { title: '操作', key: 'actions', width: 130, render: (row: { case_id: string }) => h(NButton, { size: 'tiny', secondary: true, onClick: () => requestReconcile(row.case_id) }, { default: () => '重协调' }) },
]

function resourceCaseRowKey(row: { case_id: string }) {
  return row.case_id
}

onMounted(() => { void load() })
</script>

<template>
  <div class="agentteams-bridge-tab">
    <div class="tab-header">
      <span class="tab-hint">配置协作中心的多 Agent 编排接入地址与加密身份令牌，保存需 TOTP 二次验证。</span>
    </div>
    <NSpin :show="loading">
      <NCard class="bridge-card" :segmented="{ content: true }">
        <template #header>
          <div class="bridge-heading">
            <strong>AgentTeams Bridge</strong>
            <span>为协作 Case 提供隔离的多 Agent 编排、审批与审计通道。</span>
          </div>
        </template>
        <template #header-extra>
          <NTag :type="config.connected ? 'success' : config.enabled ? 'warning' : 'default'" :bordered="false">
            {{ config.connected ? '已接通' : config.enabled ? '等待接通' : '未启用' }}
          </NTag>
        </template>

      <NAlert type="info" :show-icon="true" class="bridge-note">
        此配置仅限管理员。四个身份令牌以加密形式保存，读取时始终脱敏；保存、启用和切换地址均需 TOTP 二次验证。
      </NAlert>
      <NAlert v-if="config.source === 'environment'" type="warning" :show-icon="true" class="bridge-note">
        当前配置来自服务端环境变量。保存后会迁移为数据库加密配置，并覆盖该运行实例的环境变量回退值。
      </NAlert>

      <NCard size="small" class="preset-card" :bordered="true">
        <template #header>协作能力档位</template>
        <p class="preset-hint">{{ presetDescription }}</p>
        <NRadioGroup v-model:value="preset" name="collaboration-preset" class="preset-options">
          <NRadioButton value="light">轻量协作</NRadioButton>
          <NRadioButton value="parallel">并行增强</NRadioButton>
          <NRadioButton value="full">全流程闭环</NRadioButton>
          <NRadioButton value="custom">自定义</NRadioButton>
        </NRadioGroup>
        <div class="preset-actions">
          <NButton size="small" type="primary" :loading="presetSaving" @click="requestApplyPreset">查看变更并应用</NButton>
        </div>
        <div class="degradation-counts" aria-label="近七天协作降级次数">
          <span>近 7 天降级：</span>
          <span>并行 {{ degradationCounts.fanout || 0 }}</span>
          <span>会诊 {{ degradationCounts.consult || 0 }}</span>
          <span>Case {{ degradationCounts.case || 0 }}</span>
          <span>MAS {{ degradationCounts.dag || 0 }}</span>
        </div>
      </NCard>

      <NCard size="small" class="health-card" :bordered="true">
        <template #header>协作部署健康检查</template>
        <NAlert v-if="!health?.connection.connected" type="error" :show-icon="true" class="bridge-note">
          Bridge 尚未接通，无法验证身份令牌和外部 Worker。仅修改平台配置不会启动外部 Worker。
        </NAlert>
        <template v-else>
          <div class="health-row"><strong>Bridge 与身份令牌</strong><span>{{ health.identities.filter((item) => item.valid).length }}/{{ health.identities.length }} 有效</span></div>
          <div class="health-row"><strong>外部 Worker</strong><span>{{ health.workers.filter((item) => item.active).length }}/{{ health.workers.length }} 活跃</span></div>
          <NAlert v-if="inactiveWorkers.length" type="error" :show-icon="true" class="bridge-note">
            {{ inactiveWorkers.map((worker) => worker.identity).join('、') }} 未在心跳窗口内轮询任务。请按 `deploy/agentteams/README.md` 部署对应 Worker。
          </NAlert>
          <NAlert :type="health.scrna_submit_available ? 'success' : 'warning'" :show-icon="true" class="bridge-note">
            {{ health.scrna_submit_available ? 'Bridge 白名单已包含 scrna_seq。' : `当前白名单：${health.allowed_flows.join(', ') || '未读取'}；scrna 流程暂不可提交。` }}
          </NAlert>
        </template>
      </NCard>

      <NCard size="small" class="onboarding-card" :bordered="true">
        <template #header>Bridge 接入向导</template>
        <p class="preset-hint">按顺序完成配置。检测只读取 Bridge 健康状态，不会改动运行中的 Worker。</p>
        <ol class="onboarding-list">
          <li v-for="(step, index) in onboardingSteps" :key="step.title" :class="{ complete: step.complete }">
            <NTag :type="step.complete ? 'success' : 'default'" size="small" :bordered="false">{{ step.complete ? '已完成' : `第 ${index + 1} 步` }}</NTag>
            <span>{{ step.title }}</span>
          </li>
        </ol>
        <NAlert v-if="generatedTokens" type="warning" :show-icon="true" class="bridge-note">
          新令牌仅在本次页面会话中显示。复制到 Worker 环境变量后立即保存，离开页面前请妥善保管。
        </NAlert>
        <div class="onboarding-actions">
          <NButton secondary :loading="loading" @click="load"><template #icon><NIcon><RefreshOutline /></NIcon></template>一键检测</NButton>
          <NButton secondary @click="tokenConfirmVisible = true">生成四个 Worker 令牌</NButton>
          <NButton v-if="generatedTokens" size="small" secondary @click="copyGeneratedTokens"><template #icon><NIcon><CopyOutline /></NIcon></template>复制身份令牌</NButton>
        </div>
      </NCard>

      <NCard size="small" class="resource-card" :bordered="true">
        <template #header>AgentTeams 资源管理</template>
        <template #header-extra><NButton size="small" secondary :loading="resourceLoading" @click="loadResources"><template #icon><NIcon><RefreshOutline /></NIcon></template>刷新资源</NButton></template>
        <NAlert v-if="!resources?.health.connection.connected" type="warning" :show-icon="true" class="bridge-note">
          Bridge 未接通时无法读取真实资源。请先完成接入向导并检查 Worker 部署。
        </NAlert>
        <template v-else>
          <div class="resource-summary">
            <span>Worker：{{ resources.health.workers.filter((worker) => worker.active).length }}/{{ resources.health.workers.length }} 活跃</span>
            <span>Team：{{ resources.teams.length }}</span>
            <span>Case：{{ resources.total_cases }}</span>
          </div>
          <div v-if="resources.teams.length" class="team-chips">
            <NTag v-for="team in resources.teams" :key="team.team_id" size="small" :bordered="false">{{ team.team_id }} · {{ team.case_count }} Case</NTag>
          </div>
          <NDataTable
            v-if="resources.cases.length"
            class="resource-case-table"
            :columns="resourceColumns"
            :data="resources.cases"
            :row-key="resourceCaseRowKey"
            :bordered="false"
            :scroll-x="800"
          />
          <p v-else class="resource-empty">当前没有可管理的协作 Case。</p>
          <p class="resource-note">Worker 生命周期由独立 Worker 部署管理；此处仅显示心跳。Case 重协调会由 Bridge 重新同步其受控任务状态，需 TOTP 二次验证。</p>
        </template>
      </NCard>

      <NCard size="small" class="template-card" :bordered="true">
        <template #header>协作降级文案</template>
        <p class="preset-hint">可使用占位符：<code>{intent}</code>、<code>{setting}</code>、<code>{alternative}</code>。</p>
        <NForm label-placement="top">
          <NFormItem label="默认展示语言">
            <NSelect
              v-model:value="degradationLocale"
              :options="[{ label: '中文', value: 'zh-CN' }, { label: 'English', value: 'en' }]"
            />
          </NFormItem>
          <NFormItem label="中文模板">
            <NInput v-model:value="degradationTemplateZh" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </NFormItem>
          <NFormItem label="English template">
            <NInput v-model:value="degradationTemplateEn" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </NFormItem>
          <div class="preset-actions"><NButton size="small" :loading="templateSaving" @click="saveDegradationTemplates">保存文案</NButton></div>
        </NForm>
      </NCard>

      <NForm label-placement="top" class="bridge-form">
        <div class="bridge-status-row">
          <div>
            <strong>启用协作中心</strong>
            <p>关闭后所有用户都会看到“尚未接通”，并且无法创建或提交 Case。</p>
          </div>
          <NSwitch v-model:value="config.enabled" />
        </div>
        <NFormItem label="Bridge 地址">
          <NInput v-model:value="config.bridge_url" placeholder="例如 http://agentteams-bridge:8080" />
        </NFormItem>
        <NFormItem label="请求超时（秒）">
          <NInputNumber v-model:value="config.timeout_seconds" :min="1" :max="120" :precision="0" />
        </NFormItem>
        <NFormItem label="Element 协作房间地址">
          <NInput v-model:value="config.element_url" placeholder="例如 https://element.example/#/room/!bioops:example.org" />
          <template #feedback>仅填写用户可访问的 Element 房间链接；不得包含 access token、登录令牌或密码。</template>
        </NFormItem>
        <div class="bridge-secret-grid">
          <NFormItem label="Manager 令牌"><NInput v-model:value="config.manager_token" type="password" show-password-on="click" placeholder="未填写则保留已配置令牌" /></NFormItem>
          <NFormItem label="Data Steward 令牌"><NInput v-model:value="config.data_steward_token" type="password" show-password-on="click" placeholder="未填写则保留已配置令牌" /></NFormItem>
          <NFormItem label="审批身份令牌"><NInput v-model:value="config.approval_token" type="password" show-password-on="click" placeholder="未填写则保留已配置令牌" /></NFormItem>
          <NFormItem label="Workflow Operator 令牌"><NInput v-model:value="config.workflow_operator_token" type="password" show-password-on="click" placeholder="未填写则保留已配置令牌" /></NFormItem>
        </div>
        <div class="bridge-actions">
          <NButton secondary :loading="loading" @click="load"><template #icon><NIcon><RefreshOutline /></NIcon></template>重新检查</NButton>
          <NButton type="primary" @click="requestSave"><template #icon><NIcon><SaveOutline /></NIcon></template>保存并检查连接</NButton>
        </div>
      </NForm>
    </NCard>
  </NSpin>

  <AdminTOTPConfirmModal
    v-model:show="confirmVisible"
    title="保存 AgentTeams Bridge 配置"
    description="该操作会更新全局多 Agent 编排接入和加密凭证。请输入当前 6 位 TOTP 验证码后继续。"
    confirm-text="保存配置"
    :loading="saving"
    @confirm="save"
  />
  <AdminTOTPConfirmModal
    v-model:show="tokenConfirmVisible"
    title="生成 AgentTeams Worker 令牌"
    description="将生成四个新的高熵 Worker 令牌，仅回显一次且不会自动保存。确认后请部署 Worker，再保存 Bridge 配置。"
    confirm-text="生成令牌"
    :loading="tokenGenerating"
    @confirm="generateTokens"
  />
  <AdminTOTPConfirmModal
    v-model:show="reconcileConfirmVisible"
    title="重协调协作 Case"
    :description="'将请求 Bridge 重新同步 Case ' + reconcileCaseId + ' 的受控任务状态；不会绕过审批或创建新计算任务。'"
    confirm-text="确认重协调"
    :loading="reconciling"
    @confirm="reconcileCase"
  />
  <NModal v-model:show="presetConfirmVisible" preset="dialog" title="确认应用协作档位" positive-text="确认应用" negative-text="取消" @positive-click="applyPreset">
    <p>将应用“{{ presetDescription.split('：')[0] }}”，并原子性写入以下开关：</p>
    <ul class="preset-diff">
      <li v-for="item in presetDiff" :key="item">{{ item }}</li>
    </ul>
  </NModal>
  </div>
</template>

<style scoped>
.tab-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 14px; }
.tab-hint { font-size: 12px; color: var(--neutral-text-3); }
.bridge-heading { display: grid; gap: 4px; }
.bridge-heading strong { color: var(--neutral-text-1); }
.bridge-heading span, .bridge-status-row p { color: var(--neutral-text-2); font-size: 13px; font-weight: 400; line-height: 1.5; }
.bridge-note { margin-bottom: 16px; }
.preset-card { margin-bottom: 16px; }
.preset-hint { margin: 0 0 10px; color: var(--neutral-text-2); font-size: 13px; line-height: 1.5; }
.preset-options { display: flex; flex-wrap: wrap; }
.preset-actions { display: flex; justify-content: flex-end; margin-top: 12px; }
.degradation-counts { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 12px; color: var(--neutral-text-2); font-size: 12px; }
.health-card { margin-bottom: 16px; }
.onboarding-card { margin-bottom: 16px; }
.onboarding-list { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.onboarding-list li { display: flex; align-items: center; gap: 8px; color: var(--neutral-text-2); font-size: 13px; }
.onboarding-list li.complete { color: var(--neutral-text-1); }
.onboarding-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.resource-card { margin-bottom: 16px; }
.resource-summary, .team-chips { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-bottom: 12px; color: var(--neutral-text-2); font-size: 13px; }
.resource-case-table { margin-top: 10px; }
.resource-empty, .resource-note { margin: 10px 0 0; color: var(--neutral-text-2); font-size: 12px; line-height: 1.55; }
.template-card { margin-bottom: 16px; }
.health-row { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; color: var(--neutral-text-2); font-size: 13px; }
.health-row strong { color: var(--neutral-text-1); }
.preset-diff { margin: 8px 0 0; padding-left: 20px; line-height: 1.8; color: var(--neutral-text-2); }
.bridge-form { max-width: 980px; }
.bridge-status-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 12px 0 20px; }
.bridge-status-row strong { color: var(--neutral-text-1); font-size: 14px; }
.bridge-status-row p { max-width: 700px; margin: 4px 0 0; }
.bridge-secret-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.bridge-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
@media (max-width: 768px) { .bridge-status-row { align-items: flex-start; } .bridge-secret-grid { grid-template-columns: 1fr; } .bridge-actions { flex-direction: column-reverse; } .bridge-actions :deep(.n-button) { width: 100%; } }
</style>
