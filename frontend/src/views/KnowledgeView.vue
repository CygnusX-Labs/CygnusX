<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard,
  NSpin,
  NEmpty,
  NButton,
  NSpace,
  NIcon,
  NPopconfirm,
  useMessage,
} from 'naive-ui'
import {
  CreateOutline,
  SaveOutline,
  CloseOutline,
  CloudDownloadOutline,
  AddOutline,
  HourglassOutline,
  TrashOutline,
} from '@vicons/ionicons5'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import DocTree from '@/components/knowledge/DocTree.vue'
import DocReader from '@/components/knowledge/DocReader.vue'
import DocEditor from '@/components/knowledge/DocEditor.vue'
import DocCreateModal from '@/components/knowledge/DocCreateModal.vue'
import AuditPendingPanel from '@/components/knowledge/AuditPendingPanel.vue'
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

const editBuffer = ref('')
const draftContent = ref('')
const draftSummary = ref('')

const showCreateModal = ref(false)
const showAuditPanel = ref(false)

const isAdmin = computed(() => authStore.isAdmin)

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
      status: it.status,
    })),
  }))
})

const existingCategories = computed(() =>
  [...new Set(navItems.value.map((item) => item.category).filter(Boolean))] as string[],
)

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
  draftSummary.value = ''
  isEditMode.value = true
}

function cancelEdit() {
  draftContent.value = editBuffer.value
  draftSummary.value = ''
  isEditMode.value = false
}

async function saveDoc() {
  if (!activeDoc.value) return
  saving.value = true
  try {
    const res = await apiClient.put(`/docs/knowledge/${activeDoc.value.id}`, {
      content: draftContent.value,
      editSummary: draftSummary.value || undefined,
    })
    isEditMode.value = false
    message.success(res.data.message || '保存成功')
    await fetchDoc(activeDoc.value.id)
    await fetchNav()
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    message.error(detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteDoc() {
  if (!activeDoc.value) return
  try {
    await apiClient.delete(`/docs/knowledge/${activeDoc.value.id}`)
    message.success('文档已删除')
    activeDoc.value = null
    await fetchNav()
    // 删除后跳转到第一个文档，如果没有则清空路由参数
    if (documentTree.value.length > 0) {
      const firstLeaf = documentTree.value[0].children?.[0]
      if (firstLeaf?.docId) {
        await router.replace({ name: 'knowledge-doc', params: { docId: firstLeaf.docId } })
      } else {
        await router.replace({ name: 'knowledge' })
      }
    } else {
      await router.replace({ name: 'knowledge' })
    }
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    message.error(detail || '删除失败')
  }
}

function handleCreated(docId: string) {
  void fetchNav()
  router.push({ name: 'knowledge-doc', params: { docId } })
}

function handleAudited() {
  void fetchNav()
  if (activeDoc.value) {
    void fetchDoc(activeDoc.value.id)
  }
}

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

        <!-- 核心操作：新建文档 -->
        <NButton
          size="medium"
          type="primary"
          block
          class="create-doc-btn"
          @click="showCreateModal = true"
        >
          <template #icon><NIcon><AddOutline /></NIcon></template>
          新建文档
        </NButton>

        <!-- 管理员额外菜单 -->
        <div v-if="isAdmin" class="sider-menu">
          <div class="sider-menu-item" @click="showAuditPanel = true">
            <NIcon size="16"><HourglassOutline /></NIcon>
            <span>待审核</span>
          </div>
        </div>

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
                size="small"
                type="primary"
                ghost
                @click="startEdit"
              >
                <template #icon><NIcon><CreateOutline /></NIcon></template>
                编辑
              </NButton>
              <NPopconfirm v-if="isAdmin" @positive-click="deleteDoc">
                <template #trigger>
                  <NButton size="small" type="error" ghost>
                    <template #icon><NIcon><TrashOutline /></NIcon></template>
                    删除
                  </NButton>
                </template>
                确定删除该文档？此操作不可恢复。
              </NPopconfirm>
            </template>
            <template v-else>
              <NButton size="small" @click="cancelEdit">
                <template #icon><NIcon><CloseOutline /></NIcon></template>
                取消
              </NButton>
              <NButton size="small" type="primary" :loading="saving" @click="saveDoc">
                <template #icon><NIcon><SaveOutline /></NIcon></template>
                {{ isAdmin ? '保存并发布' : '提交审核' }}
              </NButton>
            </template>
          </NSpace>
        </div>

        <!-- 内容区 -->
        <NSpin :show="loadingDoc">
          <div v-if="activeDoc" class="content-body">
            <DocEditor
              v-if="isEditMode"
              v-model="draftContent"
              v-model:edit-summary="draftSummary"
              :is-admin="isAdmin"
            />
            <DocReader v-else :doc="activeDoc" @refresh="fetchDoc(activeDoc.id)" />
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

  <DocCreateModal
    v-model:show="showCreateModal"
    :existing-categories="existingCategories"
    @created="handleCreated"
  />

  <AuditPendingPanel
    v-model:show="showAuditPanel"
    @audited="handleAudited"
  />
</template>

<style scoped>
.docs-layout {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0 !important;
  overflow: hidden;
  padding: 0;
}

.docs-sider {
  width: 240px;
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

.docs-sider :deep(.n-card > .n-card-content) {
  padding: 16px 12px;
}

.nav-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin-bottom: 16px;
  padding: 0;
  text-align: center;
}

/* 新建文档：全宽 CTA 按钮 */
.create-doc-btn {
  margin-bottom: 8px;
  border-radius: 6px !important;
  font-weight: 500;
}

.create-doc-btn :deep(.n-button__content) {
  gap: 6px;
}

/* 侧边栏菜单项（待审核、收藏夹等） */
.sider-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.sider-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 14px;
  color: var(--neutral-text-2);
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
  user-select: none;
}

.sider-menu-item:hover {
  background-color: var(--neutral-hover);
  color: var(--neutral-text-1);
}

.docs-sider :deep(.n-tree-node) {
  padding: 0 4px;
}

.docs-sider :deep(.n-tree-node-content) {
  padding: 6px 8px;
  border-radius: 6px;
  transition: background-color 0.2s ease;
}

.docs-sider :deep(.n-tree-node-content:hover) {
  background-color: var(--neutral-hover);
}

.docs-sider :deep(.n-tree-node--selected .n-tree-node-content) {
  background-color: var(--arco-primary-light);
  color: var(--arco-primary);
}

.docs-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.docs-main > :deep(.n-card) {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.docs-main > :deep(.n-card > .n-card-content) {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 !important;
  overflow: hidden !important;
}

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
  padding: 16px 24px 12px;
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
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px 24px;
  width: 100%;
  box-sizing: border-box;
}

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
