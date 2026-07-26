<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { MdPreview, MdCatalog } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { NAlert } from 'naive-ui'
import { useThemeStore } from '@/stores/theme'
import DocEditors from '@/components/knowledge/DocEditors.vue'
import DocIssues from '@/components/knowledge/DocIssues.vue'
import type { KnowledgeDoc } from '@/types/knowledge'

const themeStore = useThemeStore()
const mdTheme = computed<'light' | 'dark'>(() => (themeStore.isDark ? 'dark' : 'light'))

const props = defineProps<{
  doc: KnowledgeDoc
}>()

const emit = defineEmits<{
  refresh: []
}>()

const STATIC_IMAGE_BASE = '/docs-static/knowledge/'

/** 把 Markdown/HTML 中的相对图片路径解析为后端静态资源 URL */
const resolvedContent = computed(() => {
  let text = props.doc.content || ''

  // 1) Markdown 图片语法: ![alt](figure/xxx.png "title") / ![alt](./figure/xxx.png)
  text = text.replace(
    /(!\[([^\]]*)\]\()(\.\/|)(figure\/[^)\s]+)(\s*"[^"]*")?(\))/g,
    (_match, prefix, _alt, _dot, relPath, title, suffix) =>
      `${prefix}${STATIC_IMAGE_BASE}${relPath}${title || ''}${suffix}`,
  )

  // 2) HTML <img> 标签: <img src="./figure/xxx.jpg" alt="...">
  text = text.replace(
    /<img\b([^\u003e]*)\bsrc=["'](\.\/|)(figure\/[^"']+)["']([^\u003e]*)\u003e/gi,
    (_match, before, _dot, relPath, after) => {
      const altMatch =
        (after as string).match(/alt=["']([^"']*)["']/) ||
        (before as string).match(/alt=["']([^"']*)["']/)
      const alt = altMatch ? altMatch[1] : ''
      return `![${alt}](${STATIC_IMAGE_BASE}${relPath})`
    },
  )

  return text
})

const hasPendingRevision = computed(() => !!props.doc.pendingRevision)

// 预览容器的 id，供 MdCatalog 锚定滚动
const previewId = 'knowledge-md-preview'
const scrollElement = ref<HTMLElement>(document.documentElement)

onMounted(() => {
  const previewEl = document.getElementById(previewId)
  const scrollParent = previewEl?.closest('.content-body') as HTMLElement | null
  if (scrollParent) scrollElement.value = scrollParent
})
</script>

<template>
  <div class="reader-layout">
    <div class="reader-preview" :id="previewId">
      <NAlert
        v-if="hasPendingRevision"
        type="warning"
        :show-icon="false"
        class="pending-alert"
      >
        当前版本正在审核中，您看到的是上一个已发布版本。
      </NAlert>

      <MdPreview
        :model-value="resolvedContent"
        :theme="mdTheme"
        :preview-theme="'default'"
        :code-theme="'github'"
      />

      <DocEditors :editors="doc.editors" />
      <DocIssues :doc-id="doc.id" :issues="doc.issues" @refresh="$emit('refresh')" />
    </div>
    <aside class="reader-toc">
      <div class="toc-title">大纲</div>
      <MdCatalog
        :model-value="resolvedContent"
        :editorId="previewId"
        :scrollElement="scrollElement"
      />
    </aside>
  </div>
</template>

<style scoped>
.reader-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  min-width: 0; /* ← 防吹爆：允许整行窄于 min-content */
  background-color: var(--neutral-card);
  color: var(--neutral-text-1);
}

.reader-preview {
  flex: 0 0 80%;
  min-width: 0; /* 允许窄于 min-content，长字符串不再顶开本格 */
  overflow-wrap: anywhere; /* Markdown 长 URL / 长字符串自动折行，不撑爆预览区 */
  background-color: var(--neutral-card);
}

.pending-alert {
  margin-bottom: 16px;
}

.reader-toc {
  flex: 0 0 20%;
  min-width: 0; /* ← 防吹爆 */
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 180px);
  overflow-y: auto;
  border-left: 1px solid var(--neutral-border);
  padding-left: 16px;
  background-color: var(--neutral-card);
}

.toc-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-3);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.reader-toc :deep(.md-editor-catalog) {
  font-size: 13px;
}

.reader-toc :deep(.md-editor-catalog-link) {
  color: var(--neutral-text-3);
  padding: 4px 0;
}

.reader-toc :deep(.md-editor-catalog-link:hover) {
  color: var(--arco-primary);
}

.reader-toc :deep(.md-editor-catalog-active > .md-editor-catalog-link) {
  color: var(--arco-primary);
  font-weight: 500;
}

.reader-preview :deep(.md-editor),
.reader-preview :deep(.md-editor-dark) {
  --md-bk-color: var(--neutral-card);
  --md-bk-color-outstand: var(--neutral-hover);
  --md-bk-hover-color: var(--neutral-hover);
  --md-color: var(--neutral-text-1);
  --md-hover-color: var(--neutral-text-1);
  --md-border-color: var(--neutral-border);
  --md-border-hover-color: var(--neutral-border);
  background-color: var(--neutral-card);
  border-color: transparent; /* 预览模式去外框，与外层卡片无缝融合 */
}

.reader-preview :deep(.md-editor-content),
.reader-preview :deep(.md-editor-preview-wrapper),
.reader-preview :deep(.md-editor-preview) {
  background-color: var(--neutral-card);
  color: var(--neutral-text-1);
}

.reader-preview :deep(.md-editor-preview pre),
.reader-preview :deep(.md-editor-preview blockquote),
.reader-preview :deep(.md-editor-preview table thead th) {
  background-color: var(--neutral-hover);
}
.reader-preview :deep(.md-editor-preview :not(pre) > code) {
  background-color: var(--neutral-hover);
}
.reader-preview :deep(.md-editor-preview blockquote) {
  border-left-color: var(--neutral-border);
}
.reader-preview :deep(.md-editor-preview table td),
.reader-preview :deep(.md-editor-preview table th) {
  border-color: var(--neutral-border);
}
.reader-toc :deep(.md-editor-catalog) {
  background-color: var(--neutral-card);
}

@media (max-width: 1024px) {
  .reader-layout {
    flex-direction: column;
  }
  .reader-preview {
    flex: 1 1 auto;
  }
  .reader-toc {
    position: static;
    max-height: 240px;
    border-left: none;
    border-top: 1px solid var(--neutral-border);
    padding-left: 0;
    padding-top: 12px;
  }
}
</style>
