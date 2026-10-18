<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { mount, type TreasureIslandHandle, type TreasureIslandProps } from '@treasure-island-poc'
const host = ref<HTMLElement>()
const locale = ref<'zh' | 'en'>(new URLSearchParams(location.search).get('lang') === 'en' ? 'en' : 'zh')
const theme = ref<'light' | 'dark'>(new URLSearchParams(location.search).get('theme') === 'dark' ? 'dark' : 'light')
const draft = ref('')
const model = ref('平台模型 A')
const streaming = ref(false)
const visible = ref(true)
const events = ref<{ event: string; value?: string }[]>([])
let island: TreasureIslandHandle | undefined
function record(event: string, value?: string) { events.value.push({ event, value }) }
const props = computed<TreasureIslandProps>(() => ({
  context: { projectId: null, projectName: '全局只读发现', locale: locale.value, theme: theme.value },
  messages: [], modelOptions: ['平台模型 A', '平台模型 B'], selectedModel: model.value,
  draft: draft.value, streaming: streaming.value, disabled: false,
  onDraftChange: (value) => { draft.value = value },
  onSubmit: (value) => record('submit', value),
  onPickExample: (value) => { draft.value = value; record('example', value) },
  onCancel: () => { streaming.value = false; record('cancel') },
  onSelectModel: (value) => { model.value = value; record('model', value) },
  onOpenDataset: (value) => record('dataset', value),
}))
function enter() { if (host.value && !island) { island = mount(host.value, props.value); record('mount') } }
function leave() { island?.unmount(); island = undefined; record('unmount') }
function toggle() { if (visible.value) leave(); visible.value = !visible.value }
watch(props, value => island?.update(value))
watch(host, () => { if (visible.value) enter() })
onMounted(enter)
onUnmounted(leave)
</script>
<template>
  <nav aria-label="隔离 PoC 控制台">
    <strong id="platform-sentinel">Vue Shell · 隔离展示 PoC</strong>
    <button id="route-toggle" @click="toggle">{{ visible ? '离开页面' : '进入页面' }}</button>
    <button id="theme-toggle" @click="theme = theme === 'light' ? 'dark' : 'light'">{{ theme }}</button>
    <button id="locale-toggle" @click="locale = locale === 'zh' ? 'en' : 'zh'">{{ locale }}</button>
    <button id="stream-toggle" @click="streaming = !streaming">测试停止态</button>
  </nav>
  <main><div v-if="visible" ref="host" id="treasure-island-host" /></main>
  <output id="events">{{ JSON.stringify(events) }}</output>
</template>
<style>
/* Deliberately conflicting platform styles: the original UI must stay isolated. */
body { margin: 0; font: 14px system-ui; background: #eef0f4; color: #25304a; }
nav { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px; align-items: center; }
button { border: 2px solid #5064a0; border-radius: 2px; padding: 6px; font-family: monospace; }
h1 { font-size: 60px; color: red; } section { background: purple; }
main { min-height: calc(100vh - 58px); } #treasure-island-host { min-height: inherit; }
#events { display: block; max-height: 70px; overflow: auto; font-size: 11px; padding: 8px; }
</style>
