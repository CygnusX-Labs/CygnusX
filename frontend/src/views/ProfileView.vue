<template>
  <div class="page-container">
    <h1 class="page-title">个人中心</h1>
    <n-card title="个人信息" :bordered="false" class="arco-card profile-card">
      <n-descriptions :column="2" bordered>
        <n-descriptions-item label="用户ID">{{ user?.id }}</n-descriptions-item>
        <n-descriptions-item label="用户名">{{ user?.username }}</n-descriptions-item>
        <n-descriptions-item label="昵称">{{ user?.nickname || '未设置' }}</n-descriptions-item>
        <n-descriptions-item label="邮箱">{{ user?.email }}</n-descriptions-item>
        <n-descriptions-item label="角色">{{ roleLabel }}</n-descriptions-item>
        <n-descriptions-item label="账户状态">
          <n-tag :type="user?.status === 'active' ? 'success' : 'warning'" round>
            {{ statusLabel }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="创建时间">{{ formatDate(user?.created_at) }}</n-descriptions-item>
        <n-descriptions-item label="最后登录">{{ formatDate(user?.last_login_at) }}</n-descriptions-item>
      </n-descriptions>

      <!-- 修改信息 / 修改密码已在「账号设置」实现，这里仅做引导跳转 -->
      <div class="card-actions">
        <n-button type="primary" @click="goSettings">前往账号设置</n-button>
      </div>
      <p class="card-hint">可在「账号设置」中修改用户名、邮箱与密码。</p>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const user = ref<User | null>(null)

const roleLabel = computed(() => (user.value?.role === 'admin' ? '管理员' : '普通用户'))
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

const formatDate = (dateStr?: string | null) => {
  if (!dateStr) return '从未登录'
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

function goSettings() {
  router.push('/settings')
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
/* 居中卡片：与「账号设置」一致的 max-width + margin: 0 auto 写法 */
.profile-card {
  max-width: 720px;
  margin: 0 auto;
}

.card-actions {
  margin-top: 24px;
  display: flex;
  gap: 12px;
  justify-content: flex-start;
}

.card-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--neutral-text-3);
}
</style>
