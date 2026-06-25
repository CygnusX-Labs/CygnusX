<template>
  <div class="profile-container">
    <n-card title="个人信息" :bordered="false" class="profile-card">
      <n-descriptions :column="2" bordered>
        <n-descriptions-item label="用户ID">{{ user?.id }}</n-descriptions-item>
        <n-descriptions-item label="用户名">{{ user?.username }}</n-descriptions-item>
        <n-descriptions-item label="邮箱">{{ user?.email }}</n-descriptions-item>
        <n-descriptions-item label="角色">{{ user?.role }}</n-descriptions-item>
        <n-descriptions-item label="账户状态">
          <n-tag :type="user?.status === 'active' ? 'success' : 'warning'">
            {{ user?.status }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="创建时间">{{ formatDate(user?.created_at) }}</n-descriptions-item>
      </n-descriptions>

      <div class="card-actions">
        <n-button type="primary" @click="handleUpdateProfile">修改信息</n-button>
        <n-button @click="handleChangePassword">修改密码</n-button>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const dialog = useDialog()
const user = ref<User | null>(null)

const formatDate = (dateStr?: string | null) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const fetchUserProfile = async () => {
  try {
    await authStore.fetchUser()
    user.value = authStore.user
  } catch (error: any) {
    message.error('获取用户信息失败')
    if (error.response?.status === 401) {
      authStore.logout()
      router.push('/login')
    }
  }
}

const handleUpdateProfile = () => {
  dialog.info({
    title: '修改个人信息',
    content: '该功能开发中...',
    positiveText: '确定',
    onPositiveClick: () => {
      message.info('功能开发中，敬请期待')
    },
  })
}

const handleChangePassword = () => {
  dialog.info({
    title: '修改密码',
    content: '该功能开发中...',
    positiveText: '确定',
    onPositiveClick: () => {
      message.info('功能开发中，敬请期待')
    },
  })
}

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  fetchUserProfile()
})
</script>

<style scoped>
.profile-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.profile-card {
  margin-bottom: 24px;
}

.card-actions {
  margin-top: 24px;
  display: flex;
  gap: 12px;
  justify-content: flex-start;
}
</style>
