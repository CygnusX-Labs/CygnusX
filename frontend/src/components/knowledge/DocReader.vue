<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { MdPreview, MdCatalog } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
// md-editor-v3 的 MdPreview.theme 默认 'light'，需显式同步应用主题，否则暗黑下正文为白底
const mdTheme = computed<'light' | 'dark'>(() => (themeStore.isDark ? 'dark' : 'light'))

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
      <MdPreview
        :model-value="resolvedContent"
        :theme="mdTheme"
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
  min-width: 0; /* ← 防吹爆：允许整行窄于 min-content */
}

.reader-preview {
  flex: 0 0 80%;
  min-width: 0; /* 允许窄于 min-content，长字符串不再顶开本格 */
  overflow-wrap: anywhere; /* Markdown 长 URL / 长字符串自动折行，不撑爆预览区 */
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

/* ===== 统一 md-editor-v3 背景到平台主题变量，消除正文区"纯黑洞"色差 =====
   背景：md-editor dark 主题默认 --md-bk-color:#000（见 md-editor-v3/lib/preview.css
   .md-editor-dark），与外层 NCard（--neutral-card，深色 #151A25）形成强色差，阅读时
   产生明显"黑洞"感。
   方案：把 md-editor 内部变量映射到平台中性色变量——
   - 正文背景 → --neutral-card：与外层 NCard 完全一致，消除色差
   - 代码块/引用块/表格表头 → --neutral-hover：比 card 高 5-10% 明度，保留层级但不纯黑
   - 正文文字 → --neutral-text-1（对比度充足），边框 → --neutral-border
   全部走 var()，:root[data-theme] 切换时自动适配，无任何硬编码颜色。
   :deep 编译为 [data-v-xxx] .md-editor，优先级高于全局 .md-editor / .md-editor-dark，
   可稳定覆盖 md-editor 自带变量。 */
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

/* 代码块、引用块、表格表头：用 --neutral-hover 形成 subtle 层级（非纯黑）。
   变量映射已让依赖 --md-bk-color-outstand 的元素跟随，此处对 pre/blockquote/th 显式
   兜底，防止 codeTheme（github）自带背景色压过变量。 */
.reader-preview :deep(.md-editor-preview pre),
.reader-preview :deep(.md-editor-preview blockquote),
.reader-preview :deep(.md-editor-preview table thead th) {
  background-color: var(--neutral-hover);
}
/* 行内 code：轻微底色，与代码块同色系 */
.reader-preview :deep(.md-editor-preview :not(pre) > code) {
  background-color: var(--neutral-hover);
}
/* 引用块/表格边框统一到中性边框 */
.reader-preview :deep(.md-editor-preview blockquote) {
  border-left-color: var(--neutral-border);
}
.reader-preview :deep(.md-editor-preview table td),
.reader-preview :deep(.md-editor-preview table th) {
  border-color: var(--neutral-border);
}
/* TOC 大纲区：透明背景，跟随外层卡片底色，与正文同底（MdCatalog 自身无背景，此处兜底） */
.reader-toc :deep(.md-editor-catalog) {
  background: transparent;
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
