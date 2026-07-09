<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { Component } from 'vue'
import { NIcon } from 'naive-ui'
import {
  ScanOutline, SearchOutline, ColorPaletteOutline, LayersOutline, BarChartOutline,
  AppsOutline, FlaskOutline, BonfireOutline, CalculatorOutline, SwapHorizontalOutline,
  TerminalOutline, GitNetworkOutline,
} from '@vicons/ionicons5'
import ToolCard from '@/components/bio-tools/ToolCard.vue'
import AppLoading from '@/components/AppLoading.vue'
import { useApi } from '@/composables/useApi'
import { fetchTools } from '@/api/tools'
import type { ToolItem } from '@/types/tools'

const router = useRouter()

/**
 * 图标字符串 key → @vicons/ionicons5 组件映射表。
 * tools_setting.yaml 的 icon 字段是字符串（YAML 不能承载 Vue 组件），
 * 故新增工具若用新图标，须在此登记；未登记的 key 回退到 AppsOutline。
 */
const ICON_MAP: Record<string, Component> = {
  ScanOutline,
  SearchOutline,
  ColorPaletteOutline,
  LayersOutline,
  BarChartOutline,
  AppsOutline,
  BonfireOutline,
  CalculatorOutline,
  SwapHorizontalOutline,
  TerminalOutline,
  GitNetworkOutline,
}

function resolveIcon(key: string): Component {
  return ICON_MAP[key] ?? AppsOutline
}

const {
  data: tools,
  loading,
  execute: fetchToolsList,
} = useApi<ToolItem[]>(fetchTools, { initialData: [] })

/** useApi 返回 Ref<T | undefined>，模板里统一经此 computed 兜底为数组 */
const toolList = computed<ToolItem[]>(() => tools.value ?? [])

fetchToolsList()
</script>

<template>
  <div class="tools-hub-page">
    <div class="page-header">
      <h1 class="page-title">生信工具箱</h1>
      <p class="page-subtitle">集成常用生物信息学分析工具，从质控到可视化一站式完成</p>
    </div>

    <!-- 加载态 -->
    <div v-if="loading && !toolList.length" class="tools-loading">
      <AppLoading text="加载工具箱..." />
    </div>

    <div v-else-if="toolList.length" class="tools-grid">
      <ToolCard
        v-for="tool in toolList"
        :key="tool.key"
        :title="tool.title"
        :description="tool.description"
        :icon="resolveIcon(tool.icon)"
        :gradient="tool.gradient"
        @click="router.push(tool.route)"
      />
    </div>

    <!-- 空状态 -->
    <div v-else class="tools-empty">
      <NIcon :size="64" class="empty-icon">
        <FlaskOutline />
      </NIcon>
      <p class="empty-title">暂无可用工具</p>
      <p class="empty-hint">请在 tools/tools_setting.yaml 中启用工具</p>
    </div>

    <div class="hub-footer">
      <p class="footer-hint">更多工具正在开发中，敬请期待...</p>
    </div>
  </div>
</template>

<style scoped>
.tools-hub-page {
  padding: 16px;
  min-height: 100%;
}
.page-header {
  margin-bottom: 28px;
}
.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 0 0 6px;
}
.page-subtitle {
  font-size: 14px;
  color: var(--neutral-text-3);
  margin: 0;
}
.tools-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}
.tools-loading,
.tools-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
}
.empty-icon {
  color: var(--neutral-text-3);
  margin-bottom: 16px;
}
.empty-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-3);
  margin: 0 0 4px;
}
.empty-hint {
  font-size: 12px;
  color: var(--neutral-text-3);
  margin: 0;
}
.hub-footer {
  text-align: center;
  padding: 24px 0;
}
.footer-hint {
  font-size: 13px;
  color: var(--neutral-text-3);
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
