<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NBadge, NTag } from 'naive-ui'
import { useCookieStore } from '@/stores/cookie'
import { useAuthStore } from '@/stores/auth'
import { useCookieWebSocket } from '@/composables/useCookieWebSocket'

const cookieStore = useCookieStore()
const authStore = useAuthStore()
const { connect } = useCookieWebSocket()

const cookieColor = computed(() => {
  const b = cookieStore.balance
  if (b >= 50) return 'success'
  if (b >= 10) return 'warning'
  return 'error'
})

onMounted(async () => {
  if (authStore.isLoggedIn) {
    await cookieStore.fetchAccount()
    connect()
  }
})
</script>

<template>
  <div v-if="authStore.isLoggedIn && cookieStore.account" class="cookie-badge">
    <NTag :type="cookieColor" size="small" round>
      🥫 {{ cookieStore.balance.toFixed(1) }}
    </NTag>
  </div>
</template>

<style scoped>
.cookie-badge {
  position: relative;
  z-index: 1;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
}

.cookie-badge :deep(.n-tag) {
  height: auto;
  min-height: 28px;
  padding: 4px 12px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
