<script setup lang="ts">
import apiClient from '@/api/client'
import {
  NButton,
  NCard,
  NDataTable,
  NInputNumber,
  NModal,
  NSpace,
  NStatistic,
  NTag,
  useMessage,
} from 'naive-ui'
import { h, onMounted, ref } from 'vue'

const message = useMessage()
const accounts = ref<any[]>([])
const stats = ref<any>(null)
const loading = ref(false)
const showAdjust = ref(false)
const adjustTarget = ref<string>('')
const adjustAmount = ref(0)
const adjustReason = ref('')

const statusTag = (status: string) => {
  const map: Record<string, 'success' | 'warning' | 'error'> = {
    active: 'success', frozen: 'warning', suspended: 'error',
  }
  return map[status] || 'success'
}

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '用户ID', key: 'user_id', ellipsis: { tooltip: true } },
  {
    title: '余额',
    key: 'balance',
    render: (row: any) => `${Number(row.balance).toFixed(1)} 🍪`,
  },
  {
    title: '可用',
    key: 'available_balance',
    render: (row: any) => `${Number(row.available_balance).toFixed(1)} 🍪`,
  },
  {
    title: '状态',
    key: 'status',
    render: (row: any) => h(NTag, { type: statusTag(row.status), size: 'small' }, { default: () => row.status }),
  },
  { title: '累计获得', key: 'total_earned', render: (row: any) => Number(row.total_earned).toFixed(1) },
  { title: '累计消费', key: 'total_spent', render: (row: any) => Number(row.total_spent).toFixed(1) },
  {
    title: '操作',
    key: 'actions',
    render: (row: any) => h(NSpace, {}, {
      default: () => [
        h(NButton, { size: 'small', type: 'primary', onClick: () => openAdjust(row.user_id) }, { default: () => '调整' }),
        row.status === 'active'
          ? h(NButton, { size: 'small', type: 'warning', onClick: () => freezeAccount(row.user_id) }, { default: () => '冻结' })
          : h(NButton, { size: 'small', type: 'success', onClick: () => unfreezeAccount(row.user_id) }, { default: () => '解冻' }),
      ],
    }),
  },
]

async function fetchData() {
  loading.value = true
  try {
    const [acctRes, statsRes] = await Promise.all([
      apiClient.get('/admin/cookies/accounts'),
      apiClient.get('/admin/cookies/stats'),
    ])
    accounts.value = acctRes.data
    stats.value = statsRes.data
  } finally {
    loading.value = false
  }
}

function openAdjust(userId: string) {
  adjustTarget.value = userId
  adjustAmount.value = 0
  adjustReason.value = ''
  showAdjust.value = true
}

async function submitAdjust() {
  await apiClient.post(`/admin/cookies/accounts/${adjustTarget.value}/adjust`, {
    amount: adjustAmount.value,
    reason: adjustReason.value,
  })
  message.success('调整成功')
  showAdjust.value = false
  await fetchData()
}

async function freezeAccount(userId: string) {
  await apiClient.put(`/admin/cookies/accounts/${userId}/freeze`, null, { params: { reason: '管理员冻结' } })
  message.success('已冻结')
  await fetchData()
}

async function unfreezeAccount(userId: string) {
  await apiClient.put(`/admin/cookies/accounts/${userId}/unfreeze`)
  message.success('已解冻')
  await fetchData()
}

onMounted(fetchData)
</script>

<template>
  <NSpace vertical :size="24" style="padding: 24px">
    <NCard v-if="stats" title="系统统计">
      <NSpace :size="48">
        <NStatistic label="总账户数" :value="stats.total_accounts" />
        <NStatistic label="活跃账户" :value="stats.active_accounts" />
        <NStatistic label="系统总余额" :value="Number(stats.total_balance).toFixed(1)">
          <template #suffix>🍪</template>
        </NStatistic>
        <NStatistic label="冻结总额" :value="Number(stats.total_frozen).toFixed(1)">
          <template #suffix>🍪</template>
        </NStatistic>
        <NStatistic label="累计发放" :value="Number(stats.total_earned).toFixed(1)">
          <template #suffix>🍪</template>
        </NStatistic>
        <NStatistic label="累计消费" :value="Number(stats.total_spent).toFixed(1)">
          <template #suffix>🍪</template>
        </NStatistic>
      </NSpace>
    </NCard>

    <NCard title="账户管理">
      <NDataTable :columns="columns" :data="accounts" :loading="loading" :pagination="{ pageSize: 20 }" />
    </NCard>

    <NModal v-model:show="showAdjust" title="调整余额" preset="dialog" style="width: 480px">
      <NSpace vertical :size="16" style="padding: 16px 0">
        <div>目标用户: {{ adjustTarget.substring(0, 8) }}...</div>
        <div>金额 (正数增加, 负数减少):</div>
        <NInputNumber v-model:value="adjustAmount" :step="1" style="width: 100%" />
        <div>原因:</div>
        <n-input v-model:value="adjustReason" placeholder="请输入调整原因" />
        <NButton type="primary" @click="submitAdjust">确认调整</NButton>
      </NSpace>
    </NModal>
  </NSpace>
</template>
