import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

const THEME_KEY = 'omichub-theme'
export type AppTheme = 'dark' | 'light'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<AppTheme>('dark')
  const isDark = computed(() => theme.value === 'dark')

  function applyTheme(next: AppTheme) {
    theme.value = next
    document.documentElement.setAttribute('data-theme', next)
    document.documentElement.classList.toggle('dark', next === 'dark')
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      /* ignore */
    }
  }

  function setTheme(next: AppTheme) {
    applyTheme(next)
  }

  function toggleTheme() {
    applyTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  function initTheme() {
    let next: AppTheme = 'dark'
    try {
      const saved = localStorage.getItem(THEME_KEY) as AppTheme | null
      if (saved === 'light' || saved === 'dark') {
        next = saved
      }
    } catch {
      /* ignore */
    }
    applyTheme(next)
  }

  initTheme()

  return {
    theme,
    isDark,
    setTheme,
    toggleTheme,
    initTheme,
  }
})
