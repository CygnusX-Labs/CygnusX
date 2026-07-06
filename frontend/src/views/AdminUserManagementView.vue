<script setup lang="ts">
import apiClient from '@/api/client'
import {
  NButton,
  NCard,
  NDataTable,
  NDropdown,
  NIcon,
  NSpace,
  NTag,
  useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  EllipsisHorizontal,
  CreateOutline,
  ServerOutline,
  PersonOutline,
  TrashOutline,
  CashOutline,
  DocumentTextOutline,
} from '@vicons/ionicons5'
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AddUserModal from '@/components/AddUserModal.vue'
import QuotaEditModal from '@/components/QuotaEditModal.vue'
import NoteEditModal from '@/components/NoteEditModal.vue'
import AdminTOTPConfirmModal from '@/components/AdminTOTPConfirmModal.vue'
import RechargeModal from '@/components/admin-cookie/RechargeModal.vue'
import { useAuthStore } from '@/stores/auth'

interface AdminUser {
  id: string
  username: string
  nickname?: string | null
  email: string
  role: string
  status: string
  created_at: string
  last_login_at: string | null
  storage_quota: number
  used_storage: number
  admin_note?: string | null
  lab_group?: string | null
  cookie_balance?: number | null
  cookie_status?: string | null
}

const message = useMessage()
const authStore = useAuthStore()
const router = useRouter()
const users = ref<AdminUser[]>([])
const loading = ref(false)

// 快捷充值弹窗（与「饼干账户管理」共用同一组件）
const showRecharge = ref(false)
const rechargeUserId = ref<string | null>(null)

// 添加用户弹窗
const addUserModalVisible = ref(false)

// 调整配额弹窗
const quotaModalVisible = ref(false)
const quotaTarget = ref<AdminUser | null>(null)

// 编辑备注弹窗
const noteModalVisible = ref(false)
const noteTarget = ref<AdminUser | null>(null)

// 高敏感操作：TOTP 二次确认弹窗
const totpModalVisible = ref(false)
const totpTargetId = ref<string | null>(null)
const totpTargetUsername = ref('')
const totpLoading = ref(false)

const statusTag = (status: string) => {
  const map: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
    active: 'success',
    pending: 'warning',
    rejected: 'error',
    inactive: 'default',
  }
  return map[status] || 'default'
}

/** "更多▾"下拉菜单：低频/破坏性操作收纳于此 */
function buildMoreOptions(row: AdminUser) {
  const opts: any[] = [
    { label: '编辑备注', key: 'note', icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) },
    { label: '修改配额', key: 'quota', icon: () => h(NIcon, null, { default: () => h(ServerOutline) }) },
    { label: '💰 快捷充值饼干', key: 'recharge', icon: () => h(NIcon, null, { default: () => h(CashOutline) }) },
    { label: '📄 查看资产流水', key: 'txns', icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }) },
  ]
  // 升降管理员：仅 active 用户可调权（已拒绝账号调权无意义）
  if (row.status === 'active') {
    opts.push({
      label: row.role === 'admin' ? '降为用户' : '升为管理员',
      key: 'role',
      icon: () => h(NIcon, null, { default: () => h(PersonOutline) }),
    })
  }
  return opts
}

/** 下拉菜单选中处理（删除不在此处理，走 TOTP 二次确认弹窗） */
function handleMoreSelect(key: string, row: AdminUser) {
  if (key === 'note') openNoteModal(row)
  else if (key === 'quota') openQuotaModal(row)
  else if (key === 'role') toggleRole(row)
  else if (key === 'recharge') openRecharge(row)
  else if (key === 'txns') viewTxns(row)
}

function openRecharge(row: AdminUser) {
  rechargeUserId.value = row.id
  showRecharge.value = true
}

function viewTxns(row: AdminUser) {
  router.push({ name: 'admin-cookies-transactions', query: { user_id: row.id } })
}

