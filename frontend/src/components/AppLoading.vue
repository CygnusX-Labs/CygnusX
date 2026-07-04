<script setup lang="ts">
withDefaults(defineProps<{
  text?: string
  size?: 'small' | 'medium' | 'large'
}>(), {
  text: '加载中...',
  size: 'medium',
})
</script>

<template>
  <div class="app-loading" :class="`app-loading--${size}`">
    <svg class="app-loading__spinner" viewBox="0 0 24 24" fill="none">
      <circle class="app-loading__track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
      <path class="app-loading__arc" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
    <span v-if="text" class="app-loading__text">{{ text }}</span>
  </div>
</template>

<style scoped>
.app-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--neutral-text-3);
}

.app-loading--small .app-loading__spinner {
  width: 20px;
  height: 20px;
}
.app-loading--small .app-loading__text {
  font-size: 12px;
}

.app-loading--medium .app-loading__spinner {
  width: 32px;
  height: 32px;
}
.app-loading--medium .app-loading__text {
  font-size: 14px;
}

.app-loading--large .app-loading__spinner {
  width: 48px;
  height: 48px;
}
.app-loading--large .app-loading__text {
  font-size: 16px;
}

.app-loading__spinner {
  animation: app-loading-spin 1s linear infinite;
}

.app-loading__track {
  opacity: 0.2;
}

.app-loading__arc {
  opacity: 0.75;
}

.app-loading__text {
  color: var(--neutral-text-2);
}

@keyframes app-loading-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
