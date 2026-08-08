<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { studioApi } from '@/api/studio'
import type { ToolCall } from './types'

interface ArtifactItem {
  path: string
  size?: number
  mtime?: number
}

const props = withDefaults(defineProps<{
  sessionId?: string
  tools?: ToolCall[]
  /** Agent/worker 直接回传的产物映射；键通常是工作区相对路径。 */
  artifacts?: unknown
}>(), {
  sessionId: '',
  tools: () => [],
  artifacts: undefined,
})

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp'])
const PREVIEW_EXTENSIONS = new Set([...IMAGE_EXTENSIONS, 'pdf'])
const previewUrls = ref<Record<string, string>>({})
const unavailablePreviews = ref(new Set<string>())

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
}

function artifactPath(value: unknown): string {
  const normalize = (raw: string) => {
    const trimmed = raw.trim().replace(/\\/g, '/')
    const outputIndex = trimmed.indexOf('/output/')
    if (outputIndex >= 0) return trimmed.slice(outputIndex + 1)
    return trimmed.startsWith('output/') ? trimmed : trimmed
  }
  if (typeof value === 'string') return normalize(value)
  const item = asRecord(value)
  return typeof item?.path === 'string' ? normalize(item.path) : ''
}

function artifactDetails(value: unknown): ArtifactItem | undefined {
  const path = artifactPath(value)
  if (!path) return undefined
  const item = asRecord(value)
  return {
    path,
    size: typeof item?.size === 'number' ? item.size : undefined,
    mtime: typeof item?.mtime === 'number' ? item.mtime : undefined,
  }
}

function artifactDetailsFromEntry(pathValue: unknown, metadata: unknown): ArtifactItem | undefined {
  const path = artifactPath(pathValue)
  if (!path) return undefined
  const item = asRecord(metadata)
  return {
    path,
    size: typeof item?.size === 'number' ? item.size : undefined,
    mtime: typeof item?.mtime === 'number' ? item.mtime : undefined,
  }
}

function directArtifacts(value: unknown): ArtifactItem[] {
  if (Array.isArray(value)) {
    return value
      .map(artifactDetails)
      .filter((item): item is ArtifactItem => Boolean(item))
  }
  const record = asRecord(value)
  if (!record) return []
  return Object.entries(record)
    .map(([path, metadata]) => artifactDetailsFromEntry(path, metadata))
    .filter((item): item is ArtifactItem => Boolean(item))
}

function collectArtifacts(tool: ToolCall): ArtifactItem[] {
  const result = asRecord(tool.result)
  const nestedPayload = asRecord(result?.ui_payload) || asRecord(result?.uiPayload)
  const sources = [tool.uiPayload?.artifacts, result?.artifacts, nestedPayload?.artifacts]
  return sources.flatMap((source) => Array.isArray(source)
    ? source.map(artifactDetails).filter((item): item is ArtifactItem => Boolean(item))
    : [])
}

const artifactItems = computed(() => {
  const unique = new Map<string, ArtifactItem>()
  for (const tool of props.tools) {
    for (const artifact of collectArtifacts(tool)) unique.set(artifact.path, artifact)
  }
  for (const artifact of directArtifacts(props.artifacts)) unique.set(artifact.path, artifact)
  return [...unique.values()]
})

const previewArtifacts = computed(() =>
  artifactItems.value.filter((artifact) => PREVIEW_EXTENSIONS.has(artifact.path.split('.').pop()?.toLowerCase() || '')),
)

const otherArtifacts = computed(() =>
  artifactItems.value.filter((artifact) => !previewArtifacts.value.some((preview) => preview.path === artifact.path)),
)

function isImageArtifact(path: string): boolean {
  return IMAGE_EXTENSIONS.has(path.split('.').pop()?.toLowerCase() || '')
}

function fileName(path: string): string {
  return path.split('/').pop() || path
}

function clearPreviews() {
  for (const url of Object.values(previewUrls.value)) URL.revokeObjectURL(url)
  previewUrls.value = {}
  unavailablePreviews.value = new Set()
}

async function loadPreviews() {
  clearPreviews()
  if (!props.sessionId) return
  await Promise.all(previewArtifacts.value.map(async (artifact) => {
    try {
      previewUrls.value[artifact.path] = await studioApi.fetchArtifactBlob(props.sessionId, artifact.path)
    } catch {
      unavailablePreviews.value = new Set([...unavailablePreviews.value, artifact.path])
    }
  }))
}

function downloadArtifact(path: string) {
  if (!props.sessionId) return
  void studioApi.downloadArtifact(props.sessionId, path)
}

watch(
  () => [props.sessionId, previewArtifacts.value.map((artifact) => artifact.path).join('|')],
  () => { void loadPreviews() },
  { immediate: true },
)

onBeforeUnmount(clearPreviews)
</script>

