<script setup lang="ts">
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NIcon } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { computed, h, ref, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Home, List, DocumentText, Chatbubbles, CloudUpload, Wallet, People, Pricetags, PersonCircle } from '@vicons/ionicons5'
import HeaderComponent from '@/components/HeaderComponent.vue'
import CookieBalanceBadge from '@/components/CookieBalanceBadge.vue'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'

const authStore = useAuthStore()
const route = useRoute()
const currentUser = ref<User | null>(null)

const isAdmin = computed(() => authStore.user?.role === 'admin')

const menuOptions = computed<MenuOption[]>(() => {
  const items: MenuOption[] = [
    {
      label: () => h(RouterLink, { to: '/' }, { default: () => '首页' }),
      key: 'dashboard',
      icon: () => h(NIcon, null, { default: () => h(Home) }),
    },
    {
      label: () => h(RouterLink, { to: '/flows' }, { default: () => '分析流程' }),
      key: 'flows',
      icon: () => h(NIcon, null, { default: () => h(List) }),
    },
    {
      label: () => h(RouterLink, { to: '/tasks' }, { default: () => '任务管理' }),
      key: 'tasks',
      icon: () => h(NIcon, null, { default: () => h(DocumentText) }),
    },
    {
      label: () => h(RouterLink, { to: '/files' }, { default: () => '文件管理' }),
      key: 'files',
      icon: () => h(NIcon, null, { default: () => h(CloudUpload) }),
    },
    {
      label: () => h(RouterLink, { to: '/ai' }, { default: () => 'AI 助手' }),
      key: 'ai',
      icon: () => h(NIcon, null, { default: () => h(Chatbubbles) }),
    },
    {
      label: () => h(RouterLink, { to: '/cookies' }, { default: () => '饼干账户' }),
      key: 'cookies',
      icon: () => h(NIcon, null, { default: () => h(Wallet) }),
    },
  ]

  if (isAdmin.value) {
    items.push({
      label: '系统管理',
      key: 'admin',
      icon: () => h(NIcon, null, { default: () => h(People) }),
      children: [
        {
          label: () => h(RouterLink, { to: '/admin/users' }, { default: () => '用户管理' }),
          key: 'admin-users',
          icon: () => h(NIcon, null, { default: () => h(PersonCircle) }),
        },
        {
          label: () => h(RouterLink, { to: '/admin/cookies/accounts' }, { default: () => '饼干账户管理' }),
          key: 'admin-cookies-accounts',
          icon: () => h(NIcon, null, { default: () => h(People) }),
        },
        {
          label: () => h(RouterLink, { to: '/admin/cookies/pricing' }, { default: () => '饼干定价管理' }),
          key: 'admin-cookies-pricing',
          icon: () => h(NIcon, null, { default: () => h(Pricetags) }),
        },
      ],
    })
  }

  return items
})

onMounted(async () => {
  if (authStore.isLoggedIn) {
    await authStore.fetchUser()
    currentUser.value = authStore.user
  }
})
</script>

<template>
  <NLayout has-sider style="height: 100vh">
    <NLayoutSider bordered :width="220" :collapsed-width="64">
      <div style="padding: 16px; font-size: 18px; font-weight: bold; text-align: center; color: #1890ff;">
        OmicHub
      </div>
      <NMenu :options="menuOptions" :value="route.name as string" :indent="18" :collapsed-width="64" />
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered style="height: 64px; padding: 0 24px; display: flex; align-items: center; justify-content: space-between;">
        <div style="flex: 1" />
        <CookieBalanceBadge />
        <HeaderComponent :current-user="currentUser" />
      </NLayoutHeader>
      <NLayoutContent content-style="padding: 24px;" :native-scrollbar="false">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>
