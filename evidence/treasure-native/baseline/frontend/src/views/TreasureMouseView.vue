<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'

const Workbench = defineAsyncComponent(() => import('./TreasureResearchWorkbench.vue'))
const mode = ref<'original' | 'platform'>('original')
const loading = ref(true)
</script>

<template>
  <main class="treasure-entry" aria-label="科研寻宝鼠">
    <nav class="treasure-modes" aria-label="寻宝鼠工作区">
      <button :aria-pressed="mode === 'original'" @click="mode = 'original'">寻宝鼠</button>
      <button :aria-pressed="mode === 'platform'" @click="mode = 'platform'">平台数据与分析</button>
      <a href="/treasure-mouse/" target="_blank" rel="noopener">独立窗口 ↗</a>
    </nav>
    <section v-show="mode === 'original'" class="original-workspace">
      <p v-if="loading" class="loading" role="status">正在打开原版寻宝鼠…</p>
      <iframe title="寻宝鼠原版" src="/treasure-mouse/" @load="loading = false" />
    </section>
    <Workbench v-if="mode === 'platform'" />
  </main>
</template>

<style scoped>
.treasure-entry { display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--neutral-bg); }
.treasure-modes { display: flex; align-items: center; gap: 8px; padding: 6px 16px; border-bottom: 1px solid var(--neutral-border); }
.treasure-modes button, .treasure-modes a { padding: 6px 12px; border: 0; border-radius: 6px; background: transparent; color: var(--neutral-text-secondary); font: inherit; font-size: 13px; cursor: pointer; text-decoration: none; }
.treasure-modes button[aria-pressed="true"] { background: var(--neutral-card); color: var(--primary-color); }
.treasure-modes a { margin-left: auto; }
.original-workspace { position: relative; flex: 1; min-height: 0; }
iframe { display: block; width: 100%; height: 100%; border: 0; }
.loading { position: absolute; top: 12px; left: 16px; color: var(--neutral-text-secondary); }
</style>
