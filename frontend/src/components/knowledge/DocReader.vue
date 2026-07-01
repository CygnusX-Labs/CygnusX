<script setup lang="ts">
import { computed } from 'vue'
import { MdPreview, MdCatalog } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'

const props = defineProps<{
  content: string
}>()

const STATIC_IMAGE_BASE = '/docs-static/knowledge/'

/** 把 Markdown/HTML 中的相对图片路径解析为后端静态资源 URL */
const resolvedContent = computed(() => {
  let text = props.content || ''

  // 1) Markdown 图片语法: ![alt](figure/xxx.png "title") / ![alt](./figure/xxx.png)
  text = text.replace(
    /(!\[([^\]]*)\]\()(\.\/|)(figure\/[^)\s]+)(\s*"[^"]*")?(\))/g,
    (_match, prefix, _alt, _dot, relPath, title, suffix) =>
      `${prefix}${STATIC_IMAGE_BASE}${relPath}${title || ''}${suffix}`,
  )

  // 2) HTML <img> 标签: <img src="./figure/xxx.jpg" alt="...">
  text = text.replace(
    /<img\b([^>]*)\bsrc=["'](\.\/|)(figure\/[^"']+)["']([^>]*)>/gi,
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

// 预览容器的 id，供 MdCatalog 锚定滚动
const previewId = 'knowledge-md-preview'
// MdCatalog 需要 string | HTMLElement（非 null），computed 保证非空
const scrollElement = computed<HTMLElement>(
  () => document.documentElement as HTMLElement,
)
</script>

<template>
  <div class="reader-layout">
    <div class="reader-preview" :id="previewId">
      <MdPreview
        :model-value="resolvedContent"
        :previewTheme="'default'"
        :codeTheme="'github'"
      />
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
}

.reader-preview {
  flex: 0 0 80%;
  min-width: 0;
}

.reader-toc {
  flex: 0 0 20%;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 180px);
  overflow-y: auto;
  border-left: 1px solid var(--neutral-border);
  padding-left: 16px;
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
