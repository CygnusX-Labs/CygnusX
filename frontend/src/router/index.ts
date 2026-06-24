import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'flows',
        name: 'flows',
        component: () => import('@/views/FlowsView.vue'),
        meta: { title: '分析流程' },
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { title: '任务管理' },
      },
      {
        path: 'files',
        name: 'files',
        component: () => import('@/views/FilesView.vue'),
        meta: { title: '文件管理' },
      },
      {
        path: 'ai',
        name: 'ai',
        component: () => import('@/views/AIChatView.vue'),
        meta: { title: 'AI 助手' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
