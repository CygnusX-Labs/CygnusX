<script setup lang="ts">
import { computed } from 'vue'
import { NTag, NSpace } from 'naive-ui'
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
  <div class="image-selector" role="radiogroup" aria-label="终端镜像">
    <button
      v-for="img in images"
      :key="img.id"
      type="button"
      class="image-item omichub-selectable-card"
      :class="{ active: selectedId === img.id, 'is-selected': selectedId === img.id }"
      role="radio"
      :aria-checked="selectedId === img.id"
      @click="selectImage(img.id)"
    >
      <span class="image-radio" aria-hidden="true">
        <span v-if="selectedId === img.id" class="radio-dot" />
      </span>
      <span class="image-info">
        <span class="image-name">{{ img.icon }} {{ img.name }}</span>
        <span class="image-desc">{{ img.description }}</span>
        <NSpace size="small" class="image-tags">
          <NTag v-for="tag in img.tags" :key="tag" size="tiny" round>{{ tag }}</NTag>
        </NSpace>
        <span class="image-resources">
          默认资源：{{ img.resources.memory_mb }} MB / {{ img.resources.cpu_cores }} 核
        </span>
      </span>
    </button>
  </div>
</template>

<style scoped>
.image-selector {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.image-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  min-height: 132px;
  padding: 16px;
  border: 2px solid var(--neutral-border);
  border-radius: 10px;
  background: var(--neutral-card);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.image-item:hover {
  border-color: var(--arco-primary);
  background: var(--neutral-hover);
  transform: translateY(-1px);
}

.image-item.active {
  border-color: var(--arco-primary);
  background: var(--neutral-hover);
  box-shadow: 0 0 0 3px rgba(46, 91, 255, 0.08);
}

.image-radio {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border: 2px solid var(--neutral-border);
  border-radius: 50%;
  background: var(--neutral-card);
  flex: 0 0 auto;
}

.image-item.active .image-radio {
  border-color: var(--arco-primary);
  background: var(--arco-primary);
}

.radio-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #fff;
}

.image-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.image-name {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--neutral-text-1);
}

.image-desc {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--neutral-text-3);
}

.image-tags {
  margin-top: 8px;
}

.image-resources {
  margin-top: 8px;
  font-size: 12px;
  color: var(--neutral-text-3);
}
</style>
