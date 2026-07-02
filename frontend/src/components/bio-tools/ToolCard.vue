<script setup lang="ts">
import { NIcon, NButton } from 'naive-ui'
import { ChevronForwardOutline } from '@vicons/ionicons5'
import type { Component } from 'vue'

defineProps<{
  title: string
  description: string
  icon: Component
  gradient: string
  to?: string
}>()

const emit = defineEmits<{
  click: []
}>()
</script>

<template>
  <div class="tool-card" @click="emit('click')">
    <div class="tool-card-icon" :style="{ background: gradient }">
      <NIcon :size="28" color="#fff">
        <component :is="icon" />
      </NIcon>
    </div>
    <div class="tool-card-body">
      <h3 class="tool-card-title">{{ title }}</h3>
      <p class="tool-card-desc">{{ description }}</p>
    </div>
    <NButton text class="tool-card-arrow">
      <NIcon :size="18">
        <ChevronForwardOutline />
      </NIcon>
    </NButton>
  </div>
</template>

<style scoped>
.tool-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s ease;
}
.tool-card:hover {
  border-color: var(--arco-primary, #165DFF);
  box-shadow: 0 4px 16px rgba(22, 93, 255, 0.1);
  transform: translateY(-2px);
}
.tool-card-icon {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.tool-card-body {
  flex: 1;
  min-width: 0;
}
.tool-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0 0 4px;
}
.tool-card-desc {
  font-size: 13px;
  color: var(--neutral-text-3, #86909c);
  margin: 0;
  line-height: 1.4;
}
.tool-card-arrow {
  color: var(--neutral-text-3, #86909c);
  flex-shrink: 0;
}
.tool-card:hover .tool-card-arrow {
  color: var(--arco-primary, #165DFF);
}
</style>
