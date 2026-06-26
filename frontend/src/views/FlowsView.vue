<script setup lang="ts">
import type { FlowDefinition } from '@/types'
import { apiClient } from '@/api'
import { NButton, NEmpty, NSpin, NTag } from 'naive-ui'
import { onMounted, ref, computed, h, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  FlaskOutline, FitnessOutline, GlobeOutline, BugOutline,
  GridOutline, BookOutline, BeakerOutline, ExtensionPuzzleOutline,
  PeopleOutline, StarOutline, CodeSlashOutline, DocumentTextOutline,
} from '@vicons/ionicons5'

const route = useRoute()
const router = useRouter()
const flows = ref<FlowDefinition[]>([])
const loading = ref(false)

async function fetchFlows() {
  loading.value = true
  try {
    const res = await apiClient.get<{ items: FlowDefinition[]; total: number }>('/flows')
    flows.value = res.data.items
  } finally {
    loading.value = false
  }
}

// 当前选中的分析类型（来自 /flows?type=xxx）
const activeType = computed(() => (route.query.type as string) || '')

const typeLabels: Record<string, string> = {
  'rna-seq': 'RNA-seq 分析',
  'atac-seq': 'ATAC-seq 分析',
  'chip-seq': 'ChIP-seq 分析',
  'scrna': '单细胞分析',
  'wgs': '全基因组测序',
  'metagenome': '宏基因组分析',
}

// 按类型过滤（匹配 flow.id 或 category 中包含该前缀）
const filteredFlows = computed(() => {
  if (!activeType.value) return flows.value
  return flows.value.filter((f) => {
    const key = `${f.id} ${f.category || ''}`.toLowerCase()
    return key.includes(activeType.value.replace('-', ''))
      || key.includes(activeType.value)
  })
})

function goToSubmit(flowId: string) {
  router.push({ name: 'flow-submit', params: { flowId } })
}

const flowMeta: Record<string, { icon: any; iconBg: string; tags: string[] }> = {
  'rna-seq': { icon: FlaskOutline, iconBg: 'blue', tags: ['转录组', '热门'] },
  'atac-seq': { icon: FitnessOutline, iconBg: 'purple', tags: ['表观遗传', '自动化'] },
  'chip-seq': { icon: FlaskOutline, iconBg: 'indigo', tags: ['表观遗传'] },
  'scrna': { icon: GridOutline, iconBg: 'green', tags: ['单细胞'] },
  'wgs': { icon: GlobeOutline, iconBg: 'cyan', tags: ['基因组'] },
  'wgbs': { icon: BookOutline, iconBg: 'amber', tags: ['表观遗传'] },
  'metagenome': { icon: BugOutline, iconBg: 'orange', tags: ['微生物'] },
  'metabolome': { icon: BeakerOutline, iconBg: 'rose', tags: ['代谢组'] },
  'proteome': { icon: ExtensionPuzzleOutline, iconBg: 'teal', tags: ['蛋白质组'] },
}

const bgColors: Record<string, string> = {
  blue: '#E8F3FF',
  purple: '#F0E8FF',
  indigo: '#EEF2FF',
  green: '#E8FFEA',
  cyan: '#E6FFFB',
  amber: '#FFF7E8',
  orange: '#FFF2E8',
  rose: '#FFF0F3',
  teal: '#E8FFFA',
}

const iconColors: Record<string, string> = {
  blue: '#165DFF',
  purple: '#722ED1',
  indigo: '#4F6EF7',
  green: '#00B42A',
  cyan: '#14C9C9',
  amber: '#FF7D00',
  orange: '#F77234',
  rose: '#F53F3F',
  teal: '#0FC6C2',
}

function getFlowMeta(flow: FlowDefinition) {
  const key = flow.id.toLowerCase()
  for (const [prefix, meta] of Object.entries(flowMeta)) {
    if (key.includes(prefix)) return meta
  }
  return { icon: FlaskOutline, iconBg: 'blue', tags: [flow.category || '分析流程'] }
}

const featuredFlow = computed(() => {
  return filteredFlows.value.find((f) => f.id.toLowerCase().includes('rna')) || filteredFlows.value[0]
})

const normalFlows = computed(() => {
  if (activeType.value) return filteredFlows.value
  return filteredFlows.value.filter((f) => f.id !== featuredFlow.value?.id)
})

watch(() => route.query.type, fetchFlows)
onMounted(fetchFlows)
</script>

