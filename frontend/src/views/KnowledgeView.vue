<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NSpin, NEmpty, NMenu, NIcon } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { BookOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import MarkdownReader from '@/components/MarkdownReader.vue'

interface DocNavItem {
  id: string
  title: string
}

interface DocContent {
  id: string
  title: string
  content: string
}

const route = useRoute()
const router = useRouter()

const loadingNav = ref(false)
const loadingDoc = ref(false)
const navTitle = ref('实验室知识库')
const navItems = ref<DocNavItem[]>([])
const currentDoc = ref<DocContent | null>(null)

async function fetchNav() {
  loadingNav.value = true
  try {
    const res = await apiClient.get<{ title: string; items: DocNavItem[] }>('/docs/knowledge')
    navTitle.value = res.data.title
    navItems.value = res.data.items
  } finally {
    loadingNav.value = false
  }
}

async function fetchDoc(docId: string) {
  loadingDoc.value = true
  try {
    const res = await apiClient.get<DocContent>(`/docs/knowledge/${docId}`)
    currentDoc.value = res.data
  } finally {
    loadingDoc.value = false
  }
}

const menuOptions = ref<MenuOption[]>([])

watch(navItems, (items) => {
  menuOptions.value = items.map((item) => ({
    key: item.id,
    label: item.title,
    icon: () => h(NIcon, null, { default: () => h(BookOutline) }),
  }))
}, { immediate: true })

watch(
  () => route.params.docId as string | undefined,
  (docId) => {
    if (docId && navItems.value.some((i) => i.id === docId)) {
      fetchDoc(docId)
    } else if (navItems.value.length > 0 && !currentDoc.value) {
      const first = navItems.value[0]
      router.replace({ name: 'knowledge', params: { docId: first.id } })
    }
  },
)

function handleMenuUpdate(key: string) {
  router.push({ name: 'knowledge', params: { docId: key } })
}

onMounted(async () => {
  await fetchNav()
  const docId = route.params.docId as string | undefined
  if (docId && navItems.value.some((i) => i.id === docId)) {
    await fetchDoc(docId)
  } else if (navItems.value.length > 0) {
    const first = navItems.value[0]
    router.replace({ name: 'knowledge', params: { docId: first.id } })
  }
})

import { h } from 'vue'
</script>

<template>
  <div class="docs-layout page-container">
    <div class="docs-sider">
      <NCard :bordered="false" class="arco-card nav-card">
        <div class="nav-title">{{ navTitle }}</div>
        <NSpin :show="loadingNav">
          <NMenu
            :value="(route.params.docId as string)"
            :options="menuOptions"
            :collapsed-width="64"
            @update:value="handleMenuUpdate"
          />
        </NSpin>
      </NCard>
    </div>
    <div class="docs-main">
      <NCard :bordered="false" class="arco-card content-card">
        <NSpin :show="loadingDoc">
          <MarkdownReader
            v-if="currentDoc"
            :title="currentDoc.title"
            :content="currentDoc.content"
          />
          <NEmpty v-else description="请选择文档" />
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.docs-layout {
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 104px);
}

.docs-sider {
  width: 260px;
  flex-shrink: 0;
}

.nav-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--neutral-text-1);
  margin-bottom: 12px;
  padding: 0 4px;
}

.nav-card :deep(.n-menu-item) {
  border-radius: 8px;
}

.docs-main {
  flex: 1;
  min-width: 0;
}

.content-card {
  min-height: 100%;
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
