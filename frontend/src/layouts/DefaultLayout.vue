<script setup lang="ts">
import {
  NLayout, NLayoutSider, NLayoutContent, NIcon, NButton, NTooltip, NDropdown,
  NDrawer, NDrawerContent, NAvatar, NBadge,
} from 'naive-ui'
import { computed, h, ref, watch, onMounted } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  HomeOutline, GridOutline, FlaskOutline, FitnessOutline, GlobeOutline, BugOutline,
  DocumentTextOutline, CloudUploadOutline, BarChartOutline, SettingsOutline,
  InformationCircleOutline, PersonOutline, LogOutOutline, MoonOutline, SunnyOutline,
  MenuOutline, ChevronForwardOutline, ChevronBackOutline, ChevronDownOutline,
  NotificationsOutline, HelpCircleOutline, ChatbubblesOutline, Planet, CodeSlashOutline,
  WalletOutline, PricetagOutline, SparklesOutline,
} from '@vicons/ionicons5'
import CookieBalanceBadge from '@/components/CookieBalanceBadge.vue'
import NotificationDrawer from '@/components/NotificationDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import type { User } from '@/types'

const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const route = useRoute()
const router = useRouter()
const currentUser = ref<User | null>(null)

const collapsed = ref(false)
const mobileDrawerOpen = ref(false)
const notificationDrawerOpen = ref(false)
const expandedKeys = ref<string[]>(['analysis-center'])

const isAdmin = computed(() => authStore.user?.role === 'admin')

// 响应式：窗口宽度 < 1024 自动折叠，< 768 进入移动端模式
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value < 768)
const isTablet = computed(() => windowWidth.value >= 768 && windowWidth.value < 1024)

function updateWindowWidth() {
  windowWidth.value = window.innerWidth
  if (isMobile.value) {
    collapsed.value = false
  } else if (isTablet.value) {
    collapsed.value = true
  } else {
    collapsed.value = false
  }
}

onMounted(() => {
  updateWindowWidth()
  window.addEventListener('resize', updateWindowWidth)
  if (authStore.isLoggedIn) {
    authStore.fetchUser().then(() => {
      currentUser.value = authStore.user
      notificationStore.fetchNotifications()
    })
  }
})

watch(windowWidth, updateWindowWidth)

interface NavItem {
  key: string
  label: string
  to: string
  icon: typeof HomeOutline
  children?: NavItem[]
}

const topNavItems = computed<NavItem[]>(() => [
  { key: 'dashboard', label: '控制台', to: '/', icon: HomeOutline },
  { key: 'flows', label: '分析流程中心', to: '/flows', icon: FlaskOutline },
  { key: 'knowledge', label: '实验室知识库', to: '/about', icon: DocumentTextOutline },
  { key: 'docs', label: '文档', to: '/about', icon: HelpCircleOutline },
])

const mainNavItems = computed<NavItem[]>(() => [
  { key: 'home', label: '首页', to: '/about', icon: HomeOutline },
  { key: 'dashboard', label: '仪表板', to: '/', icon: GridOutline },
  {
    key: 'analysis-center',
    label: '分析中心',
    to: '/flows',
    icon: FlaskOutline,
    children: [
      { key: 'rna-seq', label: 'RNA-seq 分析', to: '/flows', icon: FlaskOutline },
      { key: 'atac-seq', label: 'ATAC-seq 分析', to: '/flows', icon: FitnessOutline },
      { key: 'chip-seq', label: 'ChIP-seq 分析', to: '/flows', icon: FlaskOutline },
      { key: 'scrna', label: '单细胞分析', to: '/flows', icon: GridOutline },
      { key: 'wgs', label: '全基因组测序', to: '/flows', icon: GlobeOutline },
      { key: 'metagenome', label: '宏基因组分析', to: '/flows', icon: BugOutline },
    ],
  },
  { key: 'files', label: '数据管理', to: '/files', icon: CloudUploadOutline },
  { key: 'tasks', label: '任务中心', to: '/tasks', icon: DocumentTextOutline },
  { key: 'ai', label: 'AI 助手', to: '/ai', icon: ChatbubblesOutline },
  { key: 'sandbox', label: '代码沙盒', to: '/sandbox', icon: CodeSlashOutline },
])

const systemNavItems = computed<NavItem[]>(() => [
  { key: 'cookies', label: '用量统计', to: '/cookies', icon: BarChartOutline },
  { key: 'settings', label: '系统设置', to: '/settings', icon: SettingsOutline },
  { key: 'about', label: '关于 OmicHub', to: '/about', icon: InformationCircleOutline },
])

