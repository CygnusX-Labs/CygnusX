<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NEmpty, NIcon, NInput, NSelect, NTag, useMessage } from 'naive-ui'
import {
  AddOutline,
  ArrowForwardOutline,
  CheckmarkCircleOutline,
  LayersOutline,
  SearchOutline,
} from '@vicons/ionicons5'
import {
  DATABASE_SPECIES,
  getDataFileEntries,
  getDatabaseSummary,
  getDefaultGenomeVersion,
  getSpeciesBuildStatus,
  type BuildStatus,
  type DataFileType,
  type GenomeVersion,
  type SpeciesDatabase,
} from '@/mock/referenceGenomes'

const router = useRouter()
const message = useMessage()

const searchQuery = ref('')
const categoryFilter = ref<'all' | 'plant' | 'animal' | 'microbe'>('all')
const statusFilter = ref<'all' | BuildStatus>('all')
const sortBy = ref<'default' | 'species' | 'genes' | 'versions'>('default')
const defaultVersionBySpecies = ref<Record<string, string>>(
  Object.fromEntries(DATABASE_SPECIES.map((species) => [species.id, getDefaultGenomeVersion(species).versionId])),
)

const categoryOptions = [
  { label: '全部分类', value: 'all' },
  { label: '植物', value: 'plant' },
  { label: '动物', value: 'animal' },
  { label: '微生物', value: 'microbe' },
]

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '就绪', value: 'ready' },
  { label: '构建中', value: 'building' },
  { label: '缺失文件', value: 'missing' },
  { label: '异常', value: 'error' },
]

const sortOptions = [
  { label: '默认排序', value: 'default' },
  { label: '按物种名称', value: 'species' },
  { label: '按基因数量', value: 'genes' },
  { label: '按版本数量', value: 'versions' },
]

const sourceOrder: DataFileType[] = ['fasta', 'gff', 'go', 'kegg']
const sourceLabel: Record<DataFileType, string> = {
  fasta: 'FA',
  gff: 'GFF',
  go: 'GO',
  kegg: 'KEGG',
}

const summary = computed(() => getDatabaseSummary())

const filteredSpecies = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  let list = DATABASE_SPECIES.filter((species) => {
    if (categoryFilter.value !== 'all' && species.category !== categoryFilter.value) return false
    const status = getSpeciesBuildStatus(species)
    if (statusFilter.value !== 'all' && status !== statusFilter.value) return false
    if (!query) return true
    return [
      species.commonName,
      species.scientificName,
      species.taxonomyId,
      species.description,
      ...species.genomeVersions.flatMap((version) => [version.versionName, version.assemblyName, ...version.tags]),
    ].some((value) => value.toLowerCase().includes(query))
  })

  if (sortBy.value === 'species') {
    list = [...list].sort((a, b) => a.scientificName.localeCompare(b.scientificName))
  }
  if (sortBy.value === 'genes') {
    list = [...list].sort((a, b) => countGenes(b) - countGenes(a))
  }
  if (sortBy.value === 'versions') {
    list = [...list].sort((a, b) => b.genomeVersions.length - a.genomeVersions.length)
  }
  return list
})

function countGenes(species: SpeciesDatabase) {
  return species.genomeVersions.reduce((sum, version) => sum + version.stats.totalGenes, 0)
}

function countReadyFiles(species: SpeciesDatabase) {
  return species.genomeVersions
    .flatMap(getDataFileEntries)
    .filter((file) => file.buildStatus === 'ready').length
}

function effectiveDefaultVersion(species: SpeciesDatabase) {
  return species.genomeVersions.find((version) => version.versionId === defaultVersionBySpecies.value[species.id])
    ?? getDefaultGenomeVersion(species)
}

function versionStatusType(status: BuildStatus): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (status === 'ready') return 'success'
  if (status === 'building') return 'warning'
  if (status === 'error') return 'error'
  if (status === 'missing') return 'default'
  return 'info'
}

function statusText(status: BuildStatus) {
  if (status === 'ready') return '就绪'
  if (status === 'building') return '构建中'
  if (status === 'missing') return '缺失'
  return '异常'
}

function fileEnabled(version: GenomeVersion, type: DataFileType) {
  return version.dataFiles[type]?.buildStatus === 'ready'
}

function openVersion(version: GenomeVersion) {
  router.push(`/database/${version.versionId}`)
}

function setDefault(species: SpeciesDatabase, version: GenomeVersion) {
  defaultVersionBySpecies.value = { ...defaultVersionBySpecies.value, [species.id]: version.versionId }
  message.success(`已将 ${species.commonName} ${version.versionName} 设为默认数据库版本`)
}

