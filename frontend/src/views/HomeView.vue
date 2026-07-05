<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon } from 'naive-ui'
import {
  FlaskOutline, FitnessOutline, CloudUploadOutline, ChatbubblesOutline,
  DocumentTextOutline, CodeSlashOutline, RocketOutline, BarChartOutline,
  CheckmarkCircleOutline,
} from '@vicons/ionicons5'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import OmicBackgroundAnimation from '@/components/OmicBackgroundAnimation.vue'
import type { SiteContent } from '@/types/site-content'

// 默认文案兜底：API 拉取失败时保证首页仍可正常渲染
const DEFAULT_CONTENT: SiteContent = {
  hero: {
    title: '欢迎使用 OmicHub',
    description: '华中农业大学园艺林学学院私有化多组学分析平台。从数据上传、流程分析到结果交付，一站式完成您的组学研究。',
  },
  quick_entries: [
    { key: 'rna-seq', title: 'RNA-seq 分析', desc: '转录组差异表达分析' },
    { key: 'atac-seq', title: 'ATAC-seq 分析', desc: '染色质开放性分析' },
    { key: 'files', title: '数据管理', desc: '上传与管理样本数据' },
    { key: 'ai', title: 'AI 助手', desc: '智能分析与问答' },
    { key: 'tasks', title: '任务中心', desc: '查看分析任务进度' },
    { key: 'sandbox', title: '代码沙盒', desc: '在线编写分析脚本' },
  ],
  guide_steps: [
    { title: '上传样本数据', desc: '将 FASTQ / BAM 等原始数据上传至数据管理' },
    { title: '选择分析流程', desc: '在分析中心选择 RNA-seq 或 ATAC-seq 流程' },
    { title: '查看分析结果', desc: '任务完成后在报告中心查看与下载结果' },
  ],
}

// 快捷入口的图标 / 配色 / 路由按 key 硬编码（不进 yaml，避免组件与路由耦合）
const entryMeta: Record<string, { icon: any; iconBg: string; to: string }> = {
  'rna-seq': { icon: FlaskOutline, iconBg: 'blue', to: '/flows?type=rna-seq' },
  'atac-seq': { icon: FitnessOutline, iconBg: 'purple', to: '/flows?type=atac-seq' },
  'files': { icon: CloudUploadOutline, iconBg: 'cyan', to: '/files' },
  'ai': { icon: ChatbubblesOutline, iconBg: 'green', to: '/ai' },
  'tasks': { icon: DocumentTextOutline, iconBg: 'orange', to: '/tasks' },
  'sandbox': { icon: CodeSlashOutline, iconBg: 'teal', to: '/sandbox' },
}

const router = useRouter()
const authStore = useAuthStore()

// 展示名：优先昵称，未设置或为空则降级为用户名
const displayName = computed(() => authStore.user?.nickname || authStore.user?.username || '')
const isAdmin = computed(() => authStore.user?.role === 'admin')

// 根据当前时段返回问候语
const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

interface QuickEntry {
  key: string
  title: string
  desc: string
  icon: any
  iconBg: string
  to: string
}

const content = ref<SiteContent>(DEFAULT_CONTENT)

// 文案来自 yaml（title/desc），图标/路由按 key 合并
const quickEntries = computed<QuickEntry[]>(() =>
  content.value.quick_entries
    .filter((e) => entryMeta[e.key])
    .map((e) => ({ ...e, ...entryMeta[e.key] })),
)

const guideSteps = computed(() => content.value.guide_steps)

const bgColors: Record<string, string> = {
  blue: '#E8F3FF',
  purple: '#F0E8FF',
  cyan: '#E6FFFB',
  green: '#E8FFEA',
  orange: '#FFF2E8',
  teal: '#E8FFFA',
}

const iconColors: Record<string, string> = {
  blue: '#165DFF',
  purple: '#722ED1',
  cyan: '#14C9C9',
  green: '#00B42A',
  orange: '#F77234',
  teal: '#0FC6C2',
}

function goTo(path: string) {
  router.push(path)
}

onMounted(async () => {
  try {
    const res = await apiClient.get<SiteContent>('/site-content')
    content.value = res.data
  } catch {
    // 拉取失败保留默认文案，首页照常渲染
  }
})
</script>

