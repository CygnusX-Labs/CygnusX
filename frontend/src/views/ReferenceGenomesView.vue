<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NInput, NSelect, NTag, useMessage } from 'naive-ui'
import { SearchOutline, ArrowForwardOutline, CheckmarkCircleOutline } from '@vicons/ionicons5'
import { MOCK_GENOMES, type Genome } from '@/mock/referenceGenomes'

const router = useRouter()
const message = useMessage()

/** 本地维护默认基因组（mock，后续接后端）。 */
const genomes = ref<Genome[]>(MOCK_GENOMES.map((g) => ({ ...g })))
const searchQuery = ref('')
const speciesFilter = ref('lettuce')
const sortBy = ref('default')

const speciesOptions = [
  { label: '🥬 生菜', value: 'lettuce' },
  { label: '🍅 番茄（敬请期待）', value: 'tomato', disabled: true },
  { label: '🌾 水稻（敬请期待）', value: 'rice', disabled: true },
]
const sortOptions = [
  { label: '默认', value: 'default' },
  { label: '按基因数', value: 'genes' },
  { label: '按发布日期', value: 'date' },
]

const filteredGenomes = computed(() => {
  let list = genomes.value.filter((g) => {
    if (speciesFilter.value === 'lettuce' && g.commonName !== '生菜') return false
    return true
  })
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((g) =>
      [g.commonName, g.latinName, g.version, g.versionFull, ...g.tags].some((s) => s.toLowerCase().includes(q)),
    )
  }
  if (sortBy.value === 'genes') list = [...list].sort((a, b) => b.totalGenes - a.totalGenes)
  if (sortBy.value === 'date') list = [...list].sort((a, b) => b.releaseDate.localeCompare(a.releaseDate))
  return list
})

function tagType(tag: string): 'success' | 'info' | 'warning' {
  if (tag.includes('最新')) return 'success'
  if (tag.includes('稳定')) return 'info'
  return 'warning'
}

function viewDetail(g: Genome) {
  router.push(`/reference-genomes/${g.id}`)
}

function setDefault(g: Genome) {
  genomes.value = genomes.value.map((x) => ({ ...x, isDefault: x.id === g.id }))
  message.success(`已将 ${g.commonName} ${g.version} 设为项目默认参考基因组`)
}
</script>