const adminNavItems = computed<NavItem[]>(() => [
  {
    key: 'admin-center',
    label: '系统管理',
    to: '/admin/users',
    icon: SettingsOutline,
    children: [
      { key: 'admin-users', label: '用户管理', to: '/admin/users', icon: PersonOutline },
      { key: 'admin-cookies-accounts', label: '饼干账户管理', to: '/admin/cookies/accounts', icon: WalletOutline },
      { key: 'admin-cookies-pricing', label: '饼干定价管理', to: '/admin/cookies/pricing', icon: PricetagOutline },
      { key: 'admin-ai-providers', label: 'AI 模型配置', to: '/admin/ai-providers', icon: SparklesOutline },
    ],
  },
])

function isActive(item: NavItem): boolean {
  if (route.path === item.to && item.to !== '/flows') return true
  if (item.children) {
    return item.children.some((child) => route.name === child.key)
  }
  return false
}

function isTopActive(item: NavItem): boolean {
  if (item.key === 'dashboard') return route.path === '/'
  if (item.key === 'flows') return route.path.startsWith('/flows')
  return false
}

function toggleExpanded(key: string) {
  const idx = expandedKeys.value.indexOf(key)
  if (idx >= 0) {
    expandedKeys.value.splice(idx, 1)
  } else {
    expandedKeys.value.push(key)
  }
}

function isExpanded(key: string): boolean {
  return expandedKeys.value.includes(key)
}

