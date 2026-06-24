import { ref } from 'vue'
import apiClient from '@/api/client'

export function useApi<T>(endpoint: string) {
  const data = ref<T | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function fetchData() {
    loading.value = true
    error.value = null
    try {
      const response = await apiClient.get(endpoint)
      data.value = response.data
    } catch (e: any) {
      error.value = e.message || '请求失败'
    } finally {
      loading.value = false
    }
  }

  return { data, error, loading, fetchData }
}
