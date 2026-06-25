<template>
  <div class="header">
    <div class="header-left">
      <h1 class="logo">OmicHub</h1>
    </div>
    <div class="header-right">
      <n-dropdown :options="userMenuOptions" trigger="click" placement="bottom-end" @select="handleMenuSelect">
        <n-button text>
          <span class="username">{{ currentUser?.username || '未登录' }}</span>
          <n-icon size="18">
            <ChevronDown />
          </n-icon>
        </n-button>
      </n-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { h } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ChevronDown, Person, Settings, LogOut } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'

const router = useRouter()
const authStore = useAuthStore()

const props = defineProps<{
  currentUser: User | null
}>()

const userMenuOptions = [
  {
    label: '个人中心',
    key: 'profile',
    icon: () => h(NIcon, null, { default: () => h(Person) }),
  },
  {
    label: '设置',
    key: 'settings',
    icon: () => h(NIcon, null, { default: () => h(Settings) }),
  },
  { type: 'divider' as const },
  {
    label: '退出登录',
    key: 'logout',
    icon: () => h(NIcon, null, { default: () => h(LogOut) }),
  },
]

function handleMenuSelect(key: string) {
  if (key === 'profile') {
    router.push('/profile')
  } else if (key === 'settings') {
    router.push('/settings')
  } else if (key === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 64px;
  width: 100%;
  padding: 0 24px;
  background: white;
  border-bottom: 1px solid #e8e8e8;
}

.header-left .logo {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #1890ff;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.username {
  margin-right: 8px;
}
</style>
