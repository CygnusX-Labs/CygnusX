<script setup lang="ts">
import { useRouter } from 'vue-router'
import {
  ScanOutline, SearchOutline, ColorPaletteOutline, LayersOutline,
} from '@vicons/ionicons5'
import ToolCard from '@/components/bio-tools/ToolCard.vue'

const router = useRouter()

const tools = [
  {
    key: 'fastq-qc',
    title: 'FASTQ 极速质控',
    description: '高通量测序数据质量评估与清洗，支持 Phred 过滤、接头去除、长度截断',
    icon: ScanOutline,
    gradient: 'linear-gradient(135deg, #165DFF 0%, #6B8DD6 100%)',
    to: '/tools/fastq-qc',
  },
  {
    key: 'jbrowse',
    title: 'Web 基因组浏览器',
    description: '基于 JBrowse 2，支持 BAM / BigWig / VCF / GFF3 在线浏览，外置 YAML 配置参考基因组',
    icon: LayersOutline,
    gradient: 'linear-gradient(135deg, #722ED1 0%, #B37FEB 100%)',
    to: '/tools/jbrowse',
  },
  {
    key: 'blast',
    title: '序列检索 BLAST',
    description: '本地化序列比对检索，支持水稻泛基因组、生菜转录本等自定义数据库',
    icon: SearchOutline,
    gradient: 'linear-gradient(135deg, #FF7D00 0%, #FF9A2E 100%)',
    to: '/tools/blast',
  },
  {
    key: 'plot',
    title: '组学绘图工坊',
    description: '交互式数据可视化，支持散点图、热图、火山图、箱线图等组学常用图表',
    icon: ColorPaletteOutline,
    gradient: 'linear-gradient(135deg, #8E54E9 0%, #B96CD4 100%)',
    to: '/tools/plot',
  },
]
</script>

<template>
  <div class="tools-hub-page">
    <div class="page-header">
      <h1 class="page-title">生信工具箱</h1>
      <p class="page-subtitle">集成常用生物信息学分析工具，从质控到可视化一站式完成</p>
    </div>

    <div class="tools-grid">
      <ToolCard
        v-for="tool in tools"
        :key="tool.key"
        :title="tool.title"
        :description="tool.description"
        :icon="tool.icon"
        :gradient="tool.gradient"
        @click="router.push(tool.to)"
      />
    </div>

    <div class="hub-footer">
      <p class="footer-hint">更多工具正在开发中，敬请期待...</p>
    </div>
  </div>
</template>

<style scoped>
.tools-hub-page {
  padding: 24px;
  min-height: 100%;
}
.page-header {
  margin-bottom: 28px;
}
.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0 0 6px;
}
.page-subtitle {
  font-size: 14px;
  color: var(--neutral-text-3, #86909c);
  margin: 0;
}
.tools-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}
.hub-footer {
  text-align: center;
  padding: 24px 0;
}
.footer-hint {
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
  margin: 0;
}
@media (max-width: 768px) {
  .tools-grid {
    grid-template-columns: 1fr;
  }
  .tools-hub-page {
    padding: 16px;
  }
}
</style>
