import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', requiresAuth: false }
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { title: '注册', requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '首页', requiresAuth: true }
      },
      {
        path: 'flows',
        name: 'flows',
        component: () => import('@/views/FlowsView.vue'),
        meta: { title: '分析流程', requiresAuth: true }
      },
      {
        path: 'flows/:flowId/submit',
        name: 'flow-submit',
        component: () => import('@/views/FlowSubmitView.vue'),
        meta: { title: '提交任务', requiresAuth: true }
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { title: '任务管理', requiresAuth: true }
      },
      {
        path: 'tasks/:taskId',
        name: 'task-detail',
        component: () => import('@/views/TaskDetailView.vue'),
        meta: { title: '任务详情', requiresAuth: true }
      },
      {
        path: 'files',
        name: 'files',
        component: () => import('@/views/FilesView.vue'),
        meta: { title: '文件管理', requiresAuth: true }
      },
      {
        path: 'ai',
        name: 'ai',
        component: () => import('@/views/AIChatView.vue'),
        meta: { title: 'AI 助手', requiresAuth: true }
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: '个人中心', requiresAuth: true }
      },
      {
        path: 'cookies',
        name: 'cookies',
        component: () => import('@/views/CookieAccountView.vue'),
        meta: { title: '饼干账户', requiresAuth: true }
      },
      {
        path: 'admin/cookies/accounts',
        name: 'admin-cookies-accounts',
        component: () => import('@/views/AdminCookieManagementView.vue'),
        meta: { title: '饼干账户管理', requiresAuth: true }
      },
      {
        path: 'admin/cookies/pricing',
        name: 'admin-cookies-pricing',
        component: () => import('@/views/AdminCookiePricingView.vue'),
        meta: { title: '饼干定价管理', requiresAuth: true }
      },
      {
        path: 'admin/users',
        name: 'admin-users',
        component: () => import('@/views/AdminUserManagementView.vue'),
        meta: { title: '用户管理', requiresAuth: true }
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '404', requiresAuth: false }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const isLoggedIn = authStore.isLoggedIn
  
  if (to.meta.requiresAuth && !isLoggedIn) {
    // 需要登录但未登录
    next('/login')
  } else if ((to.name === 'login' || to.name === 'register') && isLoggedIn) {
    // 已登录且访问登录/注册页
    next('/')
  } else {
    // 设置页面标题
    if (to.meta.title) {
      document.title = `${to.meta.title} - OmicHub`
    } else {
      document.title = 'OmicHub'
    }
    next()
  }
})

export default router
