<script setup lang="ts">
import { computed } from 'vue'
import { NEmpty, NTag, NSpace } from 'naive-ui'
import type { TerminalImage } from '@/types/terminal'
import { formatMemoryMb } from '@/utils/terminal'

interface Props {
  images: TerminalImage[]
  modelValue: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const selectedId = computed({
  get: () => props.modelValue ?? '',
  set: (val) => emit('update:modelValue', val),
})

function selectImage(id: string) {
  selectedId.value = id
}

</script>

<template>
  <div class="image-selector" role="radiogroup" aria-label="终端镜像">
    <button
      v-for="img in images"
      :key="img.id"
      type="button"
      class="image-item omichub-selectable-card"
      :class="{ 'is-selected': selectedId === img.id }"
      role="radio"
      :aria-checked="selectedId === img.id"
      @click="selectImage(img.id)"
    >
      <span v-if="selectedId === img.id" class="selection-badge" aria-hidden="true">✓</span>
      <span class="image-info">
        <span class="image-title">
          <span class="image-icon">{{ img.icon }}</span>
          <span class="image-name">{{ img.name }}</span>
        </span>
        <span class="image-desc">{{ img.description }}</span>
        <NSpace size="small" class="image-tags">
          <NTag v-for="tag in img.tags" :key="tag" size="tiny" round>{{ tag }}</NTag>
        </NSpace>
        <span class="image-meta">
          默认 {{ formatMemoryMb(img.resources.memory_mb) }} / {{ img.resources.cpu_cores }} 核
          <span v-if="img.tags.length"> · {{ img.tags.length }} 类工具</span>
        </span>
      </span>
    </button>
    <NEmpty v-if="images.length === 0" size="small" description="暂无可用镜像" />
  </div>
</template>

<style scoped>
.image-selector {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: 14px;
  align-items: stretch;
  width: 100%;
}

.image-item {
  position: relative;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 18px;
  border: 2px solid transparent;
  border-radius: 12px;
  background: var(--neutral-card);
  box-shadow: inset 0 0 0 1px var(--neutral-border);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.image-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.image-item:focus-visible {
  outline: 3px solid var(--arco-primary);
  outline-offset: 2px;
}

.selection-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: absolute;
  top: 14px;
  right: 14px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--arco-primary);
  color: var(--neutral-card);
  font-size: 13px;
  font-weight: 700;
}

.image-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.image-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.image-icon {
  display: inline-flex;
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  line-height: 1;
}

.image-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--neutral-text-1);
}

.image-desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  min-height: 41.6px;
  color: var(--neutral-text-3);
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.image-tags {
  margin-top: 8px;
  overflow: hidden;
  white-space: nowrap;
}

.image-tags :deep(.n-space) {
  flex-wrap: nowrap;
}

.image-tags :deep(.n-tag) {
  flex: 0 0 auto;
  border-radius: 999px;
  font-size: 12px;
}

.image-meta {
  margin-top: auto;
  padding-top: 12px;
  font-size: 12px;
  color: var(--neutral-text-3);
}

@media (max-width: 640px) {
  .image-selector {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .image-item {
    transition: none;
  }
}
</style>
