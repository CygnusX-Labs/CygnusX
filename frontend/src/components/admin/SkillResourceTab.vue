<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import {
  NButton, NDataTable, NModal, NForm, NFormItem, NInput, NSelect,
  NSwitch, NSpace, NTag, NPopconfirm, useMessage, NIcon,
} from 'naive-ui'
import { CreateOutline, TrashOutline, RefreshOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import type { Skill } from '@/types'

const message = useMessage()
const skills = ref<Skill[]>([])
const loading = ref(false)
const showEdit = ref(false)
const editing = ref<Partial<Skill>>({})
const isEdit = ref(false)

const categoryOptions = [
  { label: '通用', value: 'general' },
  { label: '分析', value: 'analysis' },
  { label: '编程', value: 'code' },
  { label: '可视化', value: 'visualization' },
  { label: '搜索', value: 'search' },
]

const columns = [
  { title: '图标', key: 'icon', width: 50, render: (r: Skill) => r.icon },
  { title: '技能 ID', key: 'skill_id', width: 140 },
  { title: '名称', key: 'name', width: 140 },
  { title: '分类', key: 'category', width: 80 },
  {
    title: '状态', key: 'is_active', width: 70,
    render: (r: Skill) => h(NTag, { type: r.is_active ? 'success' : 'default', size: 'small' },
      { default: () => r.is_active ? '启用' : '停用' })
  },
  { title: '内置', key: 'is_builtin', width: 50, render: (r: Skill) => r.is_builtin ? '是' : '否' },
  {
    title: '操作', key: 'actions', width: 180,
    render: (r: Skill) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleEdit(r) },
          { default: () => [h(NIcon, { component: CreateOutline }), '编辑'] }),
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleToggle(r.skill_id) },
          { default: () => r.is_active ? '停用' : '启用' }),
        !r.is_builtin && h(NPopconfirm, { onPositiveClick: () => handleDelete(r.skill_id) }, {
          trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' },
            { default: () => [h(NIcon, { component: TrashOutline }), '删除'] }),
          default: () => '确定删除？'
        }),
      ]
    })
  },
]

async function fetchSkills() {
  loading.value = true
  try {
    const res = await apiClient.get<Skill[]>('/admin/skills')
    skills.value = res.data
  } finally { loading.value = false }
}

onMounted(fetchSkills)

function handleCreate() {
  editing.value = { icon: '🔧', category: 'general', is_active: true }
  isEdit.value = false
  showEdit.value = true
}

function handleEdit(row: Skill) {
  editing.value = { ...row }
  isEdit.value = true
  showEdit.value = true
}

async function handleSave() {
  try {
    if (isEdit.value) {
      await apiClient.put(`/admin/skills/${editing.value.skill_id}`, editing.value)
      message.success('更新成功')
    } else {
      await apiClient.post('/admin/skills', editing.value)
      message.success('创建成功')
    }
    showEdit.value = false
    await fetchSkills()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '操作失败')
  }
}

async function handleToggle(skillId: string) {
  try {
    await apiClient.post(`/admin/skills/${skillId}/toggle`)
    await fetchSkills()
  } catch (e: any) { message.error('操作失败') }
}

async function handleDelete(skillId: string) {
  try {
    await apiClient.delete(`/admin/skills/${skillId}`)
    message.success('已删除')
    await fetchSkills()
  } catch (e: any) { message.error(e?.response?.data?.detail || '删除失败') }
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <NButton type="primary" size="small" @click="handleCreate">
        <template #icon><NIcon :component="CreateOutline" /></template>
        创建技能
      </NButton>
      <NButton size="small" quaternary @click="fetchSkills">
        <template #icon><NIcon :component="RefreshOutline" /></template>
        刷新
      </NButton>
    </div>
    <NDataTable :columns="columns" :data="skills" :loading="loading" :bordered="false" size="small" />
    <NModal v-model:show="showEdit" preset="card" :title="isEdit ? '编辑技能' : '创建技能'" style="width: 560px">
      <NForm label-placement="left" size="small">
        <NFormItem label="技能 ID" v-if="!isEdit">
          <NInput v-model:value="editing.skill_id" placeholder="pubmed_search" />
        </NFormItem>
        <NFormItem label="名称"><NInput v-model:value="editing.name" /></NFormItem>
        <NFormItem label="描述"><NInput v-model:value="editing.description" /></NFormItem>
        <NFormItem label="Prompt">
          <NInput v-model:value="editing.prompt" type="textarea" :autosize="{minRows:4,maxRows:12}"
            placeholder="技能的 prompt 内容，将注入到 AI 的 system prompt 中" />
        </NFormItem>
        <NFormItem label="图标"><NInput v-model:value="editing.icon" /></NFormItem>
        <NFormItem label="分类"><NSelect v-model:value="editing.category" :options="categoryOptions" /></NFormItem>
        <NFormItem label="启用" v-if="!isEdit"><NSwitch v-model:value="editing.is_active" /></NFormItem>
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