function openRegisterDialog() {
  message.info('数据库注册当前通过 YAML 配置接入：编辑 databases.yaml / jbrowse_config.yaml 后热重载')
}
</script>

<template>
  <div class="database-page">
    <section class="database-hero">
      <div class="hero-copy">
        <div class="hero-kicker">
          <NIcon :size="16"><LayersOutline /></NIcon>
          Gene-Centric Database
        </div>
        <h1>数据库</h1>
        <p>集中管理 FA、GFF、GO、KEGG 与跨版本基因映射。</p>
      </div>
      <div class="hero-actions">
        <NButton type="primary" secondary class="register-button" @click="openRegisterDialog">
          <template #icon><NIcon><AddOutline /></NIcon></template>
          注册数据库
        </NButton>
      </div>
    </section>

    <section class="summary-grid">
      <div class="summary-item">
        <span class="summary-label">物种</span>
        <span class="summary-value">{{ summary.totalSpecies }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">版本</span>
        <span class="summary-value">{{ summary.totalVersions }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">基因</span>
        <span class="summary-value">{{ summary.totalGenes.toLocaleString() }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">数据文件</span>
        <span class="summary-value">{{ summary.readyFiles }}/{{ summary.totalFiles }}</span>
      </div>
    </section>

    <section class="toolbar">
      <NInput
        v-model:value="searchQuery"
        clearable
        placeholder="搜索物种、版本、Taxonomy ID 或注释关键词"
        class="search-input"
      >
        <template #prefix><NIcon><SearchOutline /></NIcon></template>
      </NInput>
      <NSelect v-model:value="categoryFilter" :options="categoryOptions" class="filter-select" />
      <NSelect v-model:value="statusFilter" :options="statusOptions" class="filter-select" />
      <NSelect v-model:value="sortBy" :options="sortOptions" class="sort-select" />
    </section>

    <section v-if="filteredSpecies.length" class="species-grid">
      <article
        v-for="species in filteredSpecies"
        :key="species.id"
        class="species-card"
      >
        <div class="card-topline" :style="{ background: species.gradient }" />
        <header class="species-header">
          <div class="species-icon" :style="{ background: species.gradient }">{{ species.icon }}</div>
          <div class="species-title-block">
            <div class="species-title-row">
              <h2>{{ species.commonName }}</h2>
              <NTag size="small" :type="versionStatusType(getSpeciesBuildStatus(species))" round>
                {{ statusText(getSpeciesBuildStatus(species)) }}
              </NTag>
            </div>
            <p class="species-latin">{{ species.scientificName }}</p>
            <p class="species-desc">{{ species.description }}</p>
          </div>
        </header>

        <div class="default-version">
          <div class="version-main">
            <span class="version-name">{{ effectiveDefaultVersion(species).versionName }}</span>
            <span class="assembly-name">{{ effectiveDefaultVersion(species).assemblyName }}</span>
          </div>
          <div class="version-tags">
            <NTag
              v-for="tag in effectiveDefaultVersion(species).tags"
              :key="tag"
              size="tiny"
              round
              type="info"
            >{{ tag }}</NTag>
          </div>
        </div>

        <div class="source-row">
          <span
            v-for="source in sourceOrder"
            :key="source"
            class="source-chip"
            :class="{ ready: fileEnabled(effectiveDefaultVersion(species), source) }"
          >{{ sourceLabel[source] }}</span>
        </div>

        <div class="metric-grid">
          <div>
            <span class="metric-value">{{ effectiveDefaultVersion(species).stats.chromosomes }}</span>
            <span class="metric-label">染色体</span>
          </div>
          <div>
            <span class="metric-value">{{ effectiveDefaultVersion(species).stats.totalGenes.toLocaleString() }}</span>
            <span class="metric-label">基因</span>
          </div>
          <div>
            <span class="metric-value">{{ effectiveDefaultVersion(species).stats.genomeSize }}</span>
            <span class="metric-label">大小</span>
          </div>
          <div>
            <span class="metric-value">{{ countReadyFiles(species) }}</span>
            <span class="metric-label">就绪文件</span>
          </div>
        </div>

        <div class="version-list">
          <button
            v-for="version in species.genomeVersions"
            :key="version.versionId"
            class="version-pill"
            :class="{ active: version.versionId === effectiveDefaultVersion(species).versionId }"
            @click="setDefault(species, version)"
          >
            <span>{{ version.versionName }}</span>
            <NIcon v-if="version.versionId === effectiveDefaultVersion(species).versionId" :size="14">
              <CheckmarkCircleOutline />
            </NIcon>
          </button>
        </div>

        <footer class="card-actions">
          <NButton type="primary" size="small" @click="openVersion(effectiveDefaultVersion(species))">
            查看数据库
            <template #icon><NIcon><ArrowForwardOutline /></NIcon></template>
          </NButton>
          <NButton size="small" quaternary @click="setDefault(species, effectiveDefaultVersion(species))">
            设为默认
          </NButton>
        </footer>
      </article>
    </section>

    <NEmpty v-else class="empty-state" description="暂无匹配的数据库" />
  </div>
</template>

<style scoped>
.database-page {
  --db-primary: #165dff;
  --db-purple: #722ed1;
  --db-cyan: #0fc6c2;
  --db-text: #1d2129;
  --db-subtext: #4e5969;
  --db-muted: #86909c;
  --db-border: #e5e6eb;
  --db-bg: #f7f8fa;
  --db-card: #fff;
  min-height: 100%;
}

.database-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 176px;
  padding: 28px 32px;
  margin-bottom: 16px;
  border-radius: 8px;
  background: linear-gradient(135deg, #0f1f4a 0%, #165dff 52%, #722ed1 100%);
  color: #fff;
  overflow: hidden;
}

.hero-copy {
  min-width: 0;
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.database-hero h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.2;
}

.database-hero p {
  max-width: 560px;
  margin: 8px 0 0;
  color: rgba(255, 255, 255, 0.82);
  font-size: 14px;
  line-height: 1.6;
}

.hero-actions {
  flex: 0 0 auto;
}

.register-button {
  color: #fff;
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.18);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 82px;
  padding: 16px;
  border: 1px solid var(--db-border);
  border-radius: 8px;
  background: var(--db-card);
}

.summary-label {
  color: var(--db-muted);
  font-size: 12px;
}

.summary-value {
  color: var(--db-text);
  font-size: 24px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--db-border);
  border-radius: 8px;
  background: var(--db-card);
}

.search-input {
  flex: 1 1 340px;
  min-width: 220px;
}

.filter-select {
  width: 136px;
}

.sort-select {
  width: 148px;
}

.species-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.species-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  min-height: 330px;
  padding: 18px;
  border: 1px solid var(--db-border);
  border-radius: 8px;
  background: var(--db-card);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.species-card:hover {
  transform: translateY(-2px);
  border-color: rgba(22, 93, 255, 0.3);
  box-shadow: 0 10px 24px rgba(22, 93, 255, 0.12);
}

.card-topline {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
}

.species-header {
  display: flex;
  gap: 12px;
  min-width: 0;
}

.species-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  border-radius: 8px;
  font-size: 23px;
}

