<script setup lang="ts">
import apiClient from '@/api/client'
import {
  NButton,
  NCard,
  NDataTable,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NInput,
  useMessage,
} from 'naive-ui'
import { h, onMounted, ref } from 'vue'

const message = useMessage()
const pricing = ref<any[]>([])
const loading = ref(false)
const showEdit = ref(false)
const editForm = ref<any>({
  pricing_type: 'task_type',
  resource_type: '',
  flow_category: '',
  base_cost: 1,
  per_sample_cost: 0,
  per_comparison_cost: 0,
  unit: 'per_sample',
  priority: 0,
  description: '',
  effective_until: null,
})

const typeOptions = [
  { label: '任务类型', value: 'task_type' },
  { label: '资源', value: 'resource' },
  { label: '沙盒', value: 'sandbox' },
  { label: '奖励', value: 'bonus' },
]
const unitOptions = [
  { label: '每次任务', value: 'per_task' },
  { label: '每小时', value: 'per_hour' },
  { label: '每核时', value: 'per_core_hour' },
  { label: '每GB时', value: 'per_gb_hour' },
  { label: '每次会话', value: 'per_session' },
  { label: '每用户', value: 'per_user' },
  { label: '每样本', value: 'per_sample' },
  { label: '每比较组', value: 'per_comparison' },
]

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '类型', key: 'pricing_type' },
  { title: '流程类别', key: 'flow_category' },
  { title: '资源类型', key: 'resource_type' },
  { title: '基础费用', key: 'base_cost', render: (r: any) => Number(r.base_cost).toFixed(2) },
  { title: '单样本费用', key: 'per_sample_cost', render: (r: any) => Number(r.per_sample_cost || 0).toFixed(2) },
  { title: '每组比较费用', key: 'per_comparison_cost', render: (r: any) => Number(r.per_comparison_cost || 0).toFixed(2) },
  { title: '单位', key: 'unit' },
  { title: '优先级', key: 'priority' },
  {
    title: '状态',
    key: 'is_active',
    render: (r: any) => (r.is_active ? '启用' : '停用'),
  },
  {
    title: '操作',
    key: 'actions',
    render: (row: any) => h(NSpace, {}, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, { default: () => '编辑' }),
        h(NButton, { size: 'small', type: 'error', onClick: () => delPricing(row.id) }, { default: () => '删除' }),
      ],
    }),
  },
]

async function fetchPricing() {
  loading.value = true
  try {
    const res = await apiClient.get('/admin/cookies/pricing')
    pricing.value = res.data
  } finally {
    loading.value = false
  }
}

function openEdit(row?: any) {
  if (row) {
    editForm.value = { ...row }
  } else {
    editForm.value = { pricing_type: 'task_type', resource_type: '', flow_category: '', base_cost: 1, per_sample_cost: 0, per_comparison_cost: 0, unit: 'per_sample', priority: 0, description: '', effective_until: null }
  }
  showEdit.value = true
}

async function savePricing() {
  const data = { ...editForm.value }
  if (data.id) {
    await apiClient.put(`/admin/cookies/pricing/${data.id}`, data)
    message.success('更新成功')
  } else {
    await apiClient.post('/admin/cookies/pricing', data)
    message.success('创建成功')
  }
  showEdit.value = false
  await fetchPricing()
}

async function delPricing(id: number) {
  await apiClient.delete(`/admin/cookies/pricing/${id}`)
  message.success('已删除')
  await fetchPricing()
}

onMounted(fetchPricing)
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">饼干定价管理</h1>
    <NSpace vertical :size="24">
      <NCard title="定价策略管理" :bordered="false" class="arco-card">
        <template #header-extra>
          <NButton type="primary" @click="openEdit()">新建定价</NButton>
        </template>
        <NDataTable :columns="columns" :data="pricing" :loading="loading" :pagination="{ pageSize: 20 }" :bordered="false" size="small" />
      </NCard>

      <NModal v-model:show="showEdit" :title="editForm.id ? '编辑定价' : '新建定价'" preset="dialog" style="width: 560px">
        <NSpace vertical :size="16" style="padding: 16px 0">
          <div>定价类型:</div>
          <NSelect v-model:value="editForm.pricing_type" :options="typeOptions" />
          <div>流程类别 (如 rna_seq):</div>
          <NInput v-model:value="editForm.flow_category" placeholder="留空表示通用" />
          <div>资源类型:</div>
          <NInput v-model:value="editForm.resource_type" placeholder="如 cpu_core_per_hour" />
          <div>基础费用:</div>
          <NInputNumber v-model:value="editForm.base_cost" :step="0.1" :min="0" style="width: 100%" />
          <div>单样本费用:</div>
          <NInputNumber v-model:value="editForm.per_sample_cost" :step="0.1" :min="0" style="width: 100%" />
          <div>每组比较费用:</div>
          <NInputNumber v-model:value="editForm.per_comparison_cost" :step="0.1" :min="0" style="width: 100%" />
          <div>计价单位:</div>
          <NSelect v-model:value="editForm.unit" :options="unitOptions" />
          <div>优先级 (数字越大越优先):</div>
          <NInputNumber v-model:value="editForm.priority" :step="1" style="width: 100%" />
          <div>描述:</div>
          <NInput v-model:value="editForm.description" type="textarea" placeholder="可选" />
          <NButton type="primary" @click="savePricing">保存</NButton>
        </NSpace>
      </NModal>
    </NSpace>
  </div>
</template>
