<script setup lang="ts">
import { h, ref } from 'vue'
import {
  NButton, NDataTable, NIcon, NTag, NSpace, NTooltip, useMessage,
} from 'naive-ui'
import { RefreshOutline, BuildOutline, PulseOutline } from '@vicons/ionicons5'
import { useAgentHubStore } from '@/stores/agentHub'
import type { McpService, McpTool } from '@/types/agent'

const message = useMessage()
const store = useAgentHubStore()

const expandedRowKeys = ref<string[]>([])

const columns = [
  {
    title: '服务', key: 'name', width: 240,
    render: (row: McpService) =>
      h('div', { class: 'mcp-name' }, [
        h('span', { class: 'mcp-icon' }, '🔌'),
        h('div', { class: 'mcp-meta' }, [
          h('div', { class: 'mcp-title' }, row.name),
          h('div', { class: 'mcp-desc' }, row.description),
        ]),
      ]),
  },
  { title: '传输', key: 'transport', width: 90, render: (r: McpService) => h(NTag, { size: 'small', bordered: false }, { default: () => r.transport }) },
  {
    title: '状态', key: 'status', width: 110,
    render: (row: McpService) =>
      h('span', { class: 'status-dot' }, [
        h('span', { class: ['dot', row.status === 'online' ? 'online' : 'offline'] }),
        h('span', null, row.status === 'online' ? 'Online' : 'Offline'),
      ]),
  },
  {
    title: '工具数', key: 'tools', width: 80,
    render: (r: McpService) => h('span', { class: 'tool-count' }, r.tools.length),
  },
  { title: '预设', key: 'is_preset', width: 60, render: (r: McpService) => (r.is_preset ? '是' : '否') },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row: McpService) =>
      h(NSpace, { size: 'small' }, {
        default: () => [
          h(NTooltip, null, {
            trigger: () => h(NButton, { size: 'tiny', quaternary: true, onClick: () => toggleStatus(row) },
              { default: () => [h(NIcon, { component: PulseOutline }), row.status === 'online' ? '下线' : '上线'] }),
            default: () => '切换在线状态',
          }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleTest(row) },
            { default: () => [h(NIcon, { component: BuildOutline }), '测试'] }),
        ],
      }),
  },
]

function toggleStatus(row: McpService) {
  store.toggleMcpStatus(row.id)
  message.success(`${row.name} 已${row.status === 'online' ? '下线' : '上线'}`)
}

function handleTest(row: McpService) {
  if (row.tools.length === 0) {
    message.warning(`${row.name} 未暴露工具`)
    return
  }
  message.success(`连接成功，发现 ${row.tools.length} 个工具：${row.tools.map((t) => t.name).join(', ')}`)
}

function renderTools(tools: McpTool[]) {
  if (!tools.length) return h('div', { class: 'tools-empty' }, '该服务暂无工具')
  return h('div', { class: 'tools-grid' },
    tools.map((t) =>
      h('div', { class: 'tool-cell' }, [
        h('div', { class: 'tool-head' }, [
          h(NIcon, { component: BuildOutline, size: 14 }),
          h('span', { class: 'tool-name' }, t.name),
        ]),
        h('div', { class: 'tool-desc' }, t.description),
        h('div', { class: 'tool-schema' },
          Object.entries(t.input_schema).map(([k, v]) =>
            h(NTag, { size: 'tiny', bordered: false }, { default: () => `${k}: ${String(v)}` }),
          ),
        ),
      ]),
    ),
  )
}

const expandColumn = {
  type: 'expand' as const,
  expandable: () => true,
  renderExpand: (row: McpService) =>
    h('div', { class: 'expand-panel' }, [
      h('div', { class: 'expand-title' }, `内部工具（${row.tools.length}）`),
      renderTools(row.tools),
    ]),
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <span class="tab-hint">点击服务行可展开查看其内部工具列表，透视底层能力。</span>
      <NButton size="small" quaternary>
        <template #icon><NIcon :component="RefreshOutline" /></template>
        刷新
      </NButton>
    </div>
    <NDataTable
      :columns="[expandColumn, ...columns]"
      :data="store.mcps"
      :row-key="(r: McpService) => r.id"
      :bordered="false"
      size="small"
      v-model:expanded-row-keys="expandedRowKeys"
    />
  </div>
</template>

<style scoped>
.tab-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.tab-hint { font-size: 12px; color: var(--n-text-color-3, #999); }
:deep(.mcp-name) { display: flex; align-items: center; gap: 10px; }
:deep(.mcp-icon) { font-size: 18px; }
:deep(.mcp-title) { font-weight: 600; }
:deep(.mcp-desc) { font-size: 12px; color: #999; }
:deep(.status-dot) { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
:deep(.status-dot .dot) { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
:deep(.status-dot .dot.online) { background: #18a058; box-shadow: 0 0 6px #18a05880; }
:deep(.status-dot .dot.offline) { background: #d03050; }
:deep(.tool-count) { font-weight: 600; color: var(--n-color-primary, #4f8ef7); }
:deep(.expand-panel) { padding: 8px 12px 16px; }
:deep(.expand-title) { font-size: 12px; color: #999; margin-bottom: 10px; }
:deep(.tools-grid) { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
:deep(.tool-cell) { background: rgba(0,0,0,0.02); border: 1px solid var(--n-border-color, #eee); border-radius: 8px; padding: 10px 12px; }
:deep(.tool-head) { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
:deep(.tool-name) { font-weight: 600; font-size: 13px; font-family: monospace; }
:deep(.tool-desc) { font-size: 12px; color: #666; margin-bottom: 6px; }
:deep(.tool-schema) { display: flex; flex-wrap: wrap; gap: 4px; }
:deep(.tools-empty) { font-size: 12px; color: #999; }
</style>
