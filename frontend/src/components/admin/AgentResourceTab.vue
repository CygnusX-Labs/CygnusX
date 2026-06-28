<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import {
  NButton, NDataTable, NModal, NForm, NFormItem, NInput, NInputNumber,
  NTag, NSpace, NPopconfirm, useMessage, NIcon, NSelect,
} from 'naive-ui'
import { CreateOutline, TrashOutline, RefreshOutline, StarOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import type { ChatAssistantAdmin } from '@/types'

const message = useMessage()
const list = ref<ChatAssistantAdmin[]>([])
const loading = ref(false)
const showEdit = ref(false)
const editing = ref<Partial<ChatAssistantAdmin>>({})
const isEdit = ref(false)

const categoryOptions = [
  { label: '通用', value: 'general' },
  { label: '分析', value: 'analysis' },
  { label: '编程', value: 'code' },
  { label: '可视化', value: 'visualization' },
]

const columns = [
  { title: '图标', key: 'icon', width: 50, render: (r: ChatAssistantAdmin) => r.icon },
  { title: '名称', key: 'name', width: 140 },
  { title: '分类', key: 'category', width: 80 },
  {
    title: '状态', key: 'is_active', width: 70,
    render: (r: ChatAssistantAdmin) => h(NTag, { type: r.is_active ? 'success' : 'default', size: 'small', round: true }, { default: () => r.is_active ? '启用' : '停用' })
  },
  {
    title: '默认', key: 'is_default', width: 60,
    render: (r: ChatAssistantAdmin) => r.is_default ? h(NTag, { type: 'warning', size: 'tiny' }, { default: () => '默认' }) : ''
  },
  { title: '内置', key: 'is_builtin', width: 50, render: (r: ChatAssistantAdmin) => r.is_builtin ? '是' : '否' },
  {
    title: '操作', key: 'actions', width: 240,
    render: (r: ChatAssistantAdmin) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleEdit(r) }, {
          default: () => [h(NIcon, { component: CreateOutline }), '编辑']
        }),
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleToggle(r.assistant_id) }, {
          default: () => r.is_active ? '停用' : '启用'
        }),
        !r.is_default && h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleSetDefault(r.assistant_id) }, {
          default: () => [h(NIcon, { component: StarOutline }), '设默认']
        }),
        !r.is_builtin && h(NPopconfirm, { onPositiveClick: () => handleDelete(r.assistant_id) }, {
          trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, {
            default: () => [h(NIcon, { component: TrashOutline }), '删除']
          }),
          default: () => '确定删除？'
        }),
      ]
    })
  },
]

onMounted(() => fetchList())

async function fetchList() {
  loading.value = true
  try {
    const res = await apiClient.get<ChatAssistantAdmin[]>('/admin/assistants')
    list.value = res.data
  } finally { loading.value = false }
}

function handleCreate() {
  editing.value = { default_temperature: 0.3, default_max_tokens: 4096, icon: '🤖', color: '#4f8ef7', category: 'general' }
  isEdit.value = false
  showEdit.value = true
}

function handleEdit(r: ChatAssistantAdmin) {
  editing.value = { ...r }
  isEdit.value = true
  showEdit.value = true
}

async function handleSave() {
  try {
    if (isEdit.value) {
      await apiClient.put(`/admin/assistants/${editing.value.assistant_id}`, editing.value)
      message.success('更新成功')
    } else {
      await apiClient.post('/admin/assistants', editing.value)
      message.success('创建成功')
    }
    showEdit.value = false
    fetchList()
  } catch (e: any) { message.error(e?.response?.data?.detail || '操作失败') }
}

async function handleToggle(id: string) {
  try { await apiClient.post(`/admin/assistants/${id}/toggle`); fetchList() }
  catch (e: any) { message.error(e?.response?.data?.detail || '操作失败') }
}

async function handleSetDefault(id: string) {
  try { await apiClient.post(`/admin/assistants/${id}/set-default`); message.success('已设为默认'); fetchList() }
  catch (e: any) { message.error(e?.response?.data?.detail || '操作失败') }
}

async function handleDelete(id: string) {
  try { await apiClient.delete(`/admin/assistants/${id}`); message.success('已删除'); fetchList() }
  catch (e: any) { message.error(e?.response?.data?.detail || '删除失败') }
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <NButton type="primary" size="small" @click="handleCreate">
        <template #icon><NIcon :component="CreateOutline" /></template>
        新建助手
      </NButton>
      <NButton size="small" quaternary @click="fetchList">
        <template #icon><NIcon :component="RefreshOutline" /></template>
        刷新
      </NButton>
    </div>
    <NDataTable :columns="columns" :data="list" :loading="loading" :bordered="false" size="small" />
    <NModal v-model:show="showEdit" preset="card" :title="isEdit ? '编辑助手' : '新建助手'" style="width: 560px">
      <NForm label-placement="left" size="small">
        <NFormItem label="助手ID"><NInput v-model:value="editing.assistant_id" :disabled="isEdit" placeholder="rna_seq_analyst" /></NFormItem>
        <NFormItem label="名称"><NInput v-model:value="editing.name" /></NFormItem>
        <NFormItem label="描述"><NInput v-model:value="editing.description" /></NFormItem>
        <NFormItem label="系统提示词"><NInput v-model:value="editing.system_prompt" type="textarea" :autosize="{minRows:4,maxRows:10}" /></NFormItem>
        <NFormItem label="图标"><NInput v-model:value="editing.icon" /></NFormItem>
        <NFormItem label="颜色"><NInput v-model:value="editing.color" /></NFormItem>
        <NFormItem label="分类"><NSelect v-model:value="editing.category" :options="categoryOptions" /></NFormItem>
        <NFormItem label="Temperature"><NInputNumber v-model:value="editing.default_temperature" :min="0" :max="2" :step="0.1" /></NFormItem>
        <NFormItem label="Max Tokens"><NInputNumber v-model:value="editing.default_max_tokens" :min="100" :max="32768" :step="100" /></NFormItem>
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