function handleNavClick(item: NavItem) {
  if (isMobile.value) {
    mobileDrawerOpen.value = false
  }
  if (item.children && item.children.length) {
    toggleExpanded(item.key)
  }
  if (item.to) {
    router.push(item.to)
  }
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

const userMenuOptions = [
  { label: '个人中心', key: 'profile', icon: () => h(NIcon, null, { default: () => h(PersonOutline) }) },
  { label: '账号设置', key: 'settings', icon: () => h(NIcon, null, { default: () => h(SettingsOutline) }) },
  { label: '深色模式', key: 'theme', icon: () => h(NIcon, null, { default: () => h(MoonOutline) }) },
  { type: 'divider' as const, key: 'divider' },
  { label: '退出登录', key: 'logout', icon: () => h(NIcon, null, { default: () => h(LogOutOutline) }) },
]

function handleUserMenuSelect(key: string) {
  if (key === 'profile') router.push('/profile')
  else if (key === 'settings') router.push('/settings')
  else if (key === 'logout') handleLogout()
}

const UserAvatar = () => {
  const name = currentUser.value?.username || 'U'
  return h(NAvatar, {
    round: true,
    size: 'small',
    style: {
      background: 'var(--arco-primary-light)',
      color: 'var(--arco-primary)',
      fontSize: '12px',
      fontWeight: 500,
    },
  }, { default: () => name.charAt(0).toUpperCase() })
}
</script>

<template>
  <div class="app-shell">
    <!-- 顶部导航栏 -->
    <header class="top-nav">
      <div class="top-nav-left">
        <NButton text class="hamburger-btn" @click="isMobile ? mobileDrawerOpen = true : collapsed = !collapsed">
          <NIcon :size="20">
            <MenuOutline />
          </NIcon>
        </NButton>
        <div class="logo-block">
          <div class="logo-icon">
            <NIcon :size="24">
              <Planet />
            </NIcon>
          </div>
          <span class="logo-text">OmicHub</span>
        </div>
        <div class="top-nav-divider" />
        <nav class="top-nav-menu">
          <RouterLink
            v-for="item in topNavItems"
            :key="item.key"
            :to="item.to"
            class="top-nav-item"
            :class="{ 'top-nav-item--active': isTopActive(item) }"
          >
            {{ item.label }}
            <span v-if="isTopActive(item)" class="top-nav-indicator" />
          </RouterLink>
        </nav>
      </div>
      <div class="top-nav-right">
        <CookieBalanceBadge />
        <NTooltip placement="bottom" :delay="300">
          <template #trigger>
            <NButton text class="top-icon-btn" @click="notificationDrawerOpen = true">
              <NBadge :value="notificationStore.unreadCount" :max="99" :show="notificationStore.unreadCount > 0">
                <NIcon :size="20">
                  <NotificationsOutline />
                </NIcon>
              </NBadge>
            </NButton>
          </template>
          通知
        </NTooltip>
        <NTooltip placement="bottom" :delay="300">
          <template #trigger>
            <NButton text class="top-icon-btn" @click="$router.push('/about')">
              <NIcon :size="20">
                <HelpCircleOutline />
              </NIcon>
            </NButton>
          </template>
          帮助文档
        </NTooltip>
      </div>
    </header>

    <div class="app-body">
      <!-- 桌面端侧边栏 -->
      <NLayoutSider
        v-if="!isMobile"
        bordered
        :width="220"
        :collapsed-width="64"
        :collapsed="collapsed"
        collapse-mode="width"
        class="app-sider"
      >
        <div class="sider-inner">
          <div class="sider-nav-groups">
            <!-- 核心功能 -->
            <nav class="nav-group">
              <div
                v-for="item in mainNavItems"
                :key="item.key"
                class="nav-group-item"
              >
                <div
                  class="nav-item"
                  :class="{
                    'nav-item--active': isActive(item),
                    'nav-item--collapsed': collapsed,
                  }"
                  @click="handleNavClick(item)"
                >
                  <NTooltip v-if="collapsed && !item.children" placement="right" :delay="300">
                    <template #trigger>
                      <div class="nav-item-inner">
                        <NIcon :size="18" class="nav-icon">
                          <component :is="item.icon" />
                        </NIcon>
                      </div>
                    </template>
                    {{ item.label }}
                  </NTooltip>
                  <div v-else class="nav-item-inner">
                    <NIcon :size="18" class="nav-icon">
                      <component :is="item.icon" />
                    </NIcon>
                    <span v-show="!collapsed" class="nav-label">{{ item.label }}</span>
                    <NIcon
                      v-if="item.children && !collapsed"
                      :size="14"
                      class="nav-chevron"
                      :class="{ 'nav-chevron--expanded': isExpanded(item.key) }"
                    >
                      <ChevronForwardOutline />
                    </NIcon>
                  </div>
                </div>
                <!-- 子菜单 -->
                <div
                  v-if="item.children && !collapsed && isExpanded(item.key)"
                  class="sub-nav"
                >
                  <RouterLink
                    v-for="child in item.children"
                    :key="child.key"
                    :to="child.to"
                    class="sub-nav-item"
                    :class="{ 'sub-nav-item--active': route.name === child.key }"
                  >
                    <NIcon :size="16" class="sub-nav-icon">
                      <component :is="child.icon" />
                    </NIcon>
                    <span>{{ child.label }}</span>
                  </RouterLink>
                </div>
              </div>
            </nav>

            <div class="nav-divider" />

            <!-- 系统与资源 -->
            <nav class="nav-group">
              <div
                v-for="item in systemNavItems"
                :key="item.key"
                class="nav-item"
                :class="{
                  'nav-item--active': isActive(item),
                  'nav-item--collapsed': collapsed,
                }"
                @click="handleNavClick(item)"
              >
                <NTooltip v-if="collapsed" placement="right" :delay="300">
                  <template #trigger>
                    <div class="nav-item-inner">
                      <NIcon :size="18" class="nav-icon">
                        <component :is="item.icon" />
                      </NIcon>
                    </div>
                  </template>
                  {{ item.label }}
                </NTooltip>
                <div v-else class="nav-item-inner">
                  <NIcon :size="18" class="nav-icon">
                    <component :is="item.icon" />
                  </NIcon>
                  <span class="nav-label">{{ item.label }}</span>
                </div>
              </div>
            </nav>

            <!-- 管理员 -->
            <template v-if="isAdmin">
              <div class="nav-divider" />
              <nav class="nav-group">
                <div
                  v-for="item in adminNavItems"
                  :key="item.key"
                  class="nav-group-item"
                >
                  <div
                    class="nav-item"
                    :class="{
                      'nav-item--active': isActive(item),
                      'nav-item--collapsed': collapsed,
                    }"
                    @click="handleNavClick(item)"
                  >
                    <NTooltip v-if="collapsed && !item.children" placement="right" :delay="300">
                      <template #trigger>
                        <div class="nav-item-inner">
                          <NIcon :size="18" class="nav-icon">
                            <component :is="item.icon" />
                          </NIcon>
                        </div>
                      </template>
                      {{ item.label }}
                    </NTooltip>
                    <div v-else class="nav-item-inner">
                      <NIcon :size="18" class="nav-icon">
                        <component :is="item.icon" />
                      </NIcon>
                      <span v-show="!collapsed" class="nav-label">{{ item.label }}</span>
                      <NIcon
                        v-if="item.children && !collapsed"
                        :size="14"
                        class="nav-chevron"
                        :class="{ 'nav-chevron--expanded': isExpanded(item.key) }"
                      >
                        <ChevronForwardOutline />
                      </NIcon>
                    </div>
                  </div>
                  <!-- 子菜单 -->
                  <div
                    v-if="item.children && !collapsed && isExpanded(item.key)"
                    class="sub-nav"
                  >
                    <RouterLink
                      v-for="child in item.children"
                      :key="child.key"
                      :to="child.to"
                      class="sub-nav-item"
                      :class="{ 'sub-nav-item--active': route.name === child.key }"
                    >
                      <NIcon :size="16" class="sub-nav-icon">
                        <component :is="child.icon" />
                      </NIcon>
                      <span>{{ child.label }}</span>
                    </RouterLink>
                  </div>
                </div>
              </nav>
            </template>
          </div>

          <!-- 底部用户区 -->
          <div class="sider-footer">
            <div v-if="collapsed" class="user-avatar-only">
              <NDropdown
                trigger="click"
                placement="right"
                :options="userMenuOptions"
                @select="handleUserMenuSelect"
              >
                <NButton text class="user-avatar-btn">
                  <UserAvatar />
                </NButton>
              </NDropdown>
            </div>
            <NDropdown
              v-else
              trigger="click"
              placement="top-start"
              :options="userMenuOptions"
              @select="handleUserMenuSelect"
            >
              <div class="user-card">
                <UserAvatar />
                <div class="user-info">
                  <p class="user-name">{{ currentUser?.username || '未登录' }}</p>
                  <p class="user-role">{{ isAdmin ? '管理员' : '普通用户' }}</p>
                </div>
                <NIcon :size="14" class="user-chevron">
                  <ChevronDownOutline />
                </NIcon>
              </div>
            </NDropdown>
          </div>
        </div>
      </NLayoutSider>

      <!-- 移动端抽屉 -->
      <NDrawer v-model:show="mobileDrawerOpen" :width="260" placement="left" class="mobile-drawer">
        <NDrawerContent body-content-style="padding: 0">
          <div class="mobile-sider">
            <div class="mobile-logo">
              <NIcon :size="26" class="mobile-logo-icon">
                <Planet />
              </NIcon>
              <span class="mobile-logo-text">OmicHub</span>
            </div>
            <nav class="mobile-nav-group">
              <RouterLink
                v-for="item in mainNavItems"
                :key="item.key"
                :to="item.to"
                class="mobile-nav-item"
                :class="{ 'mobile-nav-item--active': isActive(item) }"
                @click="mobileDrawerOpen = false"
              >
                <NIcon :size="18">
                  <component :is="item.icon" />
                </NIcon>
                <span>{{ item.label }}</span>
              </RouterLink>
            </nav>
            <div class="nav-divider" />
            <nav class="mobile-nav-group">
              <RouterLink
                v-for="item in systemNavItems"
                :key="item.key"
                :to="item.to"
                class="mobile-nav-item"
                :class="{ 'mobile-nav-item--active': isActive(item) }"
                @click="mobileDrawerOpen = false"
              >
                <NIcon :size="18">
                  <component :is="item.icon" />
                </NIcon>
                <span>{{ item.label }}</span>
              </RouterLink>
            </nav>
            <template v-if="isAdmin">
              <div class="nav-divider" />
              <nav class="mobile-nav-group">
                <RouterLink
                  v-for="item in adminNavItems.flatMap((i) => i.children || [i])"
                  :key="item.key"
                  :to="item.to"
                  class="mobile-nav-item"
                  :class="{ 'mobile-nav-item--active': isActive(item) }"
                  @click="mobileDrawerOpen = false"
                >
                  <NIcon :size="18">
                    <component :is="item.icon" />
                  </NIcon>
                  <span>{{ item.label }}</span>
                </RouterLink>
              </nav>
            </template>
            <div class="mobile-user-card" @click="handleLogout">
              <UserAvatar />
              <div class="user-info">
                <p class="user-name">{{ currentUser?.username || '未登录' }}</p>
                <p class="user-role">{{ isAdmin ? '管理员' : '普通用户' }}</p>
              </div>
            </div>
          </div>
        </NDrawerContent>
      </NDrawer>

      <!-- 主内容区 -->
      <NLayout class="main-layout">
        <NLayoutContent
          content-style="padding: 24px; background: var(--neutral-bg);"
          :native-scrollbar="false"
        >
          <RouterView v-slot="{ Component }">
            <Transition name="route" mode="out-in">
              <component :is="Component" />
            </Transition>
          </RouterView>
        </NLayoutContent>
      </NLayout>
    </div>

    <NotificationDrawer v-model:show="notificationDrawerOpen" />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--neutral-bg);
}

