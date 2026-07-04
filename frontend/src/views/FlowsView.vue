<script setup lang="ts">
import type { FlowDefinition } from '@/types'
import { apiClient } from '@/api'
import { NButton, NIcon, useMessage } from 'naive-ui'
import { onMounted, ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  FlaskOutline, CodeSlashOutline, DocumentTextOutline,
} from '@vicons/ionicons5'

interface Pipeline {
  id: string
  name: string
  desc: string
  icon: string
  tags: string[]
  version: string
  isReady: boolean
}

const route = useRoute()
const router = useRouter()
const message = useMessage()
const flows = ref<FlowDefinition[]>([])
const loading = ref(false)

const pipelines = ref<Pipeline[]>([
  { id: 'rna_seq', name: 'RNA-seq 差异表达分析', desc: '适用于基因表达定量与差异分析，支持 DESeq2、edgeR 等多种算法。', icon: '🧬', tags: ['转录组', '热门'], version: '2.1', isReady: true },
  { id: 'atac_seq', name: 'ATAC-seq 开放区域检测', desc: '基于 Tn5 转座酶的染色质可及性分析，自动调用 MACS2 与 DiffBind。', icon: '🔬', tags: ['表观遗传', '自动化'], version: '1.4', isReady: true },

  // ── 占位符：单细胞与空间组学 ──
  { id: 'sc-rna', name: '单细胞转录组分析', desc: '支持 10x Genomics 数据，包含降维聚类、细胞注释及拟时序分析。', icon: '🧫', tags: ['单细胞', 'Seurat'], version: '0.9', isReady: false },
  { id: 'spatial', name: '空间转录组分析', desc: '10x Visium / Slide-seq 数据的空间基因表达定位与域识别。', icon: '🗺️', tags: ['空间组学', 'Visium'], version: '0.5', isReady: false },

  // ── 占位符：免疫组学 ──
  { id: 'vdj', name: 'VDJ 免疫组库分析', desc: 'T/B 细胞受体多样性分析及克隆型追踪。', icon: '🛡️', tags: ['免疫组', '克隆型'], version: '0.3', isReady: false },

  // ── 占位符：群体遗传与育种 ──
  { id: 'bsa', name: 'BSA 性状定位分析', desc: '基于极端混池测序的突变基因快速定位。', icon: '🌾', tags: ['群体遗传', 'QTL'], version: '0.4', isReady: false },
  { id: 'bsr', name: 'BSR 转录组混池分析', desc: '结合 RNA-seq 的混池分离分析，定位与表达同时获取。', icon: '🌱', tags: ['转录组', '性状定位'], version: '0.3', isReady: false },
  { id: 'gwas', name: 'GWAS 全基因组关联分析', desc: '大规模群体变异与表型关联性分析。', icon: '📊', tags: ['群体遗传', '变异'], version: '0.6', isReady: false },

  // ── 占位符：重测序 ──
  { id: 'wes', name: 'WES 全外显子测序', desc: '外显子区域变异检测及临床级注释。', icon: '🎯', tags: ['变异检测', '临床'], version: '0.5', isReady: false },
  { id: 'wgs', name: 'WGS 全基因组测序', desc: '全基因组结构变异、CNV 及深度变异检测。', icon: '🧬', tags: ['基因组', '重测序'], version: '0.7', isReady: false },

  // ── 占位符：高级调控组学 ──
  { id: 'ribo-seq', name: 'Ribo-seq 翻译组分析', desc: '核糖体图谱分析，精准评估基因翻译效率。', icon: '⚙️', tags: ['翻译组', '调控'], version: '0.2', isReady: false },
  { id: 'cut-tag', name: 'CUT&Tag 蛋白质互作', desc: '高效绘制组蛋白修饰和转录因子结合图谱。', icon: '🧲', tags: ['表观遗传', '互作'], version: '0.3', isReady: false },

  // ── 占位符：表观遗传进阶 ──
  { id: 'chip-seq', name: 'ChIP-seq 峰注释分析', desc: '组蛋白修饰与转录因子 ChIP 富集峰鉴定、motif 扫描与差异结合分析。', icon: '📍', tags: ['表观遗传', 'TF 结合'], version: '0.8', isReady: false },
  { id: 'hic', name: 'Hi-C 三维基因组分析', desc: '染色质空间构象捕获，TAD 划分、Loop 鉴定与区室分析。', icon: '🌀', tags: ['三维基因组', '染色质'], version: '0.5', isReady: false },
  { id: 'methylation', name: 'DNA 甲基化分析', desc: 'WGBS / RRBS 全基因组甲基化图谱，DMR 鉴定与功能注释。', icon: '🔖', tags: ['表观遗传', '甲基化'], version: '0.6', isReady: false },

  // ── 占位符：微生物组 ──
  { id: '16s-amplicon', name: '16S/ITS 扩增子分析', desc: 'V3-V4 等可变区物种组成、Alpha/Beta 多样性与差异物种筛选。', icon: '🦠', tags: ['微生物', '扩增子'], version: '1.2', isReady: false },
  { id: 'metagenomics', name: '宏基因组组装分析', desc: '鸟枪法宏基因组物种注释、功能通路富集与 MAG 分箱。', icon: '🧪', tags: ['微生物', '宏基因组'], version: '0.7', isReady: false },

  // ── 占位符：蛋白质组与代谢组 ──
  { id: 'proteomics', name: '蛋白质组定量分析', desc: 'TMT / Label-free 标记定量，差异蛋白筛选与 GO/KEGG 富集。', icon: '🔩', tags: ['蛋白质组', '定量'], version: '0.4', isReady: false },
  { id: 'metabolomics', name: '非靶向代谢组分析', desc: 'LC-MS / GC-MS 代谢物鉴定、PCA-PLS-DA 与差异代谢物筛选。', icon: '⚗️', tags: ['代谢组', '非靶向'], version: '0.5', isReady: false },

  // ── 占位符：多组学联合 ──
  { id: 'multi-omics', name: '多组学联合分析', desc: '转录组 + 蛋白质组 + 代谢组的多层数据整合与通路联动。', icon: '🔗', tags: ['多组学', '整合'], version: '0.3', isReady: false },

  // ── 占位符：基因组组装 ──
  { id: 'denovo-assembly', name: 'De novo 基因组组装', desc: 'PacBio HiFi + ONT + Hi-C 三代联合组装，BUSCO 评估与染色体挂载。', icon: '🏗️', tags: ['基因组', '组装'], version: '0.6', isReady: false },
])

