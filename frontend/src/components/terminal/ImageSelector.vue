<script setup lang="ts">
import { computed } from 'vue'
import { NCard, NTag, NSpace, NRadio } from 'naive-ui'
import type { TerminalImage } from '@/types/terminal'

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
  <div class="image-selector">
    <NCard
      v-for="img in images"
      :key="img.id"
      size="small"
      hoverable
      :class="['image-card', { active: selectedId === img.id }]"
      @click="selectImage(img.id)"
    >
      <div class="card-content">
        <div class="image-icon">{{ img.icon }}</div>
        <div class="image-info">
          <div class="info-header">
            <span class="image-name">{{ img.name }}</span>
            <NRadio
              :checked="selectedId === img.id"
              :value="img.id"
              @click.stop
              @update:checked="selectImage(img.id)"
            />
          </div>
          <p class="image-desc">{{ img.description }}</p>
          <NSpace size="small" class="image-tags">
            <NTag v-for="tag in img.tags" :key="tag" size="tiny" round>{{ tag }}</NTag>
          </NSpace>
          <div class="image-resources">
            默认资源：{{ img.resources.memory_mb }} MB / {{ img.resources.cpu_cores }} 核
          </div>
        </div>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.image-selector {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  width: 100%;
}

.image-card {
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.image-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.image-card.active {
  border-color: var(--n-primary-color, #18a058);
  background: rgba(24, 160, 88, 0.04);
}

.card-content {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.image-icon {
  font-size: 40px;
  line-height: 1;
  flex-shrink: 0;
}

.image-info {
  flex: 1;
  min-width: 0;
}

.info-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.image-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--n-text-color-base);
}

.image-desc {
  font-size: 13px;
  color: var(--n-text-color-3);
  line-height: 1.5;
  margin: 0 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.image-tags {
  margin-bottom: 8px;
}

.image-resources {
  font-size: 12px;
  color: var(--n-text-color-2);
}
</style>
