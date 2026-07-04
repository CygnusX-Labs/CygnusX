<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NSpin, NEmpty, NButton, NSpace, NIcon, useMessage } from 'naive-ui'
import { CreateOutline, SaveOutline, CloseOutline, CloudDownloadOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import DocTree from '@/components/knowledge/DocTree.vue'
import DocReader from '@/components/knowledge/DocReader.vue'
import DocEditor from '@/components/knowledge/DocEditor.vue'
import type { KnowledgeItem, KnowledgeDoc, DocTreeNode } from '@/types/knowledge'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const navTitle = ref('实验室知识库')
const navItems = ref<KnowledgeItem[]>([])
const activeDoc = ref<KnowledgeDoc | null>(null)
const isEditMode = ref(false)

const loadingNav = ref(false)
const loadingDoc = ref(false)
const saving = ref(false)

/** 编辑缓冲：进入编辑模式时快照原文，取消时还原 */
const editBuffer = ref('')
const draftContent = ref('')

/** 由扁平导航按 category 聚合成树形结构 */
const documentTree = computed<DocTreeNode[]>(() => {
  const groups = new Map<string, KnowledgeItem[]>()
  for (const item of navItems.value) {
    const cat = item.category || '未分类'
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push(item)
  }
  return Array.from(groups.entries()).map(([cat, items]) => ({
    key: `cat:${cat}`,
    label: cat,
    isCategory: true,
    children: items.map((it) => ({
      key: `doc:${it.id}`,
      label: it.title,
      docId: it.id,
    })),
  }))
})

async function fetchNav() {
  loadingNav.value = true
  try {
    const res = await apiClient.get<{ title: string; items: KnowledgeItem[] }>(
      '/docs/knowledge',
    )
    navTitle.value = res.data.title
    navItems.value = res.data.items
  } catch {
    message.error('获取知识库目录失败')
    navItems.value = []
  } finally {
    loadingNav.value = false
  }
}

async function fetchDoc(docId: string) {
  loadingDoc.value = true
  try {
    const res = await apiClient.get<KnowledgeDoc>(`/docs/knowledge/${docId}`)
    activeDoc.value = res.data
  } catch {
    message.error('获取文档内容失败')
    activeDoc.value = null
  } finally {
    loadingDoc.value = false
  }
}

function selectDoc(docId: string) {
  if (isEditMode.value) {
    message.warning('请先保存或取消当前编辑')
    return
  }
  router.push({ name: 'knowledge-doc', params: { docId } })
}

function startEdit() {
  if (!activeDoc.value) return
  editBuffer.value = activeDoc.value.content
  draftContent.value = activeDoc.value.content
  isEditMode.value = true
}

function cancelEdit() {
  draftContent.value = editBuffer.value
  isEditMode.value = false
}

async function saveDoc() {
  if (!activeDoc.value) return
  if (!authStore.isAdmin) {
    message.error('仅管理员可保存文档')
    return
  }
  saving.value = true
  try {
    await apiClient.put(`/docs/knowledge/${activeDoc.value.id}`, {
      content: draftContent.value,
    })
    // 控制台打印当前 Markdown（任务要求，便于后续对接后端时排查）
    console.log('[知识库保存]', activeDoc.value.id, draftContent.value)
    isEditMode.value = false
    message.success('保存成功')
    await fetchDoc(activeDoc.value.id)
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    message.error(detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// 路由参数变化时拉取文档
watch(
  () => route.params.docId as string | undefined,
  (docId) => {
    if (docId) {
      void fetchDoc(docId)
    }
  },
  { immediate: true },
)

onMounted(async () => {
  await fetchNav()
  // 进入页面若未指定文档，默认选第一个叶子
  const docId = route.params.docId as string | undefined
  if (!docId && documentTree.value.length > 0) {
    const firstLeaf = documentTree.value[0].children?.[0]
    if (firstLeaf?.docId) {
      router.replace({ name: 'knowledge-doc', params: { docId: firstLeaf.docId } })
    }
  }
})
</script>

<template>
  <div class="docs-layout page-container">
    <!-- 左侧目录树 -->
    <div class="docs-sider">
      <NCard :bordered="false" class="arco-card nav-card">
        <div class="nav-title">{{ navTitle }}</div>
        <NSpin :show="loadingNav">
          <DocTree
            v-if="documentTree.length"
            :tree-data="documentTree"
            :active-id="activeDoc?.id"
            @select="selectDoc"
          />
          <NEmpty v-else description="暂无文档" />
        </NSpin>
      </NCard>
    </div>

    <!-- 右侧主体 -->
    <div class="docs-main">
      <NCard :bordered="false" class="arco-card content-card">
        <!-- 顶部栏 -->
        <div class="content-header">
          <h2 class="doc-title">
            {{ activeDoc?.title || '请选择左侧文档' }}
          </h2>
          <NSpace v-if="activeDoc">
            <template v-if="!isEditMode">
              <NButton
                v-if="authStore.isAdmin"
                size="small"
                type="primary"
                ghost
                @click="startEdit"
              >
                <template #icon><NIcon><CreateOutline /></NIcon></template>
                编辑
              </NButton>
            </template>
            <template v-else>
              <NButton size="small" @click="cancelEdit">
                <template #icon><NIcon><CloseOutline /></NIcon></template>
                取消
              </NButton>
              <NButton size="small" type="primary" :loading="saving" @click="saveDoc">
                <template #icon><NIcon><SaveOutline /></NIcon></template>
                保存
              </NButton>
            </template>
          </NSpace>
        </div>

        <!-- 内容区 -->
        <NSpin :show="loadingDoc">
          <div v-if="activeDoc" class="content-body">
            <!-- 编辑模式：满宽编辑器，隐藏 TOC -->
            <DocEditor
              v-if="isEditMode"
              v-model="draftContent"
            />
            <!-- 阅读模式：预览 80% + 大纲 20% -->
            <DocReader v-else :content="activeDoc.content" />
          </div>
          <NEmpty v-else description="请选择左侧文档进行阅读">
            <template #icon>
              <NIcon :size="48"><CloudDownloadOutline /></NIcon>
            </template>
          </NEmpty>
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.docs-layout {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0 !important;
  overflow: hidden;
  padding: 0; /* 覆盖 .page-container 的 24px padding，外层 NLayoutContent 已有 */
}

.docs-sider {
  width: 220px; /* 由 250px 收窄，减少右侧冗余留白 */
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.docs-sider :deep(.arco-card) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 穿透 NCard 内容区覆盖默认 padding。
   ⚠️ Naive UI 真实类名是 n-card-content（连字符），不是 n-card__content（BEM 双下划线）——
   写成 .n-card__content 会不命中（与正文区同类问题）。左右 16px 让内容在更窄卡片里更舒展。 */
.docs-sider :deep(.n-card > .n-card-content) {
  padding: 16px 12px;
}

.nav-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin-bottom: 12px;
  padding: 0;
  text-align: center; /* 标题居中，视觉更平衡 */
}

/* 树节点：轻微水平内边距，避免紧贴内容区左缘；NTree 自身层级缩进不动 */
.docs-sider :deep(.n-tree-node) {
  padding: 0 4px;
}

.docs-main {
  flex: 1;
  min-width: 0;   /* 允许水平收缩，防 Flex Blowout */
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 兜底：严禁 .docs-main 自身溢出 */
}

/* NCard 根节点：跟随父级高度/宽度收缩 */
.docs-main > :deep(.n-card) {
  flex: 1;
  min-width: 0;   /* ← 防吹爆：允许窄于 min-content */
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* NCard 内容区：类名 n-card-content（连字符，不是 n-card__content）。
   只传递 flex 约束，自身不滚动；padding 清零下放给 .content-header/.content-body。 */
.docs-main > :deep(.n-card > .n-card-content) {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 !important;
  overflow: hidden !important; /* 这一层绝对不滚动，只传递约束 */
}

/* NSpin 两层包裹也必须传递 flex + min-width:0，否则链路断在 NSpin */
.docs-main > :deep(.n-card .n-spin-container) {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.docs-main > :deep(.n-card .n-spin-content) {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px 12px; /* 水平 24px 与 .content-body 对齐，标题与正文左右不错位 */
  margin-bottom: 16px;
  border-bottom: 1px solid var(--neutral-border);
  flex-shrink: 0;
}

.doc-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin: 0;
}

.content-body {
  flex: 1;
  min-width: 0;   /* ← 防吹爆 */
  min-height: 0;
  overflow-y: auto;   /* 唯一的垂直滚动发生在这里 */
  overflow-x: hidden; /* 禁止水平滚动，长内容在此裁剪 */
  padding: 24px 24px; /* 水平 24px 呼吸感；滚动条仍贴卡片右缘 */
  width: 100%;
  box-sizing: border-box; /* padding 不外扩，杜绝 100% + padding 溢出 */
}

/* ===== 局部滚动条美化（8px 纤细质感） ===== */
.content-body::-webkit-scrollbar {
  width: 8px;
}
.content-body::-webkit-scrollbar-track {
  background: transparent;
}
.content-body::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.6);
}
.content-body::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

:root[data-theme="dark"] .content-body::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.05);
}
:root[data-theme="dark"] .content-body::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}

@media (max-width: 768px) {
  .docs-layout {
    flex-direction: column;
  }
  .docs-sider {
    width: 100%;
  }
}
</style>