async function fetchFlows() {
  loading.value = true
  try {
    const res = await apiClient.get<{ items: FlowDefinition[]; total: number }>('/flows')
    flows.value = res.data.items
  } finally {
    loading.value = false
  }
}

const activeType = computed(() => (route.query.type as string) || '')

const typeLabels: Record<string, string> = {
  'rna-seq': 'RNA-seq 分析',
  'atac-seq': 'ATAC-seq 分析',
  'sc-rna': '单细胞分析',
  'spatial': '空间转录组',
  'chip-seq': 'ChIP-seq 分析',
  'hic': 'Hi-C 三维基因组',
  'methylation': '甲基化分析',
  '16s-amplicon': '扩增子分析',
  'metagenomics': '宏基因组分析',
  'proteomics': '蛋白质组分析',
  'metabolomics': '代谢组分析',
  'multi-omics': '多组学联合',
  'denovo-assembly': '基因组组装',
  'wgs': '全基因组测序',
  'wes': '全外显子测序',
  'gwas': 'GWAS 分析',
}

const filteredPipelines = computed(() => {
  if (!activeType.value) return pipelines.value
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const target = norm(activeType.value)
  return pipelines.value.filter((p) => {
    const key = norm(`${p.id} ${p.tags.join(' ')}`)
    return key.includes(target)
  })
})

const featuredPipeline = computed(() =>
  filteredPipelines.value.find((p) => p.id === 'rna_seq' && p.isReady) || filteredPipelines.value.find((p) => p.isReady),
)

const gridPipelines = computed(() => {
  if (activeType.value) return filteredPipelines.value
  return filteredPipelines.value.filter((p) => p.id !== featuredPipeline.value?.id)
})

function handleCardClick(p: Pipeline) {
  if (!p.isReady) {
    message.info(`「${p.name}」正在紧锣密鼓研发中，敬请期待！`)
    return
  }
  router.push({ name: 'flow-submit', params: { flowId: p.id } })
}

