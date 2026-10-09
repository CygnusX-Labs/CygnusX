<script setup lang="ts">
import { ref } from 'vue'

const loading = ref(true)
const unavailable = ref(false)

function handleLoad() {
  loading.value = false
}

function handleError() {
  loading.value = false
  unavailable.value = true
}
</script>

<template>
  <div class="treasure-mouse-page" aria-label="寻宝鼠">
    <div v-if="loading" class="treasure-mouse-loading" role="status">正在打开寻宝鼠…</div>
    <div v-if="unavailable" class="treasure-mouse-error" role="alert">
      寻宝鼠服务暂时不可用，请稍后重试。
    </div>
    <iframe
      title="寻宝鼠"
      src="/treasure-mouse/"
      class="treasure-mouse-frame"
      @load="handleLoad"
      @error="handleError"
    />
  </div>
</template>

<style scoped>
.treasure-mouse-page {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--neutral-bg);
}

.treasure-mouse-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 640px;
  border: 0;
  background: var(--neutral-bg);
}

.treasure-mouse-loading,
.treasure-mouse-error {
  position: absolute;
  z-index: 1;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 14px;
  border: 1px solid var(--neutral-border);
  border-radius: 6px;
  background: var(--neutral-card);
  color: var(--neutral-text-secondary);
  box-shadow: var(--shadow-card);
}

.treasure-mouse-error {
  color: var(--error-color, #c2410c);
}
</style>
