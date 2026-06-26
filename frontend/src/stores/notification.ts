import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { Notification } from '@/types'

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<Notification[]>([])
  const loading = ref(false)

  const authStore = useAuthStore()
  const currentUserId = computed(() => authStore.user?.id || '')

  const unreadCount = computed(() => {
    const uid = currentUserId.value
    return notifications.value.filter((n) => !n.read_by.includes(uid)).length
  })

  async function fetchNotifications() {
    loading.value = true
    try {
      const res = await apiClient.get<Notification[]>('/notifications')
      notifications.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: string) {
    const res = await apiClient.patch<Notification>(`/notifications/${id}/read`)
    const idx = notifications.value.findIndex((n) => n.id === id)
    if (idx >= 0) {
      notifications.value[idx] = res.data
    }
  }

  async function createNotification(payload: {
    title: string
    content: string
    level: string
    is_global: boolean
    target_user_id?: string
    expires_at?: string | null
  }) {
    const res = await apiClient.post<Notification>('/notifications', payload)
    notifications.value.unshift(res.data)
    return res.data
  }

  async function deleteNotification(id: string) {
    await apiClient.delete(`/notifications/${id}`)
    notifications.value = notifications.value.filter((n) => n.id !== id)
  }

  function isRead(notification: Notification): boolean {
    return notification.read_by.includes(currentUserId.value)
  }

  return {
    notifications,
    loading,
    unreadCount,
    fetchNotifications,
    markRead,
    createNotification,
    deleteNotification,
    isRead,
  }
})