<template>
  <div class="flows-page">
    <!-- Header -->
    <div class="flows-header animate-fade-in-up">
      <div>
        <h1 class="page-title" style="margin-bottom: 8px;">{{ activeType ? (typeLabels[activeType] || '分析流程') : '分析流程中心' }}</h1>
        <p class="page-subtitle">
          {{ activeType ? '当前筛选的分析流程，点击卡片即可提交任务' : '选择适合您研究需求的分析流程，快速启动多组学分析' }}
        </p>
      </div>
      <div class="flows-header-actions">
        <NButton v-if="activeType" class="header-btn-secondary" @click="router.push('/flows')">
          查看全部流程
        </NButton>
        <NButton class="header-btn-secondary">
          <template #icon>
            <component :is="CodeSlashOutline" />
          </template>
          Github 开源代码
        </NButton>
        <NButton class="header-btn-secondary">
          <template #icon>
            <component :is="DocumentTextOutline" />
          </template>
          开发者文档
        </NButton>
      </div>
    </div>

    <NSpin :show="loading">
      <template v-if="filteredFlows.length > 0">
        <!-- 推荐流程（按类型筛选时不展示推荐区，直接全部以卡片展示） -->
        <section v-if="!activeType && featuredFlow" class="featured-section animate-fade-in-up delay-100">
          <h2 class="section-label">
            <span class="section-icon">🔥</span>
            推荐流程
          </h2>
          <div class="featured-card" @click="featuredFlow && goToSubmit(featuredFlow.id)">
            <div class="featured-bg-icon">
              <component :is="FlaskOutline" :size="160" />
            </div>
            <div class="featured-tags">
              <span class="featured-tag">热门</span>
              <span class="featured-tag">转录组</span>
            </div>
            <h3 class="featured-title">{{ featuredFlow?.name || 'RNA-seq 差异表达分析' }}</h3>
            <p class="featured-desc">
              {{ featuredFlow?.description || '适用于基因表达定量与差异分析，支持 DESeq2、edgeR 等多种算法' }}
            </p>
            <div class="featured-meta">
              <span class="featured-meta-item">
                <component :is="PeopleOutline" :size="14" />
                1,234 次使用
              </span>
              <span class="featured-meta-item">
                <component :is="StarOutline" :size="14" />
                4.9 评分
              </span>
            </div>
          </div>
        </section>

        <!-- 全部流程 -->
        <section class="all-flows-section animate-fade-in-up delay-200">
          <h2 class="section-label">
            <span class="section-icon">📋</span>
            {{ activeType ? '筛选结果' : '全部流程' }}
          </h2>
          <div class="flow-grid">
            <div
              v-for="flow in normalFlows"
              :key="flow.id"
              class="flow-card arco-card arco-card-hover"
              @click="goToSubmit(flow.id)"
            >
              <div
                class="flow-icon"
                :style="{
                  background: bgColors[getFlowMeta(flow).iconBg],
                  color: iconColors[getFlowMeta(flow).iconBg],
                }"
              >
                <component :is="getFlowMeta(flow).icon" :size="26" />
              </div>
              <h4 class="flow-name">{{ flow.name }}</h4>
              <p class="flow-desc">{{ flow.description }}</p>
              <div class="flow-tags">
                <span
                  v-for="tag in getFlowMeta(flow).tags"
                  :key="tag"
                  class="arco-tag"
                  :class="`arco-tag-${getFlowMeta(flow).iconBg === 'blue' ? 'primary' : 'gray'}`"
                >
                  {{ tag }}
                </span>
                <NTag size="small" round type="info">v{{ flow.version }}</NTag>
              </div>
            </div>
          </div>
        </section>
      </template>

      <NEmpty v-else>
        <template #default>
          <div style="text-align: center;">
            <p>{{ activeType ? '该类型暂无可用流程' : '暂无可用流程' }}</p>
            <p style="font-size: 13px; color: var(--neutral-text-3); margin-top: 8px;">
              {{ activeType ? '请尝试查看全部流程，或联系管理员添加该类型流程' : '请联系管理员配置分析流程，或查看开发者文档' }}
            </p>
          </div>
        </template>
      </NEmpty>
    </NSpin>
  </div>
</template>

<style scoped>
.flows-page {
  padding: 24px;
  min-height: 100%;
  background: var(--neutral-bg);
}

.flows-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.flows-header-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.header-btn-secondary {
  color: var(--neutral-text-2) !important;
  border-color: var(--neutral-border) !important;
  background: #fff !important;
}
.header-btn-secondary:hover {
  background: var(--neutral-hover) !important;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  line-height: 26px;
  color: var(--neutral-text-1);
  margin: 0 0 16px;
}

.section-icon {
  font-size: 20px;
}

.featured-section {
  margin-bottom: 32px;
}

.featured-card {
  position: relative;
  overflow: hidden;
  border-radius: 16px;
  padding: 24px;
  min-height: 180px;
  background: linear-gradient(135deg, #165DFF 0%, #6B8DD6 50%, #8E54E9 100%);
  color: #fff;
  cursor: pointer;
  transition: all 0.3s ease;
}

.featured-card:hover {
  box-shadow: 0 12px 32px rgba(22, 93, 255, 0.25);
  transform: translateY(-2px);
}

.featured-bg-icon {
  position: absolute;
  top: -20px;
  right: -20px;
  width: 180px;
  height: 180px;
  opacity: 0.15;
  transform: rotate(12deg);
  pointer-events: none;
}

.featured-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  position: relative;
  z-index: 1;
}

.featured-tag {
  padding: 3px 10px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.2);
  font-size: 12px;
  font-weight: 500;
}

.featured-title {
  position: relative;
  z-index: 1;
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 8px;
}

.featured-desc {
  position: relative;
  z-index: 1;
  font-size: 14px;
  line-height: 22px;
  opacity: 0.85;
  max-width: 480px;
  margin: 0 0 16px;
}

.featured-meta {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 16px;
  font-size: 12px;
  opacity: 0.8;
}

.featured-meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.all-flows-section {
  margin-bottom: 24px;
}

.flow-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.flow-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.flow-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  transition: all 0.3s ease;
}

.flow-card:hover .flow-icon {
  transform: scale(1.05);
}

.flow-name {
  font-size: 16px;
  font-weight: 500;
  line-height: 24px;
  color: var(--neutral-text-1);
  margin: 0 0 6px;
}

.flow-desc {
  font-size: 13px;
  line-height: 20px;
  color: var(--neutral-text-3);
  margin: 0 0 16px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.flow-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: auto;
}

/* 响应式 */
@media (max-width: 1024px) {
  .flow-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .flows-header {
    flex-direction: column;
  }

  .flows-header-actions {
    width: 100%;
  }

  .flow-grid {
    grid-template-columns: 1fr;
  }
}
</style>