watch(() => route.query.type, fetchFlows)
onMounted(fetchFlows)
</script>

<template>
  <div class="flows-page">
    <!-- Header -->
    <div class="flows-header animate-fade-in-up">
      <div>
        <h1 class="page-title" style="margin-bottom: 8px;">{{ activeType ? (typeLabels[activeType] || '分析流程') : '分析中心' }}</h1>
        <p class="page-subtitle">
          {{ activeType ? '当前筛选的分析流程，点击卡片即可提交任务' : '选择适合您研究需求的分析流程，快速启动多组学分析' }}
        </p>
      </div>
      <div class="flows-header-actions">
        <NButton v-if="activeType" class="header-btn-secondary" @click="router.push('/flows')">
          查看全部流程
        </NButton>
        <NButton class="header-btn-secondary">
          <template #icon><component :is="CodeSlashOutline" /></template>
          Github 开源代码
        </NButton>
        <NButton class="header-btn-secondary">
          <template #icon><component :is="DocumentTextOutline" /></template>
          开发者文档
        </NButton>
      </div>
    </div>

    <!-- 推荐流程 -->
    <section v-if="!activeType && featuredPipeline" class="featured-section animate-fade-in-up delay-100">
      <h2 class="section-label">
        <span class="section-icon">🔥</span>
        推荐流程
      </h2>
      <div class="featured-card" @click="handleCardClick(featuredPipeline)">
        <div class="featured-bg-icon">
          <component :is="FlaskOutline" :size="160" />
        </div>
        <div class="featured-tags">
          <span v-for="tag in featuredPipeline.tags" :key="tag" class="featured-tag">{{ tag }}</span>
        </div>
        <h3 class="featured-title">{{ featuredPipeline.name }}</h3>
        <p class="featured-desc">{{ featuredPipeline.desc }}</p>
      </div>
    </section>

    <!-- 全部流程（数据驱动网格） -->
    <section class="all-flows-section animate-fade-in-up delay-200">
      <h2 class="section-label">
        <span class="section-icon">📋</span>
        {{ activeType ? '筛选结果' : '全部流程' }}
      </h2>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        <div
          v-for="p in gridPipelines"
          :key="p.id"
          class="relative bg-neutral-card rounded-xl border border-gray-100 shadow-sm p-5 flex flex-col transition-all duration-200"
          :class="p.isReady
            ? 'hover:shadow-lg hover:-translate-y-0.5 cursor-pointer hover:border-blue-200'
            : 'opacity-60 grayscale-[20%] cursor-not-allowed'"
          @click="handleCardClick(p)"
        >
          <!-- 研发中角标 -->
          <span
            v-if="!p.isReady"
            class="absolute top-3 right-3 text-[10px] font-medium text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full"
          >
            研发中
          </span>

          <!-- 图标 -->
          <div
            class="w-11 h-11 rounded-xl flex items-center justify-center text-xl mb-3.5"
            :class="p.isReady ? 'bg-blue-50' : 'bg-gray-50'"
          >
            {{ p.icon }}
          </div>

          <!-- 名称 -->
          <h4 class="text-[15px] font-semibold text-gray-800 mb-1.5 leading-snug">{{ p.name }}</h4>

          <!-- 简介 -->
          <p class="text-xs text-gray-400 leading-relaxed mb-4 flex-1 line-clamp-2">{{ p.desc }}</p>

          <!-- 底部：标签 + 版本 -->
          <div class="flex items-center flex-wrap gap-1.5 mt-auto">
            <span
              v-for="tag in p.tags"
              :key="tag"
              class="text-[11px] px-2 py-0.5 rounded-full font-medium"
              :class="p.isReady ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-400'"
            >
              {{ tag }}
            </span>
            <span
              class="text-[11px] font-mono ml-auto px-1.5 py-0.5 rounded"
              :class="p.isReady ? 'bg-gray-50 text-gray-400' : 'bg-gray-50 text-gray-300'"
            >
              v{{ p.version }}
            </span>
          </div>
        </div>
      </div>
    </section>
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
  margin: 0;
}

.all-flows-section {
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .flows-header {
    flex-direction: column;
  }
  .flows-header-actions {
    width: 100%;
  }
}
</style>
