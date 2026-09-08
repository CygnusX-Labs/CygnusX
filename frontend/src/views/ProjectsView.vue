<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NCard, NDataTable, NEmpty, NIcon, NSkeleton, NSpin, useMessage,
} from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import type { DataTableColumns } from 'naive-ui'
import PageHeader from '@/components/PageHeader.vue'
import CreateProjectModal from '@/components/project/CreateProjectModal.vue'
import { projectsApi, type ProjectItem } from '@/api/projects'

const router = useRouter()
const message = useMessage()

/** 首次进入用 NSkeleton；已加载后的局部刷新（新建成功回拉）用 NSpin（§5.4） */
const initialLoading = ref(true)
const refreshing = ref(false)
const projects = ref<ProjectItem[]>([])
const showCreate = ref(false)

function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : '—'
}

function mutedText(value: string | null | undefined) {
  return value
    ? value
    : h('span', { class: 'cell-muted' }, '—')
}

function openProject(row: ProjectItem) {
  router.push({ name: 'project-detail', params: { projectId: row.id } })
}

// 列全部固定宽（§33.2③），scroll-x = 列宽之和；长文本列省略 + tooltip（§5.4）
const columns: DataTableColumns<ProjectItem> = [
  {
    title: '项目名称',
    key: 'name',
    width: 240,
    ellipsis: { tooltip: true },
    render(row) {
      return h(
        NButton,
        { text: true, type: 'primary', onClick: () => openProject(row) },
        { default: () => row.name },
      )
    },
  },
  {
    title: '客户',
    key: 'customer',
    width: 160,
    align: 'center',
    ellipsis: { tooltip: true },
    render: (row) => mutedText(row.customer),
  },
  {
    title: '描述',
    key: 'description',
    width: 320,
    ellipsis: { tooltip: true },
    render: (row) => mutedText(row.description),
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    align: 'center',
    render: (row) => formatDate(row.created_at),
  },
  {
    title: '操作',
    key: 'actions',
    width: 110,
    align: 'center',
    render(row) {
      return h(
        NButton,
        { size: 'small', secondary: true, onClick: () => openProject(row) },
        { default: () => '查看详情' },
      )
    },
  },
]
const tableScrollX = columns.reduce((sum, col) => sum + (Number(col.width) || 0), 0)

async function loadProjects() {
  if (initialLoading.value) {
    // 首载
  } else {
    refreshing.value = true
  }
  try {
    projects.value = await projectsApi.listProjects()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载项目列表失败')
  } finally {
    initialLoading.value = false
    refreshing.value = false
  }
}

onMounted(loadProjects)
</script>

<template>
  <div class="projects-view">
    <PageHeader title="项目管理" subtitle="按项目浏览历史会话与分析运行记录">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">
          <template #icon><NIcon><AddOutline /></NIcon></template>
          新建项目
        </NButton>
      </template>
    </PageHeader>
    <CreateProjectModal v-model:show="showCreate" @created="loadProjects" />

    <NCard :bordered="false" class="projects-card">
      <NSkeleton
        v-if="initialLoading"
        :repeat="6"
        height="44px"
        :sharp="false"
        style="margin-top: 4px"
      />
      <NSpin v-else :show="refreshing">
        <NEmpty
          v-if="!projects.length"
          description="还没有项目，新建一个项目来归集会话与分析运行"
          class="projects-empty"
        >
          <template #extra>
            <NButton type="primary" @click="showCreate = true">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建项目
            </NButton>
          </template>
        </NEmpty>
        <NDataTable
          v-else
          :columns="columns"
          :data="projects"
          :row-key="(row: ProjectItem) => row.id"
          :pagination="{ pageSize: 20 }"
          :bordered="false"
          :scroll-x="tableScrollX"
        />
      </NSpin>
    </NCard>
  </div>
</template>

<style scoped>
/* 页面容器：与配置中心同一条内容边界（width: min(100%, 1440px) 居中），padding 消费 --page-padding（§3.4/§4.3） */
.projects-view {
  width: min(100%, 1440px);
  margin-inline: auto;
  padding: var(--page-padding);
}

/* 卡片内边距 24px 由 NCard 默认提供；空状态给足上下留白 */
.projects-empty {
  padding: var(--space-4xl) 0;
}

/* 空值占位 '—' 用辅助色弱化（§3.2 辅助文本） */
.cell-muted {
  color: var(--neutral-text-3);
}

@media (max-width: 768px) {
  .projects-view {
    padding: var(--space-lg);
  }
}
</style>
