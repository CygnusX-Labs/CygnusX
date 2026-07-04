<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NResult } from 'naive-ui'

const router = useRouter()
const hasError = ref(false)
const errorMessage = ref('')
const errorInfo = ref('')

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorMessage.value = err instanceof Error ? err.message : String(err)
  errorInfo.value = info
  console.error('[AppErrorBoundary]', err, info, instance)
  return false
})

function reload() {
  window.location.reload()
}
</script>

<template>
  <div v-if="hasError" class="error-boundary">
    <NResult
      status="500"
      title="页面出了点小问题"
      :description="errorMessage || '渲染异常，请刷新重试'"
    >
      <template #footer>
        <div class="error-actions">
          <NButton type="primary" @click="reload">刷新页面</NButton>
          <NButton @click="router.push('/')">返回首页</NButton>
        </div>
        <p v-if="errorInfo" class="error-info">{{ errorInfo }}</p>
      </template>
    </NResult>
  </div>
  <slot v-else />
</template>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--neutral-bg);
}

.error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.error-info {
  margin-top: 16px;
  font-size: 12px;
  color: var(--neutral-text-3);
  word-break: break-all;
}
</style>