<template>
  <section v-if="artifactItems.length" class="message-artifacts" aria-label="分析产物">
    <div class="message-artifacts__header">
      <div>
        <span class="message-artifacts__eyebrow">分析产物</span>
        <strong>已生成 {{ artifactItems.length }} 个文件</strong>
      </div>
      <span class="message-artifacts__hint">预览与下载</span>
    </div>

    <div v-if="previewArtifacts.length" class="message-artifacts__images">
      <figure v-for="artifact in previewArtifacts" :key="artifact.path" class="message-artifacts__image-card">
        <div class="message-artifacts__preview">
          <img
            v-if="isImageArtifact(artifact.path) && previewUrls[artifact.path]"
            :src="previewUrls[artifact.path]"
            :alt="`${fileName(artifact.path)} 预览`"
          />
          <iframe
            v-else-if="previewUrls[artifact.path]"
            :src="previewUrls[artifact.path]"
            :title="`${fileName(artifact.path)} PDF 预览`"
            class="message-artifacts__pdf"
          />
          <span v-else class="message-artifacts__fallback" aria-live="polite">
            {{ unavailablePreviews.has(artifact.path) ? '暂时无法预览，可直接下载文件' : '正在加载预览…' }}
          </span>
        </div>
        <figcaption>
          <span class="message-artifacts__file-name" :title="artifact.path">{{ fileName(artifact.path) }}</span>
          <button type="button" class="message-artifacts__download" @click="downloadArtifact(artifact.path)">
            下载图片
          </button>
        </figcaption>
      </figure>
    </div>

    <ul v-if="otherArtifacts.length" class="message-artifacts__files">
      <li v-for="artifact in otherArtifacts" :key="artifact.path">
        <span class="message-artifacts__file-name" :title="artifact.path">{{ fileName(artifact.path) }}</span>
        <button type="button" class="message-artifacts__download" @click="downloadArtifact(artifact.path)">
          下载
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.message-artifacts {
  margin-top: var(--space-lg, 16px);
  padding: var(--space-md, 12px);
  border: 1px solid var(--stardust-border-soft);
  border-radius: var(--radius-card, 12px);
  background: var(--bg-card);
}

.message-artifacts__header,
.message-artifacts__image-card figcaption,
.message-artifacts__files li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm, 8px);
}

.message-artifacts__header {
  margin-bottom: var(--space-md, 12px);
}

.message-artifacts__header > div {
  display: grid;
  gap: 2px;
}

.message-artifacts__eyebrow,
.message-artifacts__hint {
  color: var(--text-tertiary);
  font-size: 12px;
}

.message-artifacts__header strong {
  color: var(--text-primary);
  font-size: 14px;
}

.message-artifacts__images {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-md, 12px);
}

.message-artifacts__image-card {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  border: 1px solid var(--stardust-border-soft);
  border-radius: calc(var(--radius-card, 12px) - 2px);
  background: var(--bg-secondary);
}

.message-artifacts__preview {
  display: grid;
  min-height: 180px;
  place-items: center;
  overflow: hidden;
  background: color-mix(in srgb, var(--bg-card) 86%, var(--brand-primary-light));
}

.message-artifacts__preview img {
  display: block;
  width: 100%;
  max-height: 360px;
  object-fit: contain;
}

.message-artifacts__pdf {
  display: block;
  width: 100%;
  height: 360px;
  border: 0;
  background: #fff;
}

.message-artifacts__fallback {
  padding: var(--space-md, 12px);
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: center;
}

.message-artifacts__image-card figcaption,
.message-artifacts__files li {
  padding: var(--space-sm, 8px) var(--space-md, 12px);
}

.message-artifacts__files {
  display: grid;
  gap: 1px;
  margin: var(--space-md, 12px) 0 0;
  padding: 0;
  overflow: hidden;
  list-style: none;
  border: 1px solid var(--stardust-border-soft);
  border-radius: calc(var(--radius-card, 12px) - 2px);
}

.message-artifacts__files li {
  background: var(--bg-card);
}

.message-artifacts__files li + li {
  border-top: 1px solid var(--stardust-border-soft);
}

.message-artifacts__file-name {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-artifacts__download {
  flex: 0 0 auto;
  padding: 4px 8px;
  color: var(--brand-primary);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  background: var(--brand-primary-light);
  border: 0;
  border-radius: 6px;
  cursor: pointer;
}

.message-artifacts__download:hover {
  background: color-mix(in srgb, var(--brand-primary-light) 72%, var(--brand-primary));
}

.message-artifacts__download:focus-visible {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}

@media (max-width: 640px) {
  .message-artifacts__header,
  .message-artifacts__image-card figcaption,
  .message-artifacts__files li {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (prefers-reduced-transparency: reduce) {
  .message-artifacts__preview {
    background: var(--bg-secondary);
  }
}
</style>
