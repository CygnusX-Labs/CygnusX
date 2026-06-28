<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import {
  NButton, NDataTable, NModal, NForm, NFormItem, NInput, NInputNumber,
  NSelect, NSwitch, NSpace, NTag, NPopconfirm, useMessage, NIcon,
} from 'naive-ui'
import { CreateOutline, TrashOutline, BuildOutline, RefreshOutline } from '@vicons/ionicons5'
import { useMCPStore } from '@/stores/mcp'
import type { MCPServer } from '@/types'

const message = useMessage()
const mcpStore = useMCPStore()

const showEdit = ref(false)
const editing = ref<Partial<MCPServer> & { env_text?: string }>({})
const isEdit = ref(false)
const testing = ref<string | null>(null)

const transportOptions = [
  { label: 'stdio', value: 'stdio' },
  { label: 'SSE', value: 'sse' },
  { label: 'builtin', value: 'builtin' },
]

const columns = [
  { title: '名称', key: 'name', width: 160 },
  { title: '传输', key: 'transport', width: 80 },
  {
    title: '状态', key: 'status', width: 80,
    render: (row: MCPServer) => h(NTag, {
      type: row.status === 'online' ? 'success' : row.status === 'error' ? 'error' : 'default',
      size: 'small', round: true,
    }, { default: () => row.status })
  },
  { title: '工具数', key: 'tool_count', width: 70 },
  { title: '预设', key: 'is_preset', width: 60, render: (row: MCPServer) => row.is_preset ? '是' : '否' },
  {
    title: '操作', key: 'actions', width: 200,
    render: (row: MCPServer) => h(NSpace, { size: 'small' }, {
      default: () => [
        !row.is_preset && h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleEdit(row) }, {
          default: () => [h(NIcon, { component: CreateOutline }), '编辑']
        }),
        h(NButton, {
          size: 'tiny', quaternary: true, loading: testing.value === row.id,
          onClick: () => handleTest(row.id),
        }, { default: () => [h(NIcon, { component: BuildOutline }), '测试'] }),
        !row.is_preset && h(NPopconfirm, { onPositiveClick: () => handleDelete(row.id) }, {
          trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, {
            default: () => [h(NIcon, { component: TrashOutline }), '删除']
          }),
          default: () => '确定删除？'
        }),
      ]
    })
  },
]

onMounted(() => mcpStore.fetchServers())

function handleCreate() {
  editing.value = { transport: 'stdio', timeout: 30, auto_restart: true, env_text: '' }
  isEdit.value = false
  showEdit.value = true
}

function handleEdit(row: MCPServer) {
  editing.value = { ...row }
  isEdit.value = true
  showEdit.value = true
}

async function handleSave() {
  const data = { ...editing.value }
  const payload: Record<string, unknown> = { ...data }
  if (data.env_text) {
    try { payload.env = JSON.parse(data.env_text) } catch { payload.env = {} }
  }
  try {
    if (isEdit.value && data.id) {
      await mcpStore.updateServer(data.id, payload as any)
      message.success('更新成功')
    } else {
      await mcpStore.createServer(payload as any)
      message.success('创建成功')
    }
    showEdit.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '操作失败')
  }
}

async function handleDelete(id: string) {
  try {
    await mcpStore.deleteServer(id)
    message.success('已删除')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

async function handleTest(id: string) {
  testing.value = id
  try {
    const result = await mcpStore.testServer(id)
    if (result.success) {
      message.success(`连接成功，发现 ${result.tool_count} 个工具`)
      await mcpStore.fetchServers()
    } else {
      message.error(`连接失败: ${result.error || '未知错误'}`)
    }
  } finally {
    testing.value = null
  }
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <NButton type="primary" size="small" @click="handleCreate">
        <template #icon><NIcon :component="CreateOutline" /></template>
        注册 MCP Server
      </NButton>
      <NButton size="small" quaternary @click="mcpStore.fetchServers()">
        <template #icon><NIcon :component="RefreshOutline" /></template>
        刷新
      </NButton>
    </div>
    <NDataTable
      :columns="columns"
      :data="mcpStore.servers"
      :loading="mcpStore.loading"
      :bordered="false"
      size="small"
    />
    <NModal v-model:show="showEdit" preset="card" :title="isEdit ? '编辑 MCP Server' : '注册 MCP Server'" style="width: 520px">
      <NForm label-placement="left" size="small">
        <NFormItem label="名称"><NInput v-model:value="editing.name" placeholder="server-name" /></NFormItem>
        <NFormItem label="描述"><NInput v-model:value="editing.description" /></NFormItem>
        <NFormItem label="传输方式">
          <NSelect v-model:value="editing.transport" :options="transportOptions" />
        </NFormItem>
        <NFormItem v-if="editing.transport === 'stdio'" label="启动命令">
          <NInput v-model:value="editing.command" placeholder="npx -y @mcp/server" />
        </NFormItem>
        <NFormItem v-if="editing.transport === 'sse'" label="URL">
          <NInput v-model:value="editing.url" placeholder="http://localhost:3001/sse" />
        </NFormItem>
        <NFormItem label="环境变量 (JSON)">
          <NInput v-model:value="editing.env_text" type="textarea" placeholder='{"KEY":"value"}' :autosize="{minRows:2,maxRows:4}" />
        </NFormItem>
        <NFormItem label="超时(秒)"><NInputNumber v-model:value="editing.timeout" :min="5" :max="300" /></NFormItem>
        <NFormItem label="自动重启"><NSwitch v-model:value="editing.auto_restart" /></NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton size="small" @click="showEdit = false">取消</NButton>
          <NButton size="small" type="primary" @click="handleSave">保存</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.tab-header { display: flex; gap: 8px; margin-bottom: 12px; }
</style>
