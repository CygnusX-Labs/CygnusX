import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CookieAccount, CookieTransaction, CostEstimate } from '@/types'
import apiClient from '@/api/client'

export const useCookieStore = defineStore('cookie', () => {
  const account = ref<CookieAccount | null>(null)
  const transactions = ref<CookieTransaction[]>([])
  const loading = ref(false)

  const balance = computed(() => account.value?.available_balance ?? 0)
  const isLoggedIn = computed(() => account.value !== null)

  async function fetchAccount() {
    try {
      const res = await apiClient.get<CookieAccount>('/cookies/account')
      account.value = res.data
    } catch {
      account.value = null
    }
  }

  async function fetchTransactions(offset = 0, limit = 50) {
    loading.value = true
    try {
      const res = await apiClient.get<CookieTransaction[]>('/cookies/transactions', {
        params: { offset, limit },
      })
      transactions.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function estimateCost(flowId: string): Promise<CostEstimate> {
    const res = await apiClient.get<CostEstimate>('/cookies/estimate', {
      params: { flow_id: flowId },
    })
    return res.data
  }

  function updateBalanceFromWebSocket(data: { balance: number; frozen_balance: number }) {
    if (account.value) {
      account.value.balance = data.balance
      account.value.frozen_balance = data.frozen_balance
      account.value.available_balance = data.balance - data.frozen_balance
    }
  }

  return { account, transactions, loading, balance, isLoggedIn, fetchAccount, fetchTransactions, estimateCost, updateBalanceFromWebSocket }
})
