<script setup lang="ts">
import apiClient from '@/api/client'
import {
  NButton,
  NCard,
  NDataTable,
  NSpace,
  NTag,
  useMessage,
} from 'naive-ui'
import { h, onMounted, ref } from 'vue'

const message = useMessage()
const users = ref<any[]>([])
const loading = ref(false)

const statusTag = (status: string) => {
  const map: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
    active: 'success',
    pending: 'warning',
    rejected: 'error',
    inactive: 'default',
  }
  return map[status] || 'default'
}

const columns = [
  { title: '用户名', key: 'username' },
  { title: '邮箱', key: 'email', ellipsis: { tooltip: true } },
  {
    title: '角色',
    key: 'role',
    render: (row: any) => h(NTag, { type: row.role === 'admin' ? 'success' : 'default', size: 'small' }, { default: () => row.role }),
  },
  {
    title: '状态',
    key: 'status',
    render: (row: any) => h(NTag, { type: statusTag(row.status), size: 'small' }, { default: () => row.status }),
  },
  {
    title: '注册时间',
    key: 'created_at',
    render: (row: any) => row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-',
  },
  {
    title: '最后登录',
    key: 'last_login_at',
    render: (row: any) => row.last_login_at ? new Date(row.last_login_at).toLocaleString('zh-CN') : '从未登录',
  },
  {
    title: '操作',
    key: 'actions',
    render: (row: any) => {
      const btns: any[] = []
      if (row.status === 'pending') {
        btns.push(h(NButton, { size: 'small', type: 'success', onClick: () => approveUser(row.id) }, { default: () => '通过' }))
        btns.push(h(NButton, { size: 'small', type: 'error', onClick: () => rejectUser(row.id) }, { default: () => '拒绝' }))
      }
      if (row.status === 'active' || row.status === 'rejected') {
        btns.push(h(NButton, {
          size: 'small',
          type: row.role === 'admin' ? 'warning' : 'info',
          onClick: () => toggleRole(row),
        }, { default: () => row.role === 'admin' ? '降为用户' : '升为管理员' }))
      }
      return h(NSpace, { size: 'small' }, { default: () => btns })
    },
  },
]

async function fetchUsers() {
  loading.value = true
  try {
    const res = await apiClient.get('/admin/users')
    users.value = res.data
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

async function toggleRole(row: any) {
  const newRole = row.role === 'admin' ? 'user' : 'admin'
  await apiClient.put(`/admin/users/${row.id}/role`, null, { params: { role: newRole } })
  message.success(`已设为 ${newRole}`)
  await fetchUsers()
}

onMounted(fetchUsers)
</script>

<template>
  <NSpace vertical :size="24" style="padding: 24px">
    <NCard title="用户管理">
      <NDataTable :columns="columns" :data="users" :loading="loading" :pagination="{ pageSize: 20 }" />
    </NCard>
  </NSpace>
</template>
