<script setup lang="ts">
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { h } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const menuOptions: MenuOption[] = [
  {
    label: () => h(RouterLink, { to: '/' }, { default: () => '首页' }),
    key: 'dashboard',
  },
  {
    label: () => h(RouterLink, { to: '/flows' }, { default: () => '分析流程' }),
    key: 'flows',
  },
  {
    label: () => h(RouterLink, { to: '/tasks' }, { default: () => '任务管理' }),
    key: 'tasks',
  },
  {
    label: () => h(RouterLink, { to: '/files' }, { default: () => '文件管理' }),
    key: 'files',
  },
  {
    label: () => h(RouterLink, { to: '/ai' }, { default: () => 'AI 助手' }),
    key: 'ai',
  },
]

const route = useRoute()
</script>

<template>
  <NLayout has-sider style="height: 100vh">
    <NLayoutSider bordered :width="220" :collapsed-width="64">
      <div style="padding: 16px; font-size: 18px; font-weight: bold; text-align: center">
        OmicHub
      </div>
      <NMenu :options="menuOptions" :value="route.name as string" />
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered style="height: 56px; padding: 0 24px; display: flex; align-items: center">
        <span>{{ route.meta.title || 'OmicHub' }}</span>
      </NLayoutHeader>
      <NLayoutContent content-style="padding: 24px;" :native-scrollbar="false">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>