const columns: DataTableColumns<AdminUser> = [
  {
    title: '用户',
    key: 'username',
    render: (row) => (row.nickname ? `${row.nickname}（${row.username}）` : row.username),
  },
  { title: '邮箱', key: 'email', ellipsis: { tooltip: true } },
  {
    title: '角色',
    key: 'role',
    render: (row) =>
      h(
        NTag,
        { type: row.role === 'admin' ? 'success' : 'default', size: 'small', round: true },
        { default: () => (row.role === 'admin' ? '管理员' : '用户') },
      ),
  },
  {
    title: '状态',
    key: 'status',
    render: (row) => {
      const tags: any[] = [
        h(NTag, { type: statusTag(row.status), size: 'small', round: true }, { default: () => row.status }),
      ]
      // 资产穿透：饼干余额为负 → 红色「欠费」Tag
      if (typeof row.cookie_balance === 'number' && row.cookie_balance < 0) {
        tags.push(h(NTag, { type: 'error', size: 'small', round: true }, { default: () => '欠费' }))
      }
      return h(NSpace, { size: 4, align: 'center' }, { default: () => tags })
    },
  },
  {
    title: '备注',
    key: 'admin_note',
    ellipsis: { tooltip: true },
    render: (row) =>
      row.admin_note
        ? h('span', { class: 'note-cell' }, row.admin_note)
        : h('span', { class: 'note-empty' }, '—'),
  },
  {
    title: '注册时间',
    key: 'created_at',
    render: (row) => (row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-'),
  },
  {
    title: '存储用量',
    key: 'storage',
    width: 160,
    render: (row) => {
      const usedGb = (row.used_storage || 0) / 1024 / 1024 / 1024
      const totalGb = (row.storage_quota || 0) / 1024 / 1024 / 1024
      const pct = totalGb > 0 ? Math.min(100, (usedGb / totalGb) * 100) : 0
      const color = pct >= 91 ? '#FF6B6B' : pct >= 71 ? '#FFC53D' : '#36CFC9'
      return h('div', { class: 'storage-cell' }, [
        h('div', { class: 'storage-bar' }, [
          h('div', { class: 'storage-bar-fill', style: { width: `${pct}%`, background: color } }),
        ]),
        h('span', { class: 'storage-text' }, `${usedGb.toFixed(1)} / ${totalGb.toFixed(0)} GiB`),
      ])
    },
  },
  {
    title: '当前饼干余额',
    key: 'cookie_balance',
    width: 120,
    render: (row) => {
      const bal = typeof row.cookie_balance === 'number' ? row.cookie_balance : 0
      const cls = bal < 0 ? 'cookie-danger' : bal < 50 ? 'cookie-warn' : 'cookie-normal'
      return h('span', { class: ['cookie-balance', cls] }, `${bal} 🥫`)
    },
  },
  {
    title: '最后登录',
    key: 'last_login_at',
    render: (row) => (row.last_login_at ? new Date(row.last_login_at).toLocaleString('zh-CN') : '从未登录'),
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    fixed: 'right',
    render: (row) => {
      const primary: any[] = []

      // ===== 主操作：与状态最相关的核心动作，外露 =====
      if (row.status === 'pending') {
        primary.push(
          h(NButton, { size: 'small', type: 'success', onClick: () => approveUser(row.id) }, { default: () => '通过' }),
        )
        primary.push(
          h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => rejectUser(row.id) }, { default: () => '拒绝' }),
        )
      } else if (row.status === 'rejected') {
        // 已拒绝：提供"重新通过"捞回误拒用户
        primary.push(
          h(
            NButton,
            { size: 'small', type: 'success', ghost: true, onClick: () => approveUser(row.id) },
            { default: () => '重新通过' },
          ),
        )
      } else if (row.status === 'active' || row.status === 'inactive') {
        // 启用/禁用：不能禁用自己
        const isSelf = row.id === authStore.user?.id
        const disabling = row.status === 'active'
        primary.push(
          h(
            NButton,
            {
              size: 'small',
              type: 'warning',
              ghost: true,
              disabled: isSelf && disabling,
              title: isSelf && disabling ? '不能禁用当前登录账号' : '',
              onClick: () => toggleStatus(row),
            },
            { default: () => (disabling ? '禁用' : '启用') },
          ),
        )
      }

      // ===== 次要操作：收纳进"更多▾"下拉 =====
      const isSelf = row.id === authStore.user?.id
      const moreDropdown = h(
        NDropdown,
        {
          trigger: 'click',
          options: buildMoreOptions(row),
          onSelect: (key: string) => handleMoreSelect(key, row),
        },
        {
          default: () =>
            h(
              NButton,
              { size: 'small', quaternary: true },
              {
                default: () => '更多',
                icon: () => h(NIcon, null, { default: () => h(EllipsisHorizontal) }),
              },
            ),
        },
      )

      // 删除：高危，独立放最右，TOTP 二次确认弹窗
      const deleteBtn = h(
        NButton,
        {
          size: 'small',
          type: 'error',
          ghost: true,
          disabled: isSelf,
          title: isSelf ? '不能删除当前登录账号' : '删除该用户',
          onClick: () => openDeleteWithTotp(row),
        },
        { default: () => '删除' },
      )

      return h(NSpace, { size: 4, align: 'center' }, { default: () => [...primary, moreDropdown, deleteBtn] })
    },
  },
]

async function fetchUsers() {
  loading.value = true
  try {
    const res = await apiClient.get<AdminUser[]>('/admin/users')
    users.value = res.data
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '用户列表加载失败')
  } finally {
    loading.value = false
  }
}

async function approveUser(id: string) {
  await apiClient.put(`/admin/users/${id}/approve`)
  message.success('已审批通过')
  await fetchUsers()
}

