<script setup lang="ts">
import KimiLayout from '@/components/ai-chat/KimiLayout.vue'
</script>

<template>
  <div class="ai-page">
    <KimiLayout />
  </div>
</template>

<style scoped>
.ai-page {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  height: 100%;
  display: flex;
  overflow: hidden;
}
</style>