.species-title-block {
  min-width: 0;
  flex: 1;
}

.species-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.species-title-row h2 {
  margin: 0;
  color: var(--db-text);
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0;
}

.species-latin,
.species-desc {
  margin: 0;
  color: var(--db-muted);
  font-size: 12px;
  line-height: 1.45;
}

.species-latin {
  margin-top: 3px;
  font-style: italic;
}

.species-desc {
  margin-top: 5px;
  color: var(--db-subtext);
}

.default-version {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background: #f7f8fa;
}

.version-main,
.metric-grid > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.version-name {
  color: var(--db-text);
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
}

.assembly-name,
.metric-label {
  color: var(--db-muted);
  font-size: 12px;
}

.assembly-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  word-break: break-word;
}

.version-tags {
  display: flex;
  align-content: flex-start;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.source-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  min-width: 48px;
  padding: 0 10px;
  border: 1px dashed #c9cdd4;
  border-radius: 6px;
  color: var(--db-muted);
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.source-chip.ready {
  border-style: solid;
  border-color: rgba(22, 93, 255, 0.24);
  color: var(--db-primary);
  background: #e8f3ff;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.metric-grid > div {
  padding: 9px 10px;
  border-radius: 8px;
  background: #f7f8fa;
}

.metric-value {
  color: var(--db-text);
  font-size: 15px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.version-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.version-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--db-border);
  border-radius: 6px;
  background: #fff;
  color: var(--db-subtext);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.version-pill.active {
  border-color: rgba(22, 93, 255, 0.24);
  color: var(--db-primary);
  background: #e8f3ff;
}

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

.empty-state {
  padding: 72px 24px;
  border: 1px solid var(--db-border);
  border-radius: 8px;
  background: var(--db-card);
}

@media (max-width: 1180px) {
  .species-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .database-hero,
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .summary-grid,
  .species-grid,
  .metric-grid {
    grid-template-columns: 1fr;
  }

  .filter-select,
  .sort-select {
    width: 100%;
  }

  .card-actions {
    flex-direction: column;
  }
}
</style>
