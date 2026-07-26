<template>
  <main class="profile-page-wrapper" :aria-busy="isLoading">
    <div class="profile-content">
      <PageHeader title="个人中心" subtitle="查看工作概览，管理个人偏好与账户安全。">
        <template #actions>
          <NButton secondary :loading="isRefreshing" @click="refreshProfile">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            刷新资料
          </NButton>
        </template>
      </PageHeader>

      <NSpin :show="isLoading">
        <section class="profile-grid" aria-label="个人中心概览">
          <NCard :bordered="false" class="arco-card profile-card profile-card--hero">
            <div class="profile-hero">
              <NAvatar round :size="64" :src="user?.avatar_url || undefined" class="profile-avatar">
                {{ userInitial }}
              </NAvatar>
              <div class="profile-identity">
                <div class="profile-name-row">
                  <h2>{{ displayName(user) }}</h2>
                  <NTag :type="user?.role === 'admin' ? 'warning' : 'default'" size="small" round>
                    {{ user?.role === 'admin' ? '管理员' : '普通用户' }}
                  </NTag>
                  <NTag :type="statusTagType" size="small" round>{{ statusLabel }}</NTag>
                </div>
                <p>{{ user?.email || '未设置邮箱' }}</p>
                <span>ID: {{ shortId }} · 创建于 {{ formatDateOnly(user?.created_at) }}</span>
              </div>
              <NButton text size="small" @click="router.push('/settings')">
                <template #icon><NIcon><CreateOutline /></NIcon></template>
                编辑资料
              </NButton>
            </div>
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card profile-card--wide">
            <template #header><CardTitle :icon="ListOutline" title="最近任务" /></template>
            <template #header-extra><NButton text size="small" @click="router.push('/tasks')">查看全部</NButton></template>
            <div class="task-summary" aria-label="任务与存储概览">
              <div v-for="stat in statistics" :key="stat.label" class="task-summary-item">
                <span>{{ stat.label }}</span>
                <strong :style="{ color: stat.color }">{{ stat.value }}<em>{{ stat.unit }}</em></strong>
                <NProgress v-if="stat.total" type="line" :percentage="percentage(stat.value, stat.total)" :show-indicator="false" :color="stat.color" />
              </div>
            </div>
            <div v-if="recentTasks.length" class="task-list">
              <button v-for="task in recentTasks" :key="task.id" type="button" class="task-row" @click="router.push(`/tasks/${task.id}`)">
                <span class="task-status" :class="`task-status--${task.status}`">{{ taskStatus(task.status) }}</span>
                <span class="task-copy"><strong>{{ task.name || task.flow_id }}</strong><small>{{ task.flow_id }} · {{ formatRelative(task.created_at) }}</small></span>
                <NTag :type="taskTagType(task.status)" size="small" round>{{ taskStatus(task.status) }}</NTag>
              </button>
            </div>
            <NEmpty v-else description="还没有分析任务，提交流程后会在这里显示。"><template #extra><NButton size="small" type="primary" @click="router.push('/flows')">浏览流程</NButton></template></NEmpty>
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card">
            <template #header><CardTitle :icon="FlashOutline" title="常用流程" /></template>
            <div class="quick-flow-list">
              <NButton v-for="flow in favoriteFlows" :key="flow.id" quaternary size="small" class="quick-flow" @click="router.push(`/flows/${flow.id}/submit`)">
                <span>{{ flow.icon }}</span>{{ flow.name }}
              </NButton>
            </div>
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card">
            <template #header><CardTitle :icon="ShieldCheckmarkOutline" title="安全与登录" /></template>
            <div class="detail-list">
              <div><span>最后登录</span><strong>{{ formatDateTime(user?.last_login_at) }}</strong></div>
              <div><span>二次验证</span><NTag :type="twoFactorEnabled ? 'success' : 'warning'" size="small" round>{{ twoFactorEnabled ? '已开启' : '未开启' }}</NTag></div>
              <div><span>账户状态</span><NTag :type="statusTagType" size="small" round>{{ statusLabel }}</NTag></div>
            </div>
            <NButton block secondary @click="router.push('/settings')">管理安全设置</NButton>
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card">
            <template #header><CardTitle :icon="LockClosedOutline" title="审计记录" /></template>
            <div v-if="auditLogs.length" class="audit-list">
              <div v-for="log in auditLogs" :key="`${log.created_at}-${log.description}`" class="audit-row">
                <NTag :type="auditTagType(log.type)" size="small" round>{{ log.type_label }}</NTag>
                <span><strong>{{ log.description }}</strong><small>{{ formatRelative(log.created_at) }}</small></span>
              </div>
            </div>
            <NEmpty v-else size="small" description="暂无可显示的审计记录" />
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card profile-card--wide">
            <template #header><CardTitle :icon="ListOutline" title="我的记忆" /></template>
            <template #header-extra>
              <NButton v-if="memories.length" text type="error" size="small" @click="clearMemories">清空全部</NButton>
            </template>
            <p class="memory-hint">仅保存你允许 Agent 跨会话使用的研究偏好与项目事实；可随时删除。</p>
            <div v-if="memories.length" class="memory-list">
              <div v-for="memory in memories" :key="memory.id" class="memory-row">
                <span><NTag size="small" round>{{ memoryScopeLabel(memory.scope) }}</NTag></span>
                <div><strong>{{ memory.content }}</strong><small>{{ memory.agent_id || '全局记忆' }} · {{ formatRelative(memory.updated_at) }}</small></div>
                <NButton text type="error" size="small" @click="deleteMemory(memory.id)">删除</NButton>
              </div>
            </div>
            <NEmpty v-else size="small" description="暂无跨会话记忆。Agent 在你明确授权或提供稳定研究背景时才会保存。" />
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card profile-card--wide">
            <template #header><CardTitle :icon="SettingsOutline" title="平台偏好" /></template>
            <NGrid cols="1 m:2" responsive="screen" :x-gap="20" :y-gap="20">
              <NGridItem><label class="field-label">默认首页<NSelect v-model:value="preferences.default_page" :options="defaultPageOptions" :loading="savingPreferences" @update:value="savePreferences" /></label></NGridItem>
              <NGridItem><label class="field-label">语言<NSelect v-model:value="preferences.language" :options="languageOptions" :loading="savingPreferences" @update:value="savePreferences" /></label></NGridItem>
              <NGridItem span="1 m:2"><span class="field-label">主题</span><NRadioGroup v-model:value="preferences.theme" size="small" @update:value="onThemeChange"><NRadioButton value="system">跟随系统</NRadioButton><NRadioButton value="light">亮色</NRadioButton><NRadioButton value="dark">深色</NRadioButton></NRadioGroup></NGridItem>
              <NGridItem span="1 m:2"><span class="field-label">通知渠道</span><NSpace><NCheckbox v-model:checked="preferences.notifications.email" @update:checked="savePreferences">邮件</NCheckbox><NCheckbox v-model:checked="preferences.notifications.in_app" @update:checked="savePreferences">站内消息</NCheckbox><NCheckbox v-model:checked="preferences.notifications.webhook" @update:checked="savePreferences">Webhook</NCheckbox></NSpace></NGridItem>
            </NGrid>
          </NCard>

          <NCard :bordered="false" class="arco-card profile-card profile-card--wide">
            <template #header><CardTitle :icon="ShieldOutline" title="数据与隐私" /></template>
            <div class="privacy-row"><div><strong>导出个人数据</strong><p>下载账户资料、已加载的任务清单与平台偏好。</p></div><NButton :loading="exporting" @click="exportProfileData">导出数据</NButton></div>
            <div class="privacy-row"><div><strong>账户资料</strong><p>修改昵称、邮箱、头像和登录密码。</p></div><NButton secondary @click="router.push('/settings')">前往设置</NButton></div>
          </NCard>

        </section>
      </NSpin>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NAvatar, NButton, NCard, NCheckbox, NEmpty, NGrid, NGridItem, NIcon, NProgress, NRadioButton, NRadioGroup, NSelect, NSpace, NSpin, NTag, useMessage } from 'naive-ui'