<template>
  <div class="genomes-page">
    <!-- Hero -->
    <div class="hero">
      <div class="hero-content">
        <h1 class="hero-title">🧬 参考基因组库</h1>
        <p class="hero-subtitle">预置基因组与注释，让比对与注释一步到位</p>
      </div>
      <svg class="hero-deco" viewBox="0 0 120 160" fill="none" aria-hidden="true">
        <path d="M30 10 Q60 40 30 80 Q60 120 30 150" stroke="rgba(255,255,255,0.25)" stroke-width="3" fill="none" />
        <path d="M90 10 Q60 40 90 80 Q60 120 90 150" stroke="rgba(255,255,255,0.25)" stroke-width="3" fill="none" />
        <line v-for="y in [25, 45, 65, 85, 105, 125, 145]" :key="y" :x1="32" :x2="88" :y1="y" :y2="y" stroke="rgba(255,255,255,0.15)" stroke-width="2" />
      </svg>
    </div>

    <!-- 搜索与筛选栏 -->
    <div class="filter-bar">
      <NSelect
        v-model:value="speciesFilter"
        :options="speciesOptions"
        size="small"
        style="width: 160px"
      />
      <NInput
        v-model:value="searchQuery"
        size="small"
        clearable
        placeholder="搜索物种、版本、关键词..."
        style="flex: 1; max-width: 420px"
      >
        <template #prefix><NIcon><SearchOutline /></NIcon></template>
      </NInput>
      <NSelect
        v-model:value="sortBy"
        :options="sortOptions"
        size="small"
        style="width: 140px"
      />
    </div>

    <!-- 卡片网格 -->
    <div v-if="filteredGenomes.length" class="genome-grid">
      <div
        v-for="g in filteredGenomes"
        :key="g.id"
        class="genome-card"
        :class="{ 'is-default': g.isDefault }"
      >
        <div class="card-header">
          <span class="species-emoji">{{ g.speciesEmoji }}</span>
          <div class="species-info">
            <div class="species-name">{{ g.commonName }}</div>
            <div class="species-latin">{{ g.latinName }}</div>
          </div>
          <NTag v-if="g.isDefault" size="tiny" type="success" round>默认</NTag>
        </div>

        <div class="version-box">
          <div class="version-row">
            <span class="version-text">{{ g.version }}</span>
            <NTag
              v-for="t in g.tags"
              :key="t"
              size="tiny"
              :type="tagType(t)"
              round
            >{{ t }}</NTag>
          </div>
          <div class="version-full">{{ g.versionFull }}</div>
        </div>

        <div class="card-stats">
          <div class="stat-line">🧬 {{ g.chromosomes }} 条染色体 · {{ g.totalGenes.toLocaleString() }} 基因</div>
          <div class="stat-line">📦 {{ g.genomeSize }} · {{ g.releaseDate }} 发布</div>
        </div>

        <div class="card-actions">
          <NButton size="small" type="primary" @click="viewDetail(g)">
            查看详情
            <template #icon><NIcon><ArrowForwardOutline /></NIcon></template>
          </NButton>
          <NButton
            size="small"
            :disabled="g.isDefault"
            @click="setDefault(g)"
          >
            <template #icon><NIcon><CheckmarkCircleOutline /></NIcon></template>
            设为默认
          </NButton>
        </div>

        <div class="card-gradient-bar" :style="{ background: g.gradient }" />
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <p class="empty-icon">🧬</p>
      <p>暂无基因组数据，请联系管理员预置</p>
    </div>
  </div>
</template>

<style scoped>
.genomes-page {
  min-height: 100%;
}
.hero {
  position: relative;
  height: 140px;
  background: linear-gradient(135deg, #3b82f6 0%, #7c3aed 100%);
  border-radius: 12px;
  padding: 28px 32px;
  display: flex;
  align-items: center;
  overflow: hidden;
  margin-bottom: 16px;
}
.hero-content {
  position: relative;
  z-index: 1;
}
.hero-title {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  margin: 0 0 6px;
}
.hero-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.85);
  margin: 0;
}
.hero-deco {
  position: absolute;
  right: 32px;
  top: 50%;
  transform: translateY(-50%);
  width: 120px;
  height: 160px;
  opacity: 0.6;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.genome-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.genome-card {
  position: relative;
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: all 0.3s ease;
  overflow: hidden;
}
.genome-card:hover {
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.12);
  transform: translateY(-2px);
  border-color: rgba(124, 58, 237, 0.3);
}
.genome-card.is-default {
  border-color: rgba(34, 197, 94, 0.4);
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.species-emoji {
  font-size: 28px;
}
.species-info {
  flex: 1;
  min-width: 0;
}
.species-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1, #1e293b);
}
.species-latin {
  font-size: 12px;
  color: var(--neutral-text-3, #94a3b8);
  font-style: italic;
}
.version-box {
  background: var(--neutral-bg, #f8fafc);
  border-radius: 8px;
  padding: 12px;
}
.version-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.version-text {
  font-size: 24px;
  font-weight: 700;
  color: var(--neutral-text-1, #1e293b);
}
.version-full {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: var(--neutral-text-3, #94a3b8);
}
.card-stats {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stat-line {
  font-size: 13px;
  color: var(--neutral-text-2, #475569);
}
.card-actions {
  display: flex;
  gap: 8px;
}
.card-gradient-bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
}
.empty-state {
  padding: 80px 24px;
  text-align: center;
  color: var(--neutral-text-3, #94a3b8);
}
.empty-icon {
  font-size: 48px;
  margin: 0 0 8px;
}
@media (max-width: 1024px) {
  .genome-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .genome-grid { grid-template-columns: 1fr; }
  .hero { height: 120px; padding: 20px; }
  .hero-deco { display: none; }
}
</style>