/* ===== 顶部导航栏 ===== */
.top-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 16px;
  background: var(--neutral-card);
  border-bottom: 1px solid var(--neutral-border);
  flex-shrink: 0;
  z-index: 100;
}

.top-nav-left {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 100%;
}

.hamburger-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--neutral-text-2);
  border-radius: 6px;
}
.hamburger-btn:hover {
  background: var(--neutral-hover);
}

.logo-block {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  border-radius: 8px;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1);
}

.top-nav-divider {
  width: 1px;
  height: 20px;
  background: var(--neutral-border);
  margin: 0 8px;
}

.top-nav-menu {
  display: flex;
  align-items: center;
  height: 100%;
}

.top-nav-item {
  position: relative;
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 400;
  color: var(--neutral-text-2);
  text-decoration: none;
  transition: color 0.2s ease;
}

.top-nav-item:hover {
  color: var(--neutral-text-1);
}

.top-nav-item--active {
  color: var(--arco-primary);
  font-weight: 500;
}

.top-nav-indicator {
  position: absolute;
  bottom: 0;
  left: 16px;
  right: 16px;
  height: 2px;
  background: var(--arco-primary);
  border-radius: 1px;
}

.top-nav-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.top-icon-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--neutral-text-2);
  border-radius: 6px;
}
.top-icon-btn:hover {
  background: var(--neutral-hover);
}