async function rejectUser(id: string) {
  await apiClient.put(`/admin/users/${id}/reject`)
  message.success('已拒绝')
  await fetchUsers()
}

async function toggleRole(row: AdminUser) {
  const newRole = row.role === 'admin' ? 'user' : 'admin'
  await apiClient.put(`/admin/users/${row.id}/role`, null, { params: { role: newRole } })
  message.success(`已设为 ${newRole === 'admin' ? '管理员' : '用户'}`)
  await fetchUsers()
}

// 启用/禁用账号：禁用后用户登录被拒
async function toggleStatus(row: AdminUser) {
  const newStatus = row.status === 'active' ? 'inactive' : 'active'
  await apiClient.put(`/admin/users/${row.id}/status`, null, { params: { status: newStatus } })
  message.success(newStatus === 'active' ? '账号已启用' : '账号已禁用')
  await fetchUsers()
}

// 删除：先弹 TOTP 二次确认，再请求后端（带 X-TOTP-Code 请求头）
function openDeleteWithTotp(row: AdminUser) {
  totpTargetId.value = row.id
  totpTargetUsername.value = row.username
  totpModalVisible.value = true
}

async function handleTotpConfirm(code: string) {
  if (!totpTargetId.value) return
  totpLoading.value = true
  try {
    await deleteUser(totpTargetId.value, code)
    totpModalVisible.value = false
    totpTargetId.value = null
    totpTargetUsername.value = ''
  } finally {
    totpLoading.value = false
  }
}

async function deleteUser(id: string, totpCode: string) {
  try {
    await apiClient.delete(`/admin/users/${id}`, {
      headers: { 'X-TOTP-Code': totpCode },
    })
    message.success('用户已删除')
    await fetchUsers()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '删除失败')
  }
}

function openQuotaModal(row: AdminUser) {
  quotaTarget.value = row
  quotaModalVisible.value = true
}

function openNoteModal(row: AdminUser) {
  noteTarget.value = row
  noteModalVisible.value = true
}

// 备注保存成功后，本地同步更新该行备注（免一次全量拉取）
function onNoteSaved(userId: string, note: string) {
  const row = users.value.find((u) => u.id === userId)
  if (row) row.admin_note = note
}

onMounted(fetchUsers)
</script>

<template>
  <div class="page-container">
    <div class="user-mgmt-header">
      <h1 class="page-title">用户管理</h1>
      <NButton type="primary" @click="addUserModalVisible = true">+ 添加用户</NButton>
    </div>
    <NCard title="用户列表" :bordered="false" class="arco-card">
      <NDataTable
        :columns="columns"
        :data="users"
        :loading="loading"
        :pagination="{ pageSize: 20 }"
        :bordered="false"
        size="small"
        :scroll-x="1400"
      />
    </NCard>

    <!-- 添加用户弹窗 -->
    <AddUserModal v-model:show="addUserModalVisible" @success="fetchUsers" />

    <!-- 调整存储配额弹窗 -->
    <QuotaEditModal v-model:show="quotaModalVisible" :user="quotaTarget" @success="fetchUsers" />

    <!-- 编辑管理员备注弹窗 -->
    <NoteEditModal
      v-model:show="noteModalVisible"
      :user="noteTarget"
      @success="(note: string) => onNoteSaved(noteTarget?.id || '', note)"
    />

    <!-- 快捷充值饼干（与饼干账户管理共用同一全局组件） -->
    <RechargeModal
      v-model:show="showRecharge"
      :user-id="rechargeUserId"
      @success="fetchUsers"
    />
    <!-- 删除用户 TOTP 二次确认弹窗 -->
    <AdminTOTPConfirmModal
      v-model:show="totpModalVisible"
      :title="`删除用户：${totpTargetUsername}`"
      :description="`确认彻底删除用户「${totpTargetUsername}」？此操作不可恢复，请输入当前 6 位 TOTP 验证码。`"
      confirm-text="确认删除"
      :loading="totpLoading"
      @confirm="handleTotpConfirm"
    />
  </div>
</template>

<style scoped>
.user-mgmt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.user-mgmt-header .page-title {
  margin: 0;
}
.note-cell {
  color: var(--neutral-text-2, #4e5969);
  font-size: 13px;
}
.note-empty {
  color: var(--neutral-text-4, #c9cdd4);
}
.storage-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.storage-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--neutral-fill, #e5e6eb);
  overflow: hidden;
}
.storage-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}
.storage-text {
  font-size: 11px;
  color: var(--neutral-text-3, #86909c);
}
.cookie-balance {
  font-weight: 600;
  font-size: 13px;
}
.cookie-balance.cookie-normal {
  color: var(--arco-success, #00B42A);
}
.cookie-balance.cookie-warn {
  color: var(--arco-warning, #FF7D00);
}
.cookie-balance.cookie-danger {
  color: var(--arco-danger, #F53F3F);
}
</style>
