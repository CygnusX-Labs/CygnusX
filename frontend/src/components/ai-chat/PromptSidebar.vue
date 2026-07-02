<script setup lang="ts">
import { computed } from 'vue'
import { NIcon, NButton } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { BIO_PROMPTS } from './bioPrompts'
import type { BioPromptTemplate } from './types'

interface Props {
  visible: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  close: []
  select: [content: string]
}>()

// 按 category 分组
const grouped = computed(() => {
  const map = new Map<string, BioPromptTemplate[]>()
  for (const p of BIO_PROMPTS) {
    if (!map.has(p.category)) map.set(p.category, [])
    map.get(p.category)!.push(p)
  }
  return Array.from(map.entries())
})

function handleSelect(content: string) {
  emit('select', content)
  emit('close')
}
</script>

<template>
  <template v-if="visible">
    <div class="prompt-overlay" @click="emit('close')" />
    <aside class="prompt-sidebar">
      <div class="sidebar-header">
        <span class="title">提示词模板</span>
        <n-button text @click="emit('close')">
          <n-icon size="20"><CloseOutline /></n-icon>
        </n-button>
      </div>
      <div class="sidebar-body">
        <div v-for="[category, items] in grouped" :key="category">
          <div class="group-label">{{ category }}</div>
          <div
            v-for="p in items"
            :key="p.id"
            class="prompt-card"
            @click="handleSelect(p.content)"
          >
            <div class="card-title">{{ p.title }}</div>
            <div class="card-desc">{{ p.description }}</div>
          </div>
        </div>
      </div>
    </aside>
  </template>
</template>
