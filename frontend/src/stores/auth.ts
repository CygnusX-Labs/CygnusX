import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const userId = ref<string | null>(null)

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('access_token', newToken)
  }

  function clearToken() {
    token.value = null
    userId.value = null
    localStorage.removeItem('access_token')
  }

  function isLoggedIn() {
    return token.value !== null
  }

  return { token, userId, setToken, clearToken, isLoggedIn }
})