import { CreateOutline, FlashOutline, ListOutline, LockClosedOutline, RefreshOutline, SettingsOutline, ShieldCheckmarkOutline, ShieldOutline } from '@vicons/ionicons5'
import { format, formatDistanceToNow, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { displayName } from '@/utils/displayName'
import apiClient from '@/api/client'
import type { Task, User } from '@/types'
import PageHeader from '@/components/PageHeader.vue'

interface AuditLog { type: string; type_label: string; description: string; created_at: string }
interface AgentMemory { id: string; agent_id: string | null; scope: 'profile' | 'project' | 'preference' | 'summary'; content: string; updated_at: string | null }
interface UserPreferences { default_page: string; theme: 'system' | 'light' | 'dark'; language: string; notifications: { email: boolean; in_app: boolean; webhook: boolean } }

const CardTitle = defineComponent({ props: { icon: { type: Object, required: true }, title: { type: String, required: true } }, setup: props => () => h(NSpace, { align: 'center', size: 8 }, { default: () => [h(NIcon, { size: 18 }, { default: () => h(props.icon as never) }), h('span', props.title)] }) })
const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const message = useMessage()
const tasks = ref<Task[]>([])
const auditLogs = ref<AuditLog[]>([])
const memories = ref<AgentMemory[]>([])
const isLoading = ref(true)
const isRefreshing = ref(false)
const exporting = ref(false)
const savingPreferences = ref(false)
const twoFactorEnabled = ref(false)
const preferences = ref<UserPreferences>({ default_page: 'dashboard', theme: 'system', language: 'zh-CN', notifications: { email: true, in_app: true, webhook: false } })
const favoriteFlows = [{ id: 'rna-seq', name: 'RNA-seq', icon: '🧬' }, { id: 'atac-seq', name: 'ATAC-seq', icon: '🧪' }, { id: 'scrna-seq', name: '单细胞', icon: '🔬' }, { id: 'literature', name: '文献检索', icon: '🌐' }]
const defaultPageOptions = [{ label: '控制台', value: 'dashboard' }, { label: '分析中心', value: 'analysis' }, { label: '任务中心', value: 'tasks' }, { label: '数据管理', value: 'data' }]
const languageOptions = [{ label: '简体中文', value: 'zh-CN' }, { label: 'English', value: 'en-US' }]
const user = computed(() => authStore.user)
const userInitial = computed(() => displayName(user.value).charAt(0).toUpperCase() || 'U')
const shortId = computed(() => user.value?.id ? `${user.value.id.slice(0, 8)}…` : '-')
const statusLabel = computed(() => {
  const labels: Record<string, string> = { active: '正常', inactive: '已禁用', locked: '已锁定' }
  return labels[user.value?.status || ''] || '未知'
})
const statusTagType = computed(() => user.value?.status === 'active' ? 'success' : user.value?.status === 'locked' ? 'error' : 'warning')
const recentTasks = computed(() => tasks.value.slice(0, 5))
const storageUsed = computed(() => Number(user.value?.used_storage || 0) / 1024 ** 3)
const storageQuota = computed(() => Number(user.value?.storage_quota || 0) / 1024 ** 3)
const statistics = computed(() => { const month = new Date().getMonth(); const analyses = tasks.value.filter(task => parseDate(task.created_at)?.getMonth() === month).length; const running = tasks.value.filter(task => ['pending', 'queued', 'running'].includes(task.status)).length; return [{ label: '本月分析', value: analyses, unit: '次', color: 'var(--arco-primary)' }, { label: '运行中', value: running, unit: '个', color: 'var(--arco-success)' }, { label: '存储空间', value: storageUsed.value.toFixed(1), unit: 'GB', total: storageQuota.value, color: 'var(--icon-visualization)' }] })

function parseDate(value?: string | null) { if (!value) return null; const date = parseISO(value); return Number.isNaN(date.getTime()) ? null : date }
function formatDateOnly(value?: string | null) { const date = parseDate(value); return date ? format(date, 'yyyy/MM/dd') : '-' }
function formatDateTime(value?: string | null) { const date = parseDate(value); return date ? format(date, 'yyyy/MM/dd HH:mm') : '暂无登录记录' }
function formatRelative(value?: string | null) { const date = parseDate(value); return date ? formatDistanceToNow(date, { addSuffix: true, locale: zhCN }) : '-' }
function percentage(value: string | number, total: number) { return total > 0 ? Math.min(Math.round((Number(value) / total) * 100), 100) : 0 }
function taskStatus(status: string) { return ({ pending: '等待中', queued: '排队中', running: '运行中', success: '已完成', failed: '失败', cancelled: '已取消' }[status] || status) }
function taskTagType(status: string) { return ({ success: 'success', running: 'success', failed: 'error', pending: 'warning', queued: 'warning', cancelled: 'default' }[status] || 'default') as 'success' | 'error' | 'warning' | 'default' }
function auditTagType(type: string) { return ({ password: 'warning', security: 'success', delete: 'error', email: 'default' }[type] || 'default') as 'success' | 'error' | 'warning' | 'default' }
function memoryScopeLabel(scope: AgentMemory['scope']) { return ({ profile: '用户画像', project: '项目', preference: '偏好', summary: '摘要' }[scope]) }
function applyTheme(theme: UserPreferences['theme']) { const resolved = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme; themeStore.setTheme(resolved) }

async function loadProfile() { await authStore.fetchUser(); const saved = user.value?.preferences?.profile; if (saved && typeof saved === 'object') preferences.value = { ...preferences.value, ...(saved as Partial<UserPreferences>), notifications: { ...preferences.value.notifications, ...((saved as Partial<UserPreferences>).notifications || {}) } }; applyTheme(preferences.value.theme) }
async function loadTasks() { const { data } = await apiClient.get<{ items: Task[] }>('/tasks'); tasks.value = data.items || [] }
async function loadAuditLogs() { const { data } = await apiClient.get<AuditLog[]>('/users/me/audit-logs', { params: { limit: 5 } }); auditLogs.value = data }
async function loadMemories() { const { data } = await apiClient.get<AgentMemory[]>('/users/me/memories'); memories.value = data }
async function loadSecurity() { twoFactorEnabled.value = (await authStore.fetch2FAStatus()).enabled }
async function loadAll(refresh = false) { refresh ? isRefreshing.value = true : isLoading.value = true; try { await Promise.all([loadProfile(), loadTasks(), loadAuditLogs(), loadMemories(), loadSecurity()]) } catch (error: any) { if (error.response?.status === 401) { authStore.logout(); await router.push('/login') } else message.error(error.response?.data?.detail || '个人中心加载失败，请稍后重试') } finally { isLoading.value = false; isRefreshing.value = false } }
async function deleteMemory(memoryId: string) { try { await apiClient.delete(`/users/me/memories/${memoryId}`); memories.value = memories.value.filter(memory => memory.id !== memoryId); message.success('记忆已删除') } catch (error: any) { message.error(error.response?.data?.detail || '删除记忆失败') } }
async function clearMemories() { if (!window.confirm('确定清空全部跨会话记忆吗？此操作不会影响聊天记录。')) return; try { await apiClient.delete('/users/me/memories'); memories.value = []; message.success('已清空全部记忆') } catch (error: any) { message.error(error.response?.data?.detail || '清空记忆失败') } }
async function refreshProfile() { await loadAll(true); message.success('个人中心已刷新') }
async function savePreferences() { if (!user.value) return; savingPreferences.value = true; try { await apiClient.put(`/users/${user.value.id}`, { preferences: { ...(user.value.preferences || {}), profile: preferences.value } }); await authStore.fetchUser(); message.success('偏好已保存') } catch (error: any) { message.error(error.response?.data?.detail || '保存偏好失败') } finally { savingPreferences.value = false } }
async function onThemeChange(theme: UserPreferences['theme']) { applyTheme(theme); await savePreferences() }
async function exportProfileData() { exporting.value = true; try { const payload = { exported_at: new Date().toISOString(), user: user.value, preferences: preferences.value, tasks: tasks.value }; const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = `omichub-profile-${format(new Date(), 'yyyyMMdd')}.json`; link.click(); URL.revokeObjectURL(url); message.success('个人数据已导出') } finally { exporting.value = false } }
let mediaQuery: MediaQueryList | null = null
let handleSystemThemeChange: ((event: MediaQueryListEvent) => void) | null = null
watch(() => preferences.value.theme, theme => { if (mediaQuery && handleSystemThemeChange) mediaQuery.removeEventListener('change', handleSystemThemeChange); if (theme === 'system') { mediaQuery = window.matchMedia('(prefers-color-scheme: dark)'); handleSystemThemeChange = event => themeStore.setTheme(event.matches ? 'dark' : 'light'); mediaQuery.addEventListener('change', handleSystemThemeChange) } }, { immediate: true })
onMounted(() => { if (!authStore.isLoggedIn) router.push('/login'); else loadAll() })
onUnmounted(() => { if (mediaQuery && handleSystemThemeChange) mediaQuery.removeEventListener('change', handleSystemThemeChange) })
</script>

<style scoped>
.profile-page-wrapper { min-height: 100%; padding: 32px 0 48px; background: var(--neutral-bg); }
.profile-content { width: 100%; max-width: 1024px; margin: 0 auto; padding: 0 24px; }
.profile-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.profile-card { min-width: 0; padding: 32px; }
.profile-card--hero, .profile-card--wide { grid-column: span 3; }
.profile-hero, .profile-name-row, .detail-list > div, .privacy-row, .task-row, .audit-row { display: flex; align-items: center; }
.profile-hero { gap: 20px; }.profile-identity { min-width: 0; flex: 1; }.profile-name-row { gap: 8px; flex-wrap: wrap; }.profile-name-row h2 { margin: 0; color: var(--neutral-text-1); font-size: 20px; letter-spacing: -0.015em; }.profile-identity p, .profile-identity span, .privacy-row p, .task-copy small, .audit-row small { display: block; margin: 4px 0 0; color: var(--neutral-text-3); font-size: 13px; }.profile-avatar { flex: 0 0 auto; background: var(--arco-primary-light); color: var(--arco-primary); font-size: 28px; }
.task-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: -4px 0 20px; border: 1px solid var(--neutral-border); border-radius: var(--radius-sm); background: var(--neutral-bg); }.task-summary-item { min-width: 0; padding: 14px 16px; border-right: 1px solid var(--neutral-border); }.task-summary-item:last-child { border-right: 0; }.task-summary-item > span { display: block; color: var(--neutral-text-3); font-size: 12px; line-height: 18px; }.task-summary-item strong { display: block; margin-top: 4px; font-size: 22px; font-weight: 600; line-height: 28px; letter-spacing: -0.015em; }.task-summary-item em { margin-left: 4px; color: var(--neutral-text-3); font-size: 12px; font-style: normal; font-weight: 400; letter-spacing: 0; }
.task-list, .quick-flow-list, .detail-list, .audit-list, .memory-list { display: flex; flex-direction: column; }.task-row { width: calc(100% + 64px); gap: 12px; margin: 0 -32px; padding: 12px 32px; border: 0; border-bottom: 1px solid var(--neutral-border); background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; transition: background-color 120ms ease-out, transform 120ms ease-out; }.task-row:hover { background: var(--neutral-hover); }.task-row:active { transform: scale(.995); }.task-status { width: 52px; color: var(--neutral-text-3); font-size: 12px; }.task-status--running { color: var(--arco-success); }.task-status--failed { color: var(--arco-danger); }.task-copy { min-width: 0; flex: 1; }.task-copy strong { display: block; overflow: hidden; color: var(--neutral-text-1); text-overflow: ellipsis; white-space: nowrap; }.quick-flow-list { gap: 8px; }.quick-flow { justify-content: flex-start; gap: 8px; }.detail-list { margin-bottom: 20px; }.detail-list > div { justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--neutral-border); color: var(--neutral-text-2); font-size: 13px; }.detail-list > div:last-child { border-bottom: 0; }.detail-list strong { color: var(--neutral-text-1); font-weight: 500; }.field-label { display: grid; gap: 8px; color: var(--neutral-text-2); font-size: 13px; }.privacy-row { justify-content: space-between; gap: 20px; padding: 16px 0; border-bottom: 1px solid var(--neutral-border); }.privacy-row:last-child { border-bottom: 0; }.privacy-row strong, .audit-row strong, .memory-row strong { color: var(--neutral-text-1); font-size: 14px; }.audit-row { align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--neutral-border); }.audit-row:last-child { border-bottom: 0; }.audit-row > span { min-width: 0; flex: 1; }.memory-hint { margin: 0 0 12px; color: var(--neutral-text-3); font-size: 13px; }.memory-row { display: flex; align-items: flex-start; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--neutral-border); }.memory-row:last-child { border-bottom: 0; }.memory-row > div { min-width: 0; flex: 1; }.memory-row small { display: block; margin-top: 4px; color: var(--neutral-text-3); font-size: 12px; }
@media (min-width: 1440px) { .profile-content { max-width: 1152px; padding-left: 32px; padding-right: 32px; } }
@media (max-width: 900px) { .profile-grid { grid-template-columns: repeat(2, 1fr); gap: 20px; }.profile-card--hero, .profile-card--wide { grid-column: span 2; } }
@media (max-width: 640px) { .profile-page-wrapper { padding: 24px 0 40px; }.profile-content { padding: 0 16px; }.profile-grid { grid-template-columns: 1fr; gap: 16px; }.profile-card, .profile-card--hero, .profile-card--wide { grid-column: span 1; padding: 24px; }.profile-hero { align-items: flex-start; flex-wrap: wrap; }.task-summary { grid-template-columns: 1fr; }.task-summary-item { border-right: 0; border-bottom: 1px solid var(--neutral-border); }.task-summary-item:last-child { border-bottom: 0; }.task-row { width: calc(100% + 48px); margin: 0 -24px; padding-left: 24px; padding-right: 24px; }.privacy-row { align-items: flex-start; flex-direction: column; gap: 12px; } }
@media (prefers-reduced-motion: reduce) { .task-row { transition-duration: 1ms; } }
</style>
