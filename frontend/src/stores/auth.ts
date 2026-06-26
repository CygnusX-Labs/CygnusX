import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'
import type { User, TokenResponse, RegisterRequest } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => accessToken.value !== null)

  function setTokens(access: string, refresh: string) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function clearTokens() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async function login(username: string, password: string): Promise<void> {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)

    const response = await apiClient.post<TokenResponse>('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })

    setTokens(response.data.access_token, response.data.refresh_token)
    await fetchUser()
  }

  async function register(req: RegisterRequest): Promise<void> {
    await apiClient.post('/auth/register', req)
  }

  async function setupFirstAdmin(req: RegisterRequest): Promise<void> {
    const response = await apiClient.post<TokenResponse>('/auth/setup', req)
    setTokens(response.data.access_token, response.data.refresh_token)
    await fetchUser()
  }

  async function checkSetupRequired(): Promise<boolean> {
    const response = await apiClient.get<{ setup_required: boolean }>('/auth/setup-required')
    return response.data.setup_required
  }

  async function fetchUser(): Promise<void> {
    if (!accessToken.value) return
    const response = await apiClient.get<User>('/auth/me')
    user.value = response.data
  }

  async function refreshAccessToken(): Promise<boolean> {
    if (!refreshToken.value) return false

    try {
      const response = await apiClient.post<TokenResponse>('/auth/refresh', {
        refresh_token: refreshToken.value,
      })
      setTokens(response.data.access_token, response.data.refresh_token)
      return true
    } catch {
      clearTokens()
      return false
    }
  }

  function logout() {
    clearTokens()
    // 确保 Pinia 中的用户状态同步清空
    user.value = null
  }

  return {
    accessToken,
    refreshToken,
    user,
    loading,
    isLoggedIn,
    setTokens,
    clearTokens,
    login,
    register,
    setupFirstAdmin,
    checkSetupRequired,
    fetchUser,
    refreshAccessToken,
    logout,
  }
})