<template>
  <div class="home-page">
    <!-- Hero 欢迎区 -->
    <section class="hero animate-fade-in-up">
      <OmicBackgroundAnimation context="hero" />
      <div class="hero-content">
        <p class="hero-greeting">{{ greeting }}{{ displayName ? '，' + displayName : '' }} 👋</p>
        <h1 class="hero-title">{{ content.hero.title }}</h1>
        <p class="hero-desc">
          {{ content.hero.description }}
        </p>
        <div class="hero-actions">
          <NButton type="primary" size="large" @click="goTo('/flows')">
            <template #icon>
              <NIcon><RocketOutline /></NIcon>
            </template>
            开始分析
          </NButton>
          <NButton size="large" class="hero-btn-secondary" @click="goTo('/dashboard')">
            <template #icon>
              <NIcon><BarChartOutline /></NIcon>
            </template>
            查看仪表板
          </NButton>
        </div>
      </div>
    </section>

    <!-- 快捷入口 -->
    <section class="section animate-fade-in-up delay-100">
      <h2 class="section-label">快捷入口</h2>
      <div class="entry-grid">
        <div
          v-for="entry in quickEntries"
          :key="entry.key"
          class="entry-card arco-card arco-card-hover"
          @click="goTo(entry.to)"
        >
          <div
            class="entry-icon"
            :style="{ background: bgColors[entry.iconBg], color: iconColors[entry.iconBg] }"
          >
            <NIcon :size="24">
              <component :is="entry.icon" />
            </NIcon>
          </div>
          <div class="entry-text">
            <h4 class="entry-title">{{ entry.title }}</h4>
            <p class="entry-desc">{{ entry.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 使用引导 -->
    <section class="section animate-fade-in-up delay-200">
      <h2 class="section-label">三步开始你的分析</h2>
      <div class="guide-grid">
        <div
          v-for="(step, index) in guideSteps"
          :key="step.title"
          class="guide-card arco-card"
        >
          <div class="guide-step">
            <span class="guide-number">{{ index + 1 }}</span>
            <NIcon v-if="index < guideSteps.length - 1" :size="16" class="guide-arrow">
              <CheckmarkCircleOutline />
            </NIcon>
          </div>
          <h4 class="guide-title">{{ step.title }}</h4>
          <p class="guide-desc">{{ step.desc }}</p>
        </div>
      </div>
    </section>

    <!-- 管理员入口 -->
    <section v-if="isAdmin" class="section animate-fade-in-up delay-200">
      <div class="admin-banner arco-card" @click="goTo('/admin/users')">
        <div class="admin-icon">
          <NIcon :size="20"><BarChartOutline /></NIcon>
        </div>
        <div class="admin-text">
          <h4 class="admin-title">系统管理</h4>
          <p class="admin-desc">用户、AI 模型、饼干账户与资源中心管理</p>
        </div>
        <NButton type="primary" size="small">进入管理</NButton>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-page {
  padding: 24px;
  min-height: 100%;
  background: var(--neutral-bg);
}

/* ===== Hero ===== */
.hero {
  position: relative;
  overflow: hidden;
  border-radius: 16px;
  padding: 40px 32px;
  margin-bottom: 24px;
  background: linear-gradient(135deg, #165DFF 0%, #6B8DD6 50%, #8E54E9 100%);
  color: #fff;
}

.hero-bg-icon {
  display: none;
}

.hero-content {
  position: relative;
  z-index: 2;
  max-width: 640px;
}

.hero-greeting {
  font-size: 14px;
  opacity: 0.9;
  margin: 0 0 8px;
}

.hero-title {
  font-size: 28px;
  font-weight: 600;
  line-height: 36px;
  margin: 0 0 12px;
}

.hero-desc {
  font-size: 14px;
  line-height: 22px;
  opacity: 0.85;
  margin: 0 0 24px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-btn-secondary {
  background: rgba(255, 255, 255, 0.2) !important;
  color: #fff !important;
  border: none !important;
}
.hero-btn-secondary:hover {
  background: rgba(255, 255, 255, 0.3) !important;
}

/* ===== 通用 section ===== */
.section {
  margin-bottom: 24px;
}

.section-label {
  font-size: 18px;
  font-weight: 600;
  line-height: 26px;
  color: var(--neutral-text-1);
  margin: 0 0 16px;
}

/* ===== 快捷入口 ===== */
.entry-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.entry-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.entry-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.3s ease;
}

.entry-card:hover .entry-icon {
  transform: scale(1.06);
}

.entry-text {
  min-width: 0;
}

.entry-title {
  font-size: 15px;
  font-weight: 500;
  line-height: 22px;
  color: var(--neutral-text-1);
  margin: 0 0 4px;
}

.entry-desc {
  font-size: 13px;
  line-height: 20px;
  color: var(--neutral-text-3);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== 使用引导 ===== */
.guide-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.guide-card {
  padding: 20px;
}

.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.guide-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

.guide-arrow {
  color: var(--neutral-text-4);
}

.guide-title {
  font-size: 15px;
  font-weight: 500;
  line-height: 22px;
  color: var(--neutral-text-1);
  margin: 0 0 6px;
}

.guide-desc {
  font-size: 13px;
  line-height: 20px;
  color: var(--neutral-text-3);
  margin: 0;
}

/* ===== 管理员入口 ===== */
.admin-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.admin-banner:hover {
  background: var(--neutral-hover);
}

.admin-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--arco-primary-light);
  color: var(--arco-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.admin-text {
  flex: 1;
  min-width: 0;
}

.admin-title {
  font-size: 15px;
  font-weight: 500;
  line-height: 22px;
  color: var(--neutral-text-1);
  margin: 0 0 4px;
}

.admin-desc {
  font-size: 13px;
  line-height: 20px;
  color: var(--neutral-text-3);
  margin: 0;
}

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .entry-grid,
  .guide-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .home-page {
    padding: 16px;
  }

  .hero {
    padding: 28px 20px;
  }

  .hero-title {
    font-size: 22px;
  }

  .entry-grid,
  .guide-grid {
    grid-template-columns: 1fr;
  }

  .admin-banner {
    flex-wrap: wrap;
  }
}
</style>