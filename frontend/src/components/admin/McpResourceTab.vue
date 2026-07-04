<script setup lang="ts">
import { h, ref, reactive } from 'vue'
import {
  NButton, NDataTable, NDrawer, NDrawerContent, NForm, NFormItem, NInput,
  NSelect, NIcon, NTag, NSpace, NTooltip, NPopconfirm, useMessage,
} from 'naive-ui'
import { RefreshOutline, BuildOutline, PulseOutline, AddOutline, TrashOutline } from '@vicons/ionicons5'
import { useAgentHubStore } from '@/stores/agentHub'
import type { McpService, McpTool } from '@/types/agent'

const message = useMessage()
const store = useAgentHubStore()

const expandedRowKeys = ref<string[]>([])
const toolsCache = ref<Record<string, McpTool[]>>({})

// ===== 添加 MCP 抽屉 =====
const showAddDrawer = ref(false)
const addForm = reactive({
  name: '',
  description: '',
  transport: 'stdio' as 'stdio' | 'sse',
  command: '',
  args: '',
  url: '',
  envPairs: [{ key: '', value: '' }] as Array<{ key: string; value: string }>,
  timeout: 30,
})
const addLoading = ref(false)
const addTimeoutStr = ref('30')

function resetAddForm() {
  addForm.name = ''
  addForm.description = ''
  addForm.transport = 'stdio'
  addForm.command = ''
  addForm.args = ''
  addForm.url = ''
  addForm.envPairs = [{ key: '', value: '' }]
  addForm.timeout = 30
  addTimeoutStr.value = '30'
}

function addEnvPair() {
  addForm.envPairs.push({ key: '', value: '' })
}

function removeEnvPair(idx: number) {
  addForm.envPairs.splice(idx, 1)
}

async function handleAddSubmit() {
  if (!addForm.name.trim()) {
    message.warning('请填写服务名称')
    return
  }
  const env: Record<string, string> = {}
  addForm.envPairs.forEach((p) => {
    if (p.key.trim()) env[p.key.trim()] = p.value
  })

  const payload: Record<string, unknown> = {
    name: addForm.name.trim(),
    description: addForm.description.trim(),
    transport: addForm.transport,
    timeout: parseInt(addTimeoutStr.value, 10) || 30,
  }
  if (addForm.transport === 'stdio') {
    if (!addForm.command.trim()) {
      message.warning('Stdio 模式需填写启动命令')
      return
    }
    const args = addForm.args.trim() ? addForm.args.trim().split(/\s+/) : []
    payload.command = addForm.command.trim()
    if (args.length) (payload as any).args = args.join(' ')
    if (Object.keys(env).length) payload.env = env
  } else {
    if (!addForm.url.trim()) {
      message.warning('SSE 模式需填写端点 URL')
      return
    }
    payload.url = addForm.url.trim()
  }

  addLoading.value = true
  try {
    await store.addMcpServer(payload as any)
    message.success('MCP 服务添加成功')
    showAddDrawer.value = false
    resetAddForm()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '添加失败')
  } finally {
    addLoading.value = false
  }
}

// ===== 表格操作 =====
async function toggleStatus(row: McpService) {
  await store.toggleMcpStatus(row.id)
  message.success(`${row.name} 已${row.status === 'online' ? '下线' : '上线'}`)
}

async function handleTest(row: McpService) {
  try {
    const res = await store.testMcpServer(row.id)
    if (res.success) {
      message.success(`连接成功，发现 ${res.tool_count} 个工具`)
    } else {
      message.error(`连接失败: ${res.error || '未知错误'}`)
    }
  } catch (e: any) {
    message.error('测试请求失败')
  }
}

async function handleDelete(row: McpService) {
  try {
    await store.removeMcpServer(row.id)
    delete toolsCache.value[row.id]
    message.success(`已删除 ${row.name}`)
  } catch (e: any) {
    message.error('删除失败')
  }
}

async function loadToolsForRow(row: McpService) {
  if (toolsCache.value[row.id]) return
  try {
    toolsCache.value[row.id] = await store.fetchMcpTools(row.id)
  } catch {
    toolsCache.value[row.id] = []
  }
}

function handleExpand(row: McpService) {
  if (!expandedRowKeys.value.includes(row.id)) {
    loadToolsForRow(row)
  }
}

function renderTools(tools: McpTool[]) {
  if (!tools.length) return h('div', { class: 'tools-empty' }, '该服务暂无工具（展开时自动加载）')
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
  renderExpand: (row: McpService) => {
    const tools = toolsCache.value[row.id] ?? row.tools
    const count = row.tool_count || tools.length
    return h('div', { class: 'expand-panel' }, [
      h('div', { class: 'expand-title' }, `内部工具（${count}）`),
      renderTools(tools),
    ])
  },
}

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
    title: '工具数', key: 'tool_count', width: 80,
    render: (r: McpService) => h('span', { class: 'tool-count' }, r.tool_count || r.tools.length),
  },
  { title: '预设', key: 'is_preset', width: 60, render: (r: McpService) => (r.is_preset ? '是' : '否') },
  {
    title: '操作', key: 'actions', width: 260,
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
          !row.is_preset && h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
            trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' },
              { default: () => [h(NIcon, { component: TrashOutline }), '删除'] }),
            default: () => '确定删除该 MCP 服务？关联的 Agent 将自动解绑。',
          }),
        ],
      }),
  },
]
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <span class="tab-hint">点击服务行可展开查看其内部工具列表，透视底层能力。</span>
      <NSpace>
        <NButton size="small" quaternary @click="store.fetchMcps()">
          <template #icon><NIcon :component="RefreshOutline" /></template>
          刷新
        </NButton>
        <NButton type="primary" size="small" @click="showAddDrawer = true">
          <template #icon><NIcon :component="AddOutline" /></template>
          添加 MCP 服务
        </NButton>
      </NSpace>
    </div>
    <NDataTable
      :columns="[expandColumn, ...columns]"
      :data="store.mcps"
      :row-key="(r: McpService) => r.id"
      :bordered="false"
      size="small"
      v-model:expanded-row-keys="expandedRowKeys"
      @expand="handleExpand"
    />

    <!-- 添加 MCP 服务抽屉 -->
    <NDrawer v-model:show="showAddDrawer" :width="520" placement="right" @close="resetAddForm">
      <NDrawerContent title="添加 MCP 服务" closable>
        <NForm label-placement="left" :label-width="90">
          <NFormItem label="服务名称" required>
            <NInput v-model:value="addForm.name" placeholder="例如：SequenceServer BLAST" />
          </NFormItem>

          <NFormItem label="传输方式">
            <NSelect v-model:value="addForm.transport" :options="[
              { label: 'Stdio（本地命令）', value: 'stdio' },
              { label: 'SSE（远程 HTTP）', value: 'sse' },
            ]" />
          </NFormItem>

          <template v-if="addForm.transport === 'stdio'">
            <NFormItem label="启动命令" required>
              <NInput v-model:value="addForm.command" placeholder="例如：npx、python、uvx" />
            </NFormItem>
            <NFormItem label="启动参数">
              <NInput v-model:value="addForm.args" placeholder="例如：-y @modelcontextprotocol/server-filesystem /path" />
            </NFormItem>
            <NFormItem label="环境变量">
              <div class="env-pairs">
                <div v-for="(pair, idx) in addForm.envPairs" :key="idx" class="env-row">
                  <NInput v-model:value="pair.key" placeholder="KEY" size="small" style="flex: 1" />
                  <NInput v-model:value="pair.value" placeholder="VALUE" size="small" style="flex: 1" />
                  <NButton size="tiny" quaternary type="error" @click="removeEnvPair(idx)" :disabled="addForm.envPairs.length <= 1">
                    <template #icon><NIcon :component="TrashOutline" /></template>
                  </NButton>
                </div>
                <NButton size="tiny" text type="primary" @click="addEnvPair">+ 添加环境变量</NButton>
              </div>
            </NFormItem>
          </template>

          <template v-else>
            <NFormItem label="SSE 端点 URL" required>
              <NInput v-model:value="addForm.url" placeholder="https://your-mcp-server.com/sse" />
            </NFormItem>
          </template>

          <NFormItem label="服务描述">
            <NInput v-model:value="addForm.description" type="textarea" :rows="2" placeholder="描述该 MCP 服务的功能..." />
          </NFormItem>

          <NFormItem label="超时(秒)">
            <NInput v-model:value="addTimeoutStr" placeholder="30" />
          </NFormItem>
        </NForm>

        <template #footer>
          <NSpace justify="end">
            <NButton @click="showAddDrawer = false">取消</NButton>
            <NButton type="primary" :loading="addLoading" @click="handleAddSubmit">确认添加</NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style scoped>
.tab-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.tab-hint { font-size: 12px; color: var(--n-text-color-3, #999); }
.env-pairs { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.env-row { display: flex; gap: 6px; align-items: center; }
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
