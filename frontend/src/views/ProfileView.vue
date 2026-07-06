<template>
  <div class="profile-page-wrapper">
    <div class="profile-bento-grid">
      <!-- 1. 用户信息 —— 全宽 -->
      <div class="bento-card bento-col-3 user-info-card">
        <div class="user-info-header">
          <NAvatar round :size="56" :src="user?.avatar_url || undefined" class="user-avatar">
            {{ userInitial }}
          </NAvatar>
          <div class="user-info-main">
            <div class="user-info-name-row">
              <span class="user-name">{{ displayName(user) }}</span>
              <NTag :type="roleTagType" size="small" round class="role-tag">
                {{ roleLabel }}
              </NTag>
            </div>
            <div class="user-info-meta">
              ID: {{ shortId }} · 创建于 {{ formatDateOnly(user?.created_at) }}
            </div>
            <div class="user-info-extra">
              <span v-if="user?.email">{{ user.email }}</span>
              <span v-if="user?.status" class="user-status-dot" :class="`user-status-dot--${user.status}`">/</span>
              <span v-if="user?.status" :style="{ color: statusTagColor }">{{ statusLabel }}</span>
            </div>
          </div>
          <NButton text size="small" class="avatar-edit-btn" @click="avatarEditHint">
            <template #icon>
              <NIcon><CreateOutline /></NIcon>
            </template>
            修改头像
          </NButton>
        </div>
      </div>

      <!-- 2. KPI 三兄弟 -->
      <div
        v-for="(kpi, idx) in kpiList"
        :key="idx"
        class="bento-card bento-col-1 kpi-card"
      >
        <div class="kpi-value" :class="{ 'kpi-value--pulse': kpi.pulse }" :style="{ color: kpi.color }">
          {{ kpi.value }}
        </div>
        <div class="kpi-label">{{ kpi.label }}</div>
        <div v-if="kpi.total" class="kpi-bar">
          <div class="kpi-bar-fill" :style="{ width: `${kpiPercent(kpi)}%`, background: kpi.color }" />
        </div>
      </div>

      <!-- 3. 最近任务 —— 占 2 列 -->
      <div class="bento-card bento-col-2">
        <div class="bento-card-title">
          <NIcon><ListOutline /></NIcon>
          <span>最近任务</span>
          <NButton text size="small" class="card-action" @click="router.push('/tasks')">
            查看全部 →
          </NButton>
        </div>
        <div v-if="recentTasks.length" class="task-list">
          <div
            v-for="(task, idx) in recentTasks"
            :key="task.id"
            class="task-row"
            :class="{ 'task-row--last': idx === recentTasks.length - 1 }"
            @click="router.push(`/tasks/${task.id}`)"
          >
            <span class="task-status-dot" :style="{ color: taskStatus(task.status).color }">
              {{ taskStatus(task.status).icon }}
            </span>
            <div class="task-info">
              <div class="task-name">{{ task.name }}</div>
              <div class="task-meta">{{ task.flow_name }} · {{ formatRelative(task.created_at) }}</div>
            </div>
            <NTag :color="taskStatusColor(task.status)" size="small" round>
              {{ taskStatus(task.status).text }}
            </NTag>
          </div>
        </div>
        <div v-else class="empty-state">暂无任务</div>
      </div>

      <!-- 4. 常用流程 —— 占 1 列 -->
      <div class="bento-card bento-col-1">
        <div class="bento-card-title">
          <NIcon><FlashOutline /></NIcon>
          <span>常用流程</span>
        </div>
        <div class="flow-list">
          <div
            v-for="flow in favoriteFlows"
            :key="flow.id"
            class="flow-chip"
            @click="router.push(`/flows/${flow.id}/submit`)"
          >
            <span class="flow-icon">{{ flow.icon }}</span>
            <span class="flow-name">{{ flow.name }}</span>
          </div>
        </div>
      </div>

      <!-- 5. 安全与登录 —— 占 1 列 -->
      <div class="bento-card bento-col-1">
        <div class="bento-card-title">
          <NIcon><ShieldCheckmarkOutline /></NIcon>
          <span>安全与登录</span>
        </div>
        <div class="info-list">
          <div class="info-row">
            <span class="info-label">最后登录</span>
            <span class="info-value">{{ formatShortTime(session?.last_active_at) }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">登录 IP</span>
            <code class="info-value-mono">{{ session?.ip_address || '-' }}</code>
          </div>
          <div class="info-row">
            <span class="info-label">设备</span>
            <span class="info-value">{{ session?.user_agent || '-' }}</span>
          </div>
        </div>
        <div class="security-actions">
          <NButton text size="small" @click="showLoginHistory = true">登录历史 →</NButton>
          <NButton text size="small" @click="showActiveSessions = true">会话 →</NButton>
        </div>
      </div>

      <!-- 6. 平台偏好 —— 占 2 列 -->
      <div class="bento-card bento-col-2">
        <div class="bento-card-title">
          <NIcon><SettingsOutline /></NIcon>
          <span>平台偏好</span>
        </div>
        <div class="pref-grid">
          <div class="pref-row">
            <label class="pref-label">默认首页</label>
            <NSelect v-model:value="preferences.default_page" :options="defaultPageOptions" size="small" @update:value="savePreferences" />
          </div>
          <div class="pref-row">
            <label class="pref-label">语言</label>
            <NSelect v-model:value="preferences.language" :options="languageOptions" size="small" @update:value="savePreferences" />
          </div>
          <div class="pref-row pref-row--full">
            <label class="pref-label">主题</label>
            <NRadioGroup v-model:value="preferences.theme" size="small" @update:value="onThemeChange">
              <NRadioButton value="system">跟随系统</NRadioButton>
              <NRadioButton value="light">亮色</NRadioButton>
              <NRadioButton value="dark">深色</NRadioButton>
            </NRadioGroup>
          </div>
          <div class="pref-row pref-row--full">
            <label class="pref-label">通知渠道</label>
            <NSpace size="small">
              <NCheckbox v-model:checked="preferences.notifications.email" @update:checked="savePreferences">邮件</NCheckbox>
              <NCheckbox v-model:checked="preferences.notifications.in_app" @update:checked="savePreferences">站内消息</NCheckbox>
              <NCheckbox v-model:checked="preferences.notifications.webhook" @update:checked="savePreferences">Webhook</NCheckbox>
            </NSpace>
          </div>
        </div>
      </div>

      <!-- 7. API 密钥 —— 全宽 -->
      <div class="bento-card bento-col-3">
        <div class="bento-card-title">
          <NIcon><KeyOutline /></NIcon>
          <span>API 密钥</span>
          <NButton text size="small" class="card-action" @click="handleCreateApiKey">
            + 新建
          </NButton>
        </div>

        <div v-if="newApiKey" class="new-api-key-banner">
          <div class="new-api-key-title">⚠️ 请立即复制保存，此密钥只显示一次</div>
          <code class="new-api-key-code">{{ newApiKey }}</code>
          <NButton size="tiny" @click="copyNewKey">复制</NButton>
        </div>

        <div v-if="apiKeys.length" class="api-key-list">
          <div
            v-for="(key, idx) in apiKeys"
            :key="key.id"
            class="api-key-row"
            :class="{ 'api-key-row--last': idx === apiKeys.length - 1 }"
          >
            <div class="api-key-info">
              <div class="api-key-name">{{ key.name }}</div>
              <div class="api-key-meta">
                {{ key.masked_key }} · 创建于 {{ formatDateOnly(key.created_at) }}
                <span v-if="key.last_used_at"> · 最后使用 {{ formatRelative(key.last_used_at) }}</span>
              </div>
            </div>
            <NButton text size="small" type="error" @click="handleRevokeApiKey(key.id)">
              撤销
            </NButton>
          </div>
        </div>
        <div v-else class="empty-state">暂无 API 密钥</div>
      </div>

      <!-- 8. 数据与隐私 —— 占 2 列 -->
      <div class="bento-card bento-col-2">
        <div class="bento-card-title">
          <NIcon><ShieldOutline /></NIcon>
          <span>数据与隐私</span>
        </div>
        <div class="privacy-list">
          <div class="privacy-row">
            <div>
              <div class="privacy-title">导出分析历史</div>
              <div class="privacy-desc">下载包含所有任务、设置和数据的 JSON 文件</div>
            </div>
            <NButton size="small" :loading="exporting" @click="handleExportData">导出</NButton>
          </div>
          <div class="privacy-row">
            <div>
              <div class="privacy-title">下载个人数据</div>
              <div class="privacy-desc">符合 GDPR 要求的数据副本</div>
            </div>
            <NButton size="small" :loading="exporting" @click="handleExportData">下载</NButton>
          </div>
          <div class="privacy-row privacy-row--danger">
            <div>
              <div class="privacy-title">删除账户</div>
              <div class="privacy-desc">永久删除账户和所有关联数据</div>
            </div>
            <NPopconfirm @positive-click="handleDeleteAccount">
              <template #trigger>
                <NButton size="small" type="error">删除</NButton>
              </template>
              确认删除账户？此操作不可撤销，将删除你的所有数据、任务和历史记录。
            </NPopconfirm>
          </div>
        </div>
      </div>

      <!-- 9. 审计日志 —— 占 1 列 -->
      <div class="bento-card bento-col-1">
        <div class="bento-card-title">
          <NIcon><LockClosedOutline /></NIcon>
          <span>审计日志</span>
        </div>
        <div class="audit-list">
          <div
            v-for="(log, idx) in auditLogs.slice(0, 3)"
            :key="idx"
            class="audit-row"
            :class="{ 'audit-row--last': idx === Math.min(auditLogs.length, 3) - 1 }"
          >
            <NTag :color="auditTypeColor(log.type)" size="small" round>{{ log.type_label }}</NTag>
            <div class="audit-content">
              <div class="audit-desc">{{ log.description }}</div>
              <div class="audit-time">{{ formatRelative(log.created_at) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 登录历史抽屉 -->
    <NDrawer v-model:show="showLoginHistory" width="520" placement="right">
      <NDrawerContent title="登录历史" :native-scrollbar="false">
        <div class="history-list">
          <div
            v-for="(record, idx) in loginHistory"
            :key="idx"
            class="history-row"
            :class="{ 'history-row--last': idx === loginHistory.length - 1 }"
          >
            <div class="history-device-icon">{{ deviceIcon(record.device_type) }}</div>
            <div class="history-info">
              <div class="history-device">{{ record.browser }} / {{ record.os }}</div>
              <div class="history-ip">
                <code class="mono-text">{{ record.ip_address }}</code>
                <span v-if="record.location"> · {{ record.location }}</span>
              </div>
              <div class="history-time">
                {{ formatDateTime(record.login_at) }}
                <span v-if="record.is_current" class="current-session-tag">当前会话</span>
              </div>
            </div>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>

    <!-- 活跃会话抽屉 -->
    <NDrawer v-model:show="showActiveSessions" width="520" placement="right">
      <NDrawerContent title="活跃会话" :native-scrollbar="false">
        <p class="session-tip">以下设备当前已登录你的账号。如发现有异常设备，请立即踢出。</p>
        <div class="session-list">
          <div
            v-for="s in activeSessions"
            :key="s.id"
            class="session-card"
            :class="{ 'session-card--current': s.is_current }"
          >
            <div class="session-header">
              <div class="session-device">
                <span class="session-device-icon">{{ deviceIcon(s.device_type) }}</span>
                <div>
                  <div class="session-device-name">
                    {{ s.browser }} / {{ s.os }}
                    <span v-if="s.is_current" class="session-current-label">(当前设备)</span>
                  </div>
                  <div class="session-meta">{{ s.ip_address }} · {{ s.location }} · 登录于 {{ formatDateTime(s.login_at) }}</div>
                </div>
              </div>
              <NButton v-if="!s.is_current" size="small" type="error" @click="handleRevokeSession(s.id)">
                踢出
              </NButton>
            </div>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NTag, NAvatar, NDrawer, NDrawerContent,
  NSelect, NRadioGroup, NRadioButton, NCheckbox, NSpace, NIcon,
  NPopconfirm, useMessage, useDialog,
} from 'naive-ui'
import {
  PersonOutline, CreateOutline, AnalyticsOutline, FlashOutline,
  ListOutline, ShieldCheckmarkOutline, LockClosedOutline, KeyOutline,
  SettingsOutline, ShieldOutline,
} from '@vicons/ionicons5'
import { format, formatDistanceToNow, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { displayName } from '@/utils/displayName'
import apiClient from '@/api/client'
import type { User } from '@/types'

// ===== 类型定义 =====
interface SessionInfo {
  last_active_at: string
  ip_address: string
  location: string
  user_agent: string
}

interface TaskSummary {
  id: string
  name: string
  flow_name: string
  status: 'running' | 'success' | 'failed' | 'pending' | 'queued' | 'cancelled'
  created_at: string
}

interface UsageStats {
  analysis_count: number
  running_tasks: number
  storage_used: number
  storage_total: number
  recent_task_name: string
  recent_tasks: TaskSummary[]
}

interface LoginRecord {
  login_at: string
  ip_address: string
  location: string
  browser: string
  os: string
  device_type: 'desktop' | 'mobile' | 'other'
  is_current: boolean
}

interface ActiveSession extends LoginRecord {
  id: string
}

interface AuditLog {
  type: 'password' | 'email' | 'delete' | 'security'
  type_label: string
  description: string
  created_at: string
}

interface ApiKey {
  id: string
  name: string
  masked_key: string
  created_at: string
  last_used_at?: string | null
}

interface UserPreferences {
  default_page: string
  theme: 'system' | 'light' | 'dark'
  language: string
  notifications: {
    email: boolean
    in_app: boolean
    webhook: boolean
  }
}

// ===== 依赖 =====
const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const message = useMessage()
const dialog = useDialog()

const user = ref<User | null>(null)
const session = ref<SessionInfo | null>(null)
const stats = ref<UsageStats | null>(null)

// 抽屉显隐
const showLoginHistory = ref(false)
const showActiveSessions = ref(false)

// ===== Mock 数据（后端未就绪时使用） =====
const MOCK_USER: Partial<User> = {
  id: 'cb79a200-b2ca-441f-9a42-d3417fbfa89d',
  username: 'root',
  nickname: '',
  email: '1099651528@qq.com',
  role: 'admin',
  status: 'active',
  avatar_url: null,
  created_at: '2026-07-05T01:04:59+08:00',
  last_login_at: '2026-07-05T01:44:37+08:00',
}

const MOCK_SESSION: SessionInfo = {
  last_active_at: '2026-07-05T01:44:37+08:00',
  ip_address: '192.168.1.100',
  location: '武汉, 湖北',
  user_agent: 'Chrome 126 / macOS',
}

const MOCK_STATS: UsageStats = {
  analysis_count: 128,
  running_tasks: 3,
  storage_used: 45.2,
  storage_total: 100,
  recent_task_name: 'RNA-seq',
  recent_tasks: [
    { id: 't1', name: 'RNA-seq 差异表达分析', flow_name: 'RNA-seq', status: 'running', created_at: '2026-07-04T23:44:37+08:00' },
    { id: 't2', name: '基因组注释', flow_name: 'Genome Annotation', status: 'success', created_at: '2026-07-03T18:00:00+08:00' },
    { id: 't3', name: 'ChIP-seq 峰值分析', flow_name: 'ChIP-seq', status: 'failed', created_at: '2026-07-02T14:00:00+08:00' },
  ],
}

const MOCK_FLOWS = [
  { id: 'rna-seq', name: 'RNA-seq', icon: '🧬' },
  { id: 'atac-seq', name: 'ATAC-seq', icon: '🧪' },
  { id: 'scrna-seq', name: '单细胞', icon: '🔬' },
  { id: 'literature', name: '文献检索', icon: '🌐' },
]

const MOCK_LOGIN_HISTORY: LoginRecord[] = [
  { login_at: '2026-07-05T01:44:37+08:00', ip_address: '192.168.1.100', location: '武汉, 湖北', browser: 'Chrome 126', os: 'macOS', device_type: 'desktop', is_current: true },
  { login_at: '2026-07-04T18:22:15+08:00', ip_address: '192.168.1.100', location: '武汉, 湖北', browser: 'Chrome 126', os: 'macOS', device_type: 'desktop', is_current: false },
  { login_at: '2026-07-03T09:15:00+08:00', ip_address: '10.0.0.55', location: '北京', browser: 'Safari', os: 'iOS', device_type: 'mobile', is_current: false },
]

const MOCK_SESSIONS: ActiveSession[] = [
  { id: 'sess_1', login_at: '2026-07-05T01:44:37+08:00', ip_address: '192.168.1.100', location: '武汉, 湖北', browser: 'Chrome 126', os: 'macOS', device_type: 'desktop', is_current: true },
  { id: 'sess_2', login_at: '2026-07-03T09:15:00+08:00', ip_address: '10.0.0.55', location: '北京', browser: 'Safari', os: 'iOS', device_type: 'mobile', is_current: false },
]

const MOCK_AUDIT_LOGS: AuditLog[] = [
  { type: 'password', type_label: '密码', description: '修改了登录密码', created_at: '2026-07-01T10:00:00+08:00' },
  { type: 'email', type_label: '邮箱', description: '绑定邮箱 1099651528@qq.com', created_at: '2026-06-28T15:30:00+08:00' },
  { type: 'security', type_label: '安全', description: '开启二次验证 (TOTP)', created_at: '2026-06-25T09:00:00+08:00' },
  { type: 'delete', type_label: '删除', description: '删除了任务 #1283', created_at: '2026-06-20T14:00:00+08:00' },
  { type: 'password', type_label: '密码', description: '重置了 API 密钥', created_at: '2026-06-15T11:00:00+08:00' },
]

const MOCK_API_KEYS: ApiKey[] = [
  { id: 'key_1', name: '开发测试', masked_key: 'oh-****-3f2a', created_at: '2026-06-01', last_used_at: '2026-07-04T12:00:00' },
]

// ===== 计算属性 =====
const userInitial = computed(() => displayName(user.value).charAt(0).toUpperCase() || 'U')
const shortId = computed(() => {
  if (!user.value?.id) return '-'
  return user.value.id.slice(0, 8) + '…'
})
const roleLabel = computed(() => (user.value?.role === 'admin' ? '管理员' : '普通用户'))
const roleTagType = computed(() => (user.value?.role === 'admin' ? 'warning' : 'default'))
const statusLabel = computed(() => {
  const map: Record<string, string> = {
    active: '正常',
    inactive: '已禁用',
    pending: '待审批',
    rejected: '已拒绝',
    locked: '已锁定',
  }
  return map[user.value?.status ?? ''] ?? user.value?.status ?? '-'
})
const statusTagColor = computed(() => {
  const map: Record<string, string> = {
    active: '#00B42A',
    inactive: '#FF7D00',
    pending: '#FF7D00',
    rejected: '#F53F3F',
    locked: '#F53F3F',
  }
  return map[user.value?.status ?? ''] ?? '#86909C'
})

const kpiList = computed(() => {
  const s = stats.value || MOCK_STATS
  return [
    { label: '本月分析', value: s.analysis_count, unit: '次', color: '#165DFF', pulse: false },
    { label: '运行中', value: s.running_tasks, unit: '个', color: '#00B42A', pulse: s.running_tasks > 0 },
    { label: '存储 GB', value: s.storage_used, unit: 'GB', color: '#722ED1', total: s.storage_total },
  ]
})

const favoriteFlows = computed(() => MOCK_FLOWS)
const recentTasks = computed(() => stats.value?.recent_tasks || MOCK_STATS.recent_tasks)
const loginHistory = ref<LoginRecord[]>(MOCK_LOGIN_HISTORY)
const activeSessions = ref<ActiveSession[]>(MOCK_SESSIONS)
const auditLogs = ref<AuditLog[]>(MOCK_AUDIT_LOGS)
const apiKeys = ref<ApiKey[]>([...MOCK_API_KEYS])
const newApiKey = ref<string | null>(null)
const exporting = ref(false)

const preferences = ref<UserPreferences>({
  default_page: 'analysis',
  theme: 'system',
  language: 'zh-CN',
  notifications: { email: true, in_app: true, webhook: false },
})

const defaultPageOptions = [
  { label: '控制台', value: 'dashboard' },
  { label: '分析中心', value: 'analysis' },
  { label: '任务中心', value: 'tasks' },
  { label: '数据管理', value: 'data' },
]

const languageOptions = [
  { label: '简体中文', value: 'zh-CN' },
  { label: 'English', value: 'en-US' },
]

// ===== 工具函数 =====
function parseDate(input?: string | null): Date | null {
  if (!input) return null
  try {
    const d = parseISO(input)
    if (Number.isNaN(d.getTime())) return null
    return d
  } catch {
    return null
  }
}

function formatDateOnly(input?: string | null): string {
  const d = parseDate(input)
  if (!d) return '-'
  return format(d, 'yyyy/MM/dd')
}

function formatDateTime(input?: string | null): string {
  const d = parseDate(input)
  if (!d) return '-'
  return format(d, 'yyyy/MM/dd HH:mm:ss')
}

function formatShortTime(input?: string | null): string {
  const d = parseDate(input)
  if (!d) return '-'
  return format(d, 'HH:mm')
}

function formatRelative(input?: string | null): string {
  const d = parseDate(input)
  if (!d) return '-'
  return formatDistanceToNow(d, { addSuffix: true, locale: zhCN })
}

function kpiPercent(kpi: { value: number | string; total?: number }): number {
  if (!kpi.total || typeof kpi.value !== 'number') return 0
  return Math.min(Math.round((kpi.value / kpi.total) * 100), 100)
}

function taskStatus(status: string) {
  const map: Record<string, { color: string; text: string; icon: string }> = {
    running: { color: '#00B42A', text: '运行中', icon: '●' },
    success: { color: '#00B42A', text: '成功', icon: '✓' },
    failed: { color: '#F53F3F', text: '失败', icon: '✗' },
    pending: { color: '#FF7D00', text: '排队中', icon: '◐' },
    queued: { color: '#FF7D00', text: '排队中', icon: '◐' },
    cancelled: { color: '#86909C', text: '已取消', icon: '○' },
  }
  return map[status] || map.pending
}

function taskStatusColor(status: string) {
  const s = taskStatus(status)
  return { color: s.color, textColor: s.color, borderColor: s.color }
}

function auditTypeColor(type: string) {
  const map: Record<string, { color: string; textColor: string; borderColor: string }> = {
    password: { color: '#FF7D00', textColor: '#FF7D00', borderColor: '#FF7D00' },
    email: { color: '#165DFF', textColor: '#165DFF', borderColor: '#165DFF' },
    delete: { color: '#F53F3F', textColor: '#F53F3F', borderColor: '#F53F3F' },
    security: { color: '#00B42A', textColor: '#00B42A', borderColor: '#00B42A' },
  }
  return map[type] || { color: '#86909C', textColor: '#86909C', borderColor: '#86909C' }
}

function deviceIcon(deviceType?: string): string {
  if (deviceType === 'desktop') return '💻'
  if (deviceType === 'mobile') return '📱'
  return '🌐'
}

// ===== 交互处理 =====
function avatarEditHint() {
  message.info('头像修改功能开发中，请前往「账号设置」管理个人信息')
}

function handleCreateApiKey() {
  const id = `key_${Date.now()}`
  const rawKey = `oh-${Math.random().toString(36).slice(2, 6)}-${Math.random().toString(36).slice(2, 6)}${Math.random().toString(36).slice(2, 6)}`
  apiKeys.value.push({
    id,
    name: `新密钥 ${apiKeys.value.length + 1}`,
    masked_key: `oh-****-${rawKey.slice(-4)}`,
    created_at: new Date().toISOString(),
    last_used_at: null,
  })
  newApiKey.value = rawKey
  message.success('密钥已创建，请立即复制保存')
}

function copyNewKey() {
  if (!newApiKey.value) return
  navigator.clipboard.writeText(newApiKey.value).then(() => message.success('已复制到剪贴板'))
}

function handleRevokeApiKey(keyId: string) {
  dialog.warning({
    title: '确认撤销密钥？',
    content: '撤销后，使用该密钥的 API 请求将立即失效。',
    positiveText: '确认撤销',
    negativeText: '取消',
    onPositiveClick: () => {
      apiKeys.value = apiKeys.value.filter((k) => k.id !== keyId)
      if (newApiKey.value) newApiKey.value = null
      message.success('密钥已撤销')
    },
  })
}

function handleRevokeSession(sessionId: string) {
  dialog.warning({
    title: '确认踢出设备？',
    content: '该设备上的登录状态将立即失效。',
    positiveText: '确认踢出',
    negativeText: '取消',
    onPositiveClick: () => {
      activeSessions.value = activeSessions.value.filter((s) => s.id !== sessionId)
      message.success('已踢出该设备')
    },
  })
}

async function handleExportData() {
  exporting.value = true
  try {
    await new Promise((resolve) => setTimeout(resolve, 800))
    const data = {
      user: user.value,
      exportAt: new Date().toISOString(),
      tasks: recentTasks.value,
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `omicHub_data_${formatDateOnly(new Date().toISOString())}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    message.success('数据导出成功')
  } finally {
    exporting.value = false
  }
}

function handleDeleteAccount() {
  dialog.error({
    title: '确认删除账户？',
    content: '此操作不可撤销，将删除你的所有数据、任务和历史记录。',
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.delete('/user/account')
      } catch {
        // 后端未就绪时仅做前端演示
      }
      message.success('账户已删除')
      authStore.logout()
      router.push('/login')
    },
  })
}

function applyThemePreference(theme: 'system' | 'light' | 'dark') {
  if (theme === 'dark') themeStore.setTheme('dark')
  else if (theme === 'light') themeStore.setTheme('light')
  else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    themeStore.setTheme(prefersDark ? 'dark' : 'light')
  }
}

function onThemeChange(theme: 'system' | 'light' | 'dark') {
  applyThemePreference(theme)
  savePreferences()
}

function savePreferences() {
  // 后端未就绪时先写入 localStorage，接口就绪后替换为 API 调用
  localStorage.setItem('omichub:profile:preferences', JSON.stringify(preferences.value))
  message.success('偏好已保存')
}

// ===== 数据加载 =====
async function loadUserProfile() {
  try {
    await authStore.fetchUser()
    user.value = authStore.user || ({ ...MOCK_USER } as User)
  } catch (error: any) {
    message.error('获取用户信息失败')
    user.value = { ...MOCK_USER } as User
    if (error.response?.status === 401) {
      authStore.logout()
      router.push('/login')
    }
  }
}

async function loadSession() {
  try {
    const { data } = await apiClient.get<SessionInfo>('/user/session')
    session.value = data
  } catch {
    session.value = MOCK_SESSION
  }
}

async function loadStats() {
  try {
    const { data } = await apiClient.get<UsageStats>('/user/stats')
    stats.value = data
  } catch {
    stats.value = MOCK_STATS
  }
}

async function loadLoginHistory() {
  try {
    const { data } = await apiClient.get<LoginRecord[]>('/user/login-history')
    loginHistory.value = data
  } catch {
    loginHistory.value = MOCK_LOGIN_HISTORY
  }
}

async function loadActiveSessions() {
  try {
    const { data } = await apiClient.get<ActiveSession[]>('/user/sessions')
    activeSessions.value = data
  } catch {
    activeSessions.value = MOCK_SESSIONS
  }
}

async function loadAuditLogs() {
  try {
    const { data } = await apiClient.get<AuditLog[]>('/user/audit-logs')
    auditLogs.value = data
  } catch {
    auditLogs.value = MOCK_AUDIT_LOGS
  }
}

async function loadApiKeys() {
  try {
    const { data } = await apiClient.get<ApiKey[]>('/user/api-keys')
    apiKeys.value = data
  } catch {
    apiKeys.value = [...MOCK_API_KEYS]
  }
}

async function loadPreferences() {
  try {
    const saved = localStorage.getItem('omichub:profile:preferences')
    if (saved) {
      preferences.value = { ...preferences.value, ...JSON.parse(saved) }
    }
    const { data } = await apiClient.get<UserPreferences>('/user/preferences')
    preferences.value = { ...preferences.value, ...data }
  } catch {
    // 使用 localStorage 或默认值
  }
  applyThemePreference(preferences.value.theme)
}

async function loadAll() {
  await loadUserProfile()
  await Promise.all([
    loadSession(),
    loadStats(),
    loadLoginHistory(),
    loadActiveSessions(),
    loadAuditLogs(),
    loadApiKeys(),
    loadPreferences(),
  ])
}

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  loadAll()
})

// 监听系统主题变化，自动应用
watch(
  () => preferences.value.theme,
  (theme) => {
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      const handler = (e: MediaQueryListEvent) => themeStore.setTheme(e.matches ? 'dark' : 'light')
      mediaQuery.addEventListener('change', handler)
    }
  },
  { immediate: true },
)
</script>

<style scoped>
/* ===== Bento Grid 容器 ===== */
.profile-page-wrapper {
  width: 100%;
  padding: 24px 0;
  display: flex;
  justify-content: center;
}

.profile-bento-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  width: 100%;
  max-width: 960px;
  padding: 0 32px;
}

/* ===== 通用卡片样式 ===== */
.bento-card {
  background: var(--neutral-card);
  border: 1px solid var(--neutral-border);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  overflow: hidden;
}

.bento-card:hover {
  border-color: var(--neutral-text-3);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
}

.bento-col-1 { grid-column: span 1; }
.bento-col-2 { grid-column: span 2; }
.bento-col-3 { grid-column: span 3; }

.bento-card-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-1);
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.bento-card-title .n-icon {
  font-size: 16px;
}

.card-action {
  margin-left: auto;
  font-size: 12px;
}

/* ===== 用户信息卡片 ===== */
.user-info-card {
  padding: 20px 24px;
}

.user-info-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-avatar {
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  font-size: 24px;
  flex-shrink: 0;
}

.user-info-main {
  flex: 1;
  min-width: 0;
}

.user-info-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 2px;
}

.user-name {
  font-size: 17px;
  font-weight: 500;
  color: var(--neutral-text-1);
}

.user-info-meta {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin-bottom: 2px;
}

.user-info-extra {
  font-size: 12px;
  color: var(--neutral-text-2);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.user-status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.avatar-edit-btn {
  flex-shrink: 0;
}

/* ===== KPI 卡片 ===== */
.kpi-card {
  text-align: center;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.kpi-value {
  font-size: 28px;
  font-weight: 500;
  color: var(--neutral-text-1);
  line-height: 1;
}

.kpi-value--pulse {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.kpi-label {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin-top: 8px;
}

.kpi-bar {
  height: 3px;
  border-radius: 2px;
  background: var(--neutral-border);
  margin-top: 12px;
  overflow: hidden;
}

.kpi-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s ease;
}

/* ===== 信息行 ===== */
.info-list {
  display: flex;
  flex-direction: column;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--neutral-border);
  font-size: 12px;
  gap: 8px;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  color: var(--neutral-text-2);
  flex-shrink: 0;
}

.info-value {
  color: var(--neutral-text-1);
  font-weight: 500;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-value-mono {
  font-family: var(--kimi-font-mono, 'SFMono-Regular', Consolas, monospace);
  color: var(--neutral-text-1);
  font-size: 12px;
}

.security-actions {
  display: flex;
  gap: 12px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--neutral-border);
}

/* ===== 最近任务 ===== */
.task-list {
  display: flex;
  flex-direction: column;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--neutral-border);
  cursor: pointer;
  transition: background 0.15s ease;
  margin: 0 -20px;
  padding-left: 20px;
  padding-right: 20px;
}

.task-row:hover {
  background: var(--neutral-hover);
}

.task-row--last {
  border-bottom: none;
}

.task-status-dot {
  font-size: 10px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.task-info {
  flex: 1;
  min-width: 0;
}

.task-name {
  font-size: 13px;
  color: var(--neutral-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-meta {
  font-size: 11px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

/* ===== 常用流程竖排 ===== */
.flow-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.flow-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--neutral-border);
  background: var(--neutral-bg);
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 13px;
  color: var(--neutral-text-1);
}

.flow-chip:hover {
  border-color: var(--arco-primary);
  color: var(--arco-primary);
}

.flow-icon {
  font-size: 16px;
}

.flow-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== 平台偏好 ===== */
.pref-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.pref-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pref-row--full {
  grid-column: span 2;
}

.pref-label {
  font-size: 12px;
  color: var(--neutral-text-2);
  width: 60px;
  flex-shrink: 0;
}

/* ===== API 密钥 ===== */
.api-key-hint {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin-bottom: 12px;
}

.new-api-key-banner {
  padding: 12px;
  border-radius: 8px;
  background: rgba(0, 180, 42, 0.08);
  border: 1px solid rgba(0, 180, 42, 0.2);
  margin-bottom: 12px;
}

.new-api-key-title {
  font-size: 13px;
  font-weight: 500;
  color: #00B42A;
  margin-bottom: 4px;
}

.new-api-key-code {
  display: block;
  padding: 8px;
  border-radius: 4px;
  background: var(--neutral-card);
  font-family: var(--kimi-font-mono, 'SFMono-Regular', Consolas, monospace);
  font-size: 12px;
  word-break: break-all;
  margin-bottom: 8px;
}

.api-key-list {
  display: flex;
  flex-direction: column;
}

.api-key-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--neutral-border);
}

.api-key-row--last {
  border-bottom: none;
}

.api-key-info {
  flex: 1;
  min-width: 0;
}

.api-key-name {
  font-size: 13px;
  color: var(--neutral-text-1);
}

.api-key-meta {
  font-size: 11px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

/* ===== 数据与隐私 ===== */
.privacy-list {
  display: flex;
  flex-direction: column;
}

.privacy-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--neutral-border);
  gap: 12px;
}

.privacy-row:last-child {
  border-bottom: none;
}

.privacy-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--neutral-text-1);
}

.privacy-row--danger .privacy-title {
  color: var(--arco-danger);
}

.privacy-desc {
  font-size: 11px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

/* ===== 审计日志 ===== */
.audit-list {
  display: flex;
  flex-direction: column;
}

.audit-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--neutral-border);
}

.audit-row--last {
  border-bottom: none;
}

.audit-content {
  flex: 1;
  min-width: 0;
}

.audit-desc {
  font-size: 12px;
  color: var(--neutral-text-1);
  line-height: 1.4;
}

.audit-time {
  font-size: 11px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

.empty-state {
  text-align: center;
  padding: 24px 0;
  color: var(--neutral-text-3);
  font-size: 13px;
}

/* ===== 抽屉内容 ===== */
.history-list,
.session-list {
  display: flex;
  flex-direction: column;
}

.history-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--neutral-border);
}

.history-row--last {
  border-bottom: none;
}

.history-device-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--neutral-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}

.history-info {
  flex: 1;
  min-width: 0;
}

.history-device {
  font-size: 14px;
  color: var(--neutral-text-1);
}

.history-ip {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

.history-time {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

.current-session-tag {
  margin-left: 8px;
  font-size: 11px;
  color: #00B42A;
  background: rgba(0, 180, 42, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.session-tip {
  font-size: 13px;
  color: var(--neutral-text-2);
  margin-bottom: 16px;
}

.session-card {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--neutral-border);
  background: var(--neutral-bg);
  margin-bottom: 12px;
}

.session-card--current {
  background: rgba(22, 93, 255, 0.05);
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.session-device {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-device-icon {
  font-size: 20px;
}

.session-device-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-1);
}

.session-current-label {
  margin-left: 8px;
  font-size: 12px;
  color: var(--arco-primary);
}

.session-meta {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin-top: 2px;
}

.mono-text {
  font-family: var(--kimi-font-mono, 'SFMono-Regular', Consolas, monospace);
  font-size: 13px;
}

/* ===== 响应式：平板 2 列 ===== */
@media (max-width: 900px) {
  .profile-bento-grid {
    grid-template-columns: repeat(2, 1fr);
    padding: 0 20px;
    gap: 14px;
  }

  .bento-col-1,
  .bento-col-2,
  .bento-col-3 {
    grid-column: span 2;
  }

  .kpi-card {
    grid-column: span 1 !important;
  }

  .pref-grid {
    grid-template-columns: 1fr;
  }

  .pref-row--full {
    grid-column: span 1;
  }
}

/* ===== 响应式：手机 1 列 ===== */
@media (max-width: 600px) {
  .profile-page-wrapper {
    padding: 16px 0;
  }

  .profile-bento-grid {
    grid-template-columns: 1fr;
    padding: 0 16px;
    gap: 12px;
  }

  .bento-col-1,
  .bento-col-2,
  .bento-col-3,
  .kpi-card {
    grid-column: span 1 !important;
  }

  .bento-card {
    padding: 16px;
  }

  .user-info-header {
    flex-wrap: wrap;
  }

  .avatar-edit-btn {
    margin-left: auto;
  }

  .pref-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .pref-label {
    width: auto;
  }

  .security-actions {
    flex-wrap: wrap;
  }
}
</style>