/* ===== 主体 ===== */
.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.app-sider {
  background: var(--sidebar-bg) !important;
}

.sider-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px 12px 12px;
}

.sider-nav-groups {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-group-item {
  display: flex;
  flex-direction: column;
}

.nav-item {
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--neutral-text-2);
}

.nav-item:hover {
  background: var(--sidebar-hover);
  color: var(--neutral-text-1);
}

.nav-item--active {
  background: var(--sidebar-active);
  color: var(--sidebar-active-text);
  font-weight: 500;
}

.nav-item-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  padding: 0 12px;
}

.nav-item--collapsed .nav-item-inner {
  justify-content: center;
  padding: 0;
}

.nav-icon {
  flex-shrink: 0;
}

.nav-label {
  flex: 1;
  font-size: 14px;
  line-height: 22px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-chevron {
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.nav-chevron--expanded {
  transform: rotate(90deg);
}

/* 子菜单 */
.sub-nav {
  margin-left: 22px;
  padding-left: 12px;
  border-left: 1px solid var(--neutral-border);
  display: flex;
  flex-direction: column;
}

.sub-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--neutral-text-2);
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.sub-nav-item:hover {
  color: var(--neutral-text-1);
  background: var(--neutral-hover);
}

.sub-nav-item--active {
  color: var(--arco-primary);
  background: var(--arco-primary-light);
  font-weight: 500;
}

.sub-nav-icon {
  flex-shrink: 0;
}

.nav-divider {
  height: 1px;
  background: var(--neutral-border);
  margin: 12px 12px;
}

/* ===== 底部用户区 ===== */
.sider-footer {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--neutral-border);
}

.user-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.user-card:hover {
  background: var(--neutral-hover);
}

.user-info {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-1);
  line-height: 20px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: 12px;
  color: var(--neutral-text-3);
  line-height: 18px;
}

.user-chevron {
  color: var(--neutral-text-3);
  flex-shrink: 0;
}

.user-avatar-only {
  display: flex;
  justify-content: center;
  padding: 4px 0;
}

.user-avatar-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

/* ===== 移动端抽屉 ===== */
.mobile-sider {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
}

.mobile-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.mobile-logo-icon {
  color: var(--arco-primary);
}

.mobile-logo-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--neutral-text-1);
}

.mobile-nav-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mobile-nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  padding: 0 12px;
  font-size: 14px;
  color: var(--neutral-text-2);
  text-decoration: none;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.mobile-nav-item:hover {
  background: var(--neutral-hover);
  color: var(--neutral-text-1);
}

.mobile-nav-item--active {
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  font-weight: 500;
}

.mobile-user-card {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
  border-top: 1px solid var(--neutral-border);
}

.mobile-user-card:hover {
  background: var(--neutral-hover);
}

/* ===== 主内容区 ===== */
.main-layout {
  flex: 1;
  overflow: hidden;
  background: var(--neutral-bg);
}

/* 隐藏 Naive UI LayoutSider 默认 border 以使用自定义边框 */
:deep(.n-layout-sider) {
  background: var(--sidebar-bg);
}

:deep(.n-layout-sider .n-layout-sider-scroll-container) {
  border-right: 1px solid var(--sidebar-border);
}
</style>
