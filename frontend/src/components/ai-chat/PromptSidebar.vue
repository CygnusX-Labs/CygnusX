<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NIcon, NButton } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { loadBioPrompts } from './bioPrompts'
import type { BioPromptTemplate } from './types'

interface Props {
  visible: boolean
}

const props = defineProps<Props>()
const prompts = ref<BioPromptTemplate[]>([])
const loaded = ref(false)

const emit = defineEmits<{
  close: []
  select: [content: string]
}>()

// 按 category 分组
const grouped = computed(() => {
  const map = new Map<string, BioPromptTemplate[]>()
  for (const p of prompts.value) {
    if (!map.has(p.category)) map.set(p.category, [])
    map.get(p.category)!.push(p)
  }
  return Array.from(map.entries())
})

watch(() => props.visible, async (visible) => {
  if (!visible || loaded.value) return
  prompts.value = await loadBioPrompts().catch(() => [])
  loaded.value = true
}, { immediate: true })

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
        <div v-if="loaded && !grouped.length" class="prompt-empty">暂无可用提示词模板</div>
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
