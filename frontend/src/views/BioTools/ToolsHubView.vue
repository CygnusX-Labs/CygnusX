<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { Component } from 'vue'
import { NButton, NCollapseTransition, NIcon, NSkeleton } from 'naive-ui'
import {
  ScanOutline, SearchOutline, CodeSlashOutline, ColorPaletteOutline, LayersOutline, BarChartOutline,
  AppsOutline, FlaskOutline, BonfireOutline, CalculatorOutline, SwapHorizontalOutline,
  TerminalOutline, GitNetworkOutline, GitBranchOutline, GridOutline,
  ChevronDownOutline, ChevronForwardOutline,
} from '@vicons/ionicons5'
import ToolCard from '@/components/bio-tools/ToolCard.vue'
import { useApi } from '@/composables/useApi'
import { fetchTools } from '@/api/tools'
import type { ToolItem } from '@/types/tools'

const router = useRouter()

const COLLAPSED_STORAGE_KEY = 'omicHub_tools_group_collapsed'

const GROUP_MAP: Record<string, { label: string; icon: string; order: number }> = {
  sequence: { label: '序列分析', icon: 'CodeSlashOutline', order: 1 },
  visualization: { label: '数据可视化', icon: 'ColorPaletteOutline', order: 2 },
  genome: { label: '基因组与进化', icon: 'LayersOutline', order: 3 },
  function: { label: '功能注释', icon: 'BarChartOutline', order: 4 },
  environment: { label: '计算环境', icon: 'TerminalOutline', order: 5 },
}

const OTHER_GROUP = {
  label: '其他工具',
  icon: 'AppsOutline',
  order: Number.MAX_SAFE_INTEGER,
}

/**
 * 图标字符串 key → @vicons/ionicons5 组件映射表。
 * tools_setting.yaml 的 icon 字段是字符串（YAML 不能承载 Vue 组件），
 * 故新增工具若用新图标，须在此登记；未登记的 key 回退到 AppsOutline。
 */
const ICON_MAP: Record<string, Component> = {
  ScanOutline,
  SearchOutline,
  CodeSlashOutline,
  ColorPaletteOutline,
  LayersOutline,
  BarChartOutline,
  AppsOutline,
  BonfireOutline,
  CalculatorOutline,
  SwapHorizontalOutline,
  TerminalOutline,
  GitNetworkOutline,
  GitBranchOutline,
  GridOutline,
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

interface ToolGroup {
  key: string
  label: string
  icon: string
  order: number
  tools: ToolItem[]
}

const groupedTools = computed<ToolGroup[]>(() => {
  const groups = new Map<string, ToolGroup>()

  for (const tool of toolList.value) {
    if (tool.enabled === false) continue

    const groupKey = GROUP_MAP[tool.group] ? tool.group : 'other'
    const groupMeta = GROUP_MAP[groupKey] ?? OTHER_GROUP
    const group = groups.get(groupKey) ?? {
      key: groupKey,
      ...groupMeta,
      tools: [],
    }

    group.tools.push(tool)
    groups.set(groupKey, group)
  }

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      tools: [...group.tools].sort((firstTool, secondTool) => firstTool.order - secondTool.order),
    }))
    .sort((firstGroup, secondGroup) => firstGroup.order - secondGroup.order)
})

const collapsed = ref<Record<string, boolean>>({})

function toggleGroup(groupKey: string) {
  collapsed.value[groupKey] = !collapsed.value[groupKey]
}

onMounted(() => {
  try {
    const savedCollapsed = localStorage.getItem(COLLAPSED_STORAGE_KEY)
    if (savedCollapsed) {
      collapsed.value = JSON.parse(savedCollapsed) as Record<string, boolean>
    }
  } catch {
    collapsed.value = {}
  }
})

watch(
  collapsed,
  (value) => {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify(value))
  },
  { deep: true },
)

fetchToolsList()
</script>

<template>
  <div class="tools-hub-page">
    <div class="page-header">
      <h1 class="page-title">生信工具箱</h1>
      <p class="page-subtitle">集成常用生物信息学分析工具，从质控到可视化一站式完成</p>
    </div>

    <!-- 加载态 -->
    <div v-if="loading && !toolList.length" class="tool-groups tools-loading">
      <div v-for="(group, groupKey) in GROUP_MAP" :key="groupKey" class="tool-group">
        <div class="group-header">
          <NIcon :component="ICON_MAP[group.icon]" />
          <span class="group-label">{{ group.label }}</span>
        </div>
        <div class="tools-grid skeleton-grid">
          <NSkeleton v-for="index in 4" :key="index" height="92px" :sharp="false" />
        </div>
      </div>
    </div>

    <div v-else-if="groupedTools.length" class="tool-groups">
      <section v-for="group in groupedTools" :key="group.key" class="tool-group">
        <div class="group-header">
          <NIcon :component="ICON_MAP[group.icon]" />
          <span class="group-label">{{ group.label }}</span>
          <span class="group-count">{{ group.tools.length }} 个工具</span>
          <NButton text class="group-toggle" @click="toggleGroup(group.key)">
            <NIcon :component="collapsed[group.key] ? ChevronForwardOutline : ChevronDownOutline" />
          </NButton>
        </div>

        <NCollapseTransition :show="!collapsed[group.key]">
          <div class="tools-grid">
            <ToolCard
              v-for="tool in group.tools"
              :key="tool.key"
              :title="tool.title"
              :description="tool.description"
              :icon="resolveIcon(tool.icon)"
              :gradient="tool.gradient"
              @click="router.push(tool.route)"
            />
          </div>
        </NCollapseTransition>
      </section>
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
.tool-group {
  margin-bottom: 24px;
}
.group-header {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
  color: var(--text-color-base, var(--neutral-text-1));
}
.group-label {
  overflow: hidden;
  font-size: 16px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.group-count {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--neutral-text-3);
}
.group-toggle {
  margin-left: auto;
  color: var(--neutral-text-3);
}
.tools-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin: 12px 0;
}
.skeleton-grid :deep(.n-skeleton) {
  border-radius: 12px;
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
  .group-header {
    gap: 6px;
  }
}
</style>
