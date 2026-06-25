<script setup lang="ts">
import type { CookieTransaction } from '@/types'
import apiClient from '@/api/client'
import {
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NGrid,
  NGridItem,
  NStatistic,
  NSpace,
  NTag,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

const account = ref<any>(null)
const transactions = ref<CookieTransaction[]>([])
const loading = ref(false)

const statusTagType = computed(() => {
  const map: Record<string, 'success' | 'warning' | 'error'> = {
    active: 'success',
    frozen: 'warning',
    suspended: 'error',
  }
  return map[account.value?.status || 'active'] || 'success'
})

const txnTagType = (type: string) => {
  const map: Record<string, 'success' | 'error' | 'warning' | 'info' | 'default'> = {
    earn: 'success',
    spend: 'error',
    adjust: 'warning',
    refund: 'info',
    freeze: 'warning',
    unfreeze: 'info',
  }
  return map[type] || 'default'
}

const columns = [
  {
    title: '时间',
    key: 'created_at',
    render(row: CookieTransaction) {
      return row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-'
    },
  },
  {
    title: '类型',
    key: 'txn_type',
    render(row: CookieTransaction) {
      return h(NTag, { type: txnTagType(row.txn_type), size: 'small' }, { default: () => row.txn_type })
    },
  },
  {
    title: '金额',
    key: 'amount',
    render(row: CookieTransaction) {
      const color = row.amount >= 0 ? '#18a058' : '#d03050'
      return h('span', { style: { color, fontWeight: 'bold' } }, `${row.amount >= 0 ? '+' : ''}${Number(row.amount).toFixed(2)}`)
    },
  },
  { title: '交易后余额', key: 'balance_after', render: (row: CookieTransaction) => Number(row.balance_after).toFixed(2) },
  { title: '说明', key: 'description' },
]

onMounted(async () => {
  loading.value = true
  try {
    const [acctRes, txnRes] = await Promise.all([
      apiClient.get('/cookies/account'),
      apiClient.get('/cookies/transactions'),
    ])
    account.value = acctRes.data
    transactions.value = txnRes.data
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <NSpace vertical :size="24" style="padding: 24px">
    <NCard title="饼干账户">
      <NGrid v-if="account" :cols="4" :x-gap="16" :y-gap="16" responsive="screen">
        <NGridItem>
          <NStatistic label="可用余额" :value="Number(account.available_balance).toFixed(1)">
            <template #suffix>🍪</template>
          </NStatistic>
        </NGridItem>
        <NGridItem>
          <NStatistic label="总余额" :value="Number(account.balance).toFixed(1)">
            <template #suffix>🍪</template>
          </NStatistic>
        </NGridItem>
        <NGridItem>
          <NStatistic label="冻结中" :value="Number(account.frozen_balance).toFixed(1)">
            <template #suffix>🍪</template>
          </NStatistic>
        </NGridItem>
        <NGridItem>
          <NStatistic label="累计获得" :value="Number(account.total_earned).toFixed(1)">
            <template #suffix>🍪</template>
          </NStatistic>
        </NGridItem>
      </NGrid>
      <NDescriptions v-if="account" :columns="2" bordered style="margin-top: 16px">
        <NDescriptionsItem label="账户状态">
          <NTag :type="statusTagType" size="small">{{ account.status }}</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem label="累计消费">{{ Number(account.total_spent).toFixed(2) }} 🍪</NDescriptionsItem>
        <NDescriptionsItem label="累计调整">{{ Number(account.total_adjusted).toFixed(2) }} 🍪</NDescriptionsItem>
        <NDescriptionsItem label="创建时间">
          {{ account.created_at ? new Date(account.created_at).toLocaleString('zh-CN') : '-' }}
        </NDescriptionsItem>
      </NDescriptions>
    </NCard>

    <NCard title="交易流水">
      <NDataTable
        :columns="columns"
        :data="transactions"
        :loading="loading"
        :pagination="{ pageSize: 20 }"
        :bordered="false"
        size="small"
      />
    </NCard>
  </NSpace>
</template>
