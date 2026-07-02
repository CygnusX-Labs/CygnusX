<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NIcon, NSelect, NSpace, NTag } from 'naive-ui'
import { ArrowBackOutline, GlobeOutline } from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()

const genomeOptions = [
  { label: 'Human (hg38)', value: 'hg38' },
  { label: 'Mouse (mm10)', value: 'mm10' },
  { label: 'Rice (IRGSP-1.0)', value: 'rice' },
  { label: 'Arabidopsis (TAIR10)', value: 'tair10' },
]

const selectedGenome = ref('hg38')

const mockTracks = [
  { name: 'Sample_1.bam', type: 'Alignment', size: '2.4 GB', status: 'ready' },
  { name: 'H3K27ac.bw', type: 'BigWig', size: '380 MB', status: 'ready' },
]

/** 外部路由参数：?bam=文件名&id=文件ID（来自「数据管理」BAM 行的"在 IGV 中查看"） */
const pendingBam = ref<string>((route.query.bam as string) || '')
const pendingId = ref<string>((route.query.id as string) || '')

// igv.js 挂载容器 —— 预留，后续阶段引入 igv.js 后在此创建浏览器实例
const igvMountRef = ref<HTMLElement | null>(null)

/** 预留：未来 igv.js 就绪后加载 BAM 轨道 */
function loadTrack(_bam: string, _id?: string) {
  // TODO: import igv from 'igv' → igv.createBrowser(igvMountRef.value, { genome, tracks: [{ url }] })
}

watch(
  () => route.query,
  (q) => {
    pendingBam.value = (q.bam as string) || ''
    pendingId.value = (q.id as string) || ''
  },
)

onMounted(() => {
  if (pendingBam.value) {
    loadTrack(pendingBam.value, pendingId.value)
  }
})
</script>

<template>
  <div class="igv-page">
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回工具箱
      </NButton>
      <h1 class="page-title">Web IGV 浏览器</h1>
    </div>

    <div class="igv-toolbar">
      <div class="genome-select">
        <span class="toolbar-label">参考基因组：</span>
        <NSelect
          v-model:value="selectedGenome"
          :options="genomeOptions"
          size="small"
          style="width: 200px"
        />
      </div>
      <NSpace size="small">
        <NButton size="small" type="primary" disabled>加载轨道</NButton>
        <NButton size="small" disabled>从数据管理导入</NButton>
      </NSpace>
    </div>

    <div class="igv-container">
      <div v-if="pendingBam" class="pending-banner">
        <span class="pending-label">即将加载：</span>
        <NTag size="small" type="info" round>{{ pendingBam }}</NTag>
        <span v-if="pendingId" class="pending-id">ID: {{ pendingId }}</span>
      </div>

      <!-- igv.js 挂载容器 —— 预留：后续阶段引入 igv.js 后在此 createBrowser -->
      <div ref="igvMountRef" class="igv-mount"></div>

      <div class="igv-placeholder">
        <NIcon :size="64" class="placeholder-icon">
          <GlobeOutline />
        </NIcon>
        <h3 class="placeholder-title">IGV 浏览器将在此处渲染</h3>
        <p class="placeholder-desc">
          后续阶段将引入 igv.js，支持 BAM / BigWig / VCF 等格式在线浏览。<br />
          大文件将通过 HTTP Range Requests 实现流畅的区域滑动查看。
        </p>
        <div class="placeholder-tracks">
          <h4 class="tracks-title">当前测试轨道</h4>
          <div v-for="track in mockTracks" :key="track.name" class="track-item">
            <span class="track-name">{{ track.name }}</span>
            <span class="track-type">{{ track.type }}</span>
            <span class="track-size">{{ track.size }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="igv-footer">
      <p class="footer-hint">
        提示：后续可从「数据管理」模块直接选择 BAM/BigWig 文件加载到浏览器中。
      </p>
    </div>
  </div>
</template>

<style scoped>
.igv-page {
  padding: 24px;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.page-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0;
}
.igv-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 10px;
  padding: 10px 16px;
  margin-bottom: 16px;
}
.genome-select {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar-label {
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
  white-space: nowrap;
}
.igv-container {
  flex: 1;
  min-height: 480px;
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 16px;
  box-sizing: border-box;
}
.pending-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: rgba(22, 93, 255, 0.06);
  border: 1px solid rgba(22, 93, 255, 0.18);
  border-radius: 8px;
  font-size: 13px;
  color: var(--neutral-text-2, #4e5969);
}
.pending-label {
  font-weight: 600;
}
.pending-id {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  font-family: 'SF Mono', monospace;
}
/* igv.js 挂载容器：预留，未集成前隐藏 */
.igv-mount {
  display: none;
  flex: 1;
  min-height: 400px;
}
.igv-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 32px;
  max-width: 520px;
  margin: 0 auto;
}
.placeholder-icon {
  color: var(--neutral-text-3, #86909c);
  opacity: 0.5;
  margin-bottom: 16px;
}
.placeholder-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0 0 8px;
}
.placeholder-desc {
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
  line-height: 1.6;
  margin: 0 0 24px;
}
.placeholder-tracks {
  text-align: left;
  background: var(--neutral-bg, #f2f3f8);
  border-radius: 8px;
  padding: 14px 16px;
}
.tracks-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--neutral-text-2, #4e5969);
  margin: 0 0 8px;
}
.track-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 13px;
}
.track-name {
  font-weight: 500;
  color: var(--neutral-text-1, #1d2129);
  flex: 1;
}
.track-type {
  color: var(--arco-primary, #165DFF);
  font-size: 12px;
  background: rgba(22, 93, 255, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
}
.track-size {
  color: var(--neutral-text-3, #86909c);
  font-size: 12px;
}
.igv-footer {
  margin-top: 12px;
}
.footer-hint {
  font-size: 12px;
  color: var(--neutral-text-3, #86909c);
  margin: 0;
}
@media (max-width: 768px) {
  .igv-page {
    padding: 16px;
  }
  .igv-toolbar {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }
}
</style>
