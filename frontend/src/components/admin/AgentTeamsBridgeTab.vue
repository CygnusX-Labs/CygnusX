<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputNumber,
  NSpin,
  NTag,
  NSwitch,
  useMessage,
} from 'naive-ui'
import { RefreshOutline, SaveOutline } from '@vicons/ionicons5'
import AdminTOTPConfirmModal from '@/components/AdminTOTPConfirmModal.vue'
import {
  agentTeamsBridgeAdminApi,
  type AgentTeamsBridgeConfig,
} from '@/api/admin/agentTeamsBridge'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const confirmVisible = ref(false)
const config = ref<AgentTeamsBridgeConfig>({
  enabled: false,
  bridge_url: '',
  timeout_seconds: 10,
  manager_token: '',
  data_steward_token: '',
  approval_token: '',
  workflow_operator_token: '',
  source: 'database',
  configured: false,
  connected: false,
})

async function load() {
  loading.value = true
  try {
    config.value = await agentTeamsBridgeAdminApi.get()
  } catch (cause: any) {
    message.error(cause?.response?.data?.detail || '无法读取 AgentTeams Bridge 配置。')
  } finally {
    loading.value = false
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

onMounted(() => { void load() })
</script>

<template>
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
</template>

<style scoped>
.bridge-card { background: var(--card-color, var(--bg-card)); }
.bridge-heading { display: grid; gap: 4px; }
.bridge-heading span, .bridge-status-row p { color: var(--text-secondary); font-size: 13px; font-weight: 400; line-height: 1.5; }
.bridge-note { margin-bottom: 16px; }
.bridge-form { max-width: 980px; }
.bridge-status-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 12px 0 20px; }
.bridge-status-row strong { color: var(--text-primary); font-size: 14px; }
.bridge-status-row p { max-width: 700px; margin: 4px 0 0; }
.bridge-secret-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.bridge-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
@media (max-width: 768px) { .bridge-status-row { align-items: flex-start; } .bridge-secret-grid { grid-template-columns: 1fr; } .bridge-actions { flex-direction: column-reverse; } .bridge-actions :deep(.n-button) { width: 100%; } }
</style>
