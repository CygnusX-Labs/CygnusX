<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDropdown, NEmpty, NIcon, NSpin, NTree, useDialog, useMessage } from 'naive-ui'
import type { TreeOption } from 'naive-ui'
import { FolderOutline, AddOutline, TrashOutline, FolderOpenOutline, EllipsisHorizontalOutline, CreateOutline, LockClosedOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import type { Directory } from '@/types'

const props = defineProps<{
  modelValue: string
  fileCounts?: Record<string, number>
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'refresh-files'): void
}>()

const message = useMessage()
const dialog = useDialog()
const directories = ref<Directory[]>([])
const loading = ref(false)

/** 选中目录："" = 根 */
const selected = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v),
})

/** 把扁平目录列表组装成树 */
const treeData = computed<TreeOption[]>(() => {
  const root: TreeOption = {
    key: '',
    label: '根目录',
    children: [],
  }
  const nodeMap = new Map<string, TreeOption>()
  nodeMap.set('', root)
  for (const d of directories.value) {
    const node: TreeOption = { key: d.path, label: d.name, children: [] }
    nodeMap.set(d.path, node)
  }
  for (const d of directories.value) {
    const parent = nodeMap.get(d.parent_path ?? '') ?? root
    parent.children!.push(nodeMap.get(d.path)!)
  }
  return [root]
})

const selectedKeys = computed(() => [selected.value || ''])

/** 节点 label 渲染：名称 + 文件计数 (N)，计数含子目录汇总 */
function renderLabel({ option }: { option: TreeOption }) {
  const path = String(option.key ?? '')
  const name = option.label as string
  const counts = props.fileCounts || {}
  // 该目录直接文件数 + 所有以该目录为前缀的子目录文件数（汇总）
  let total = counts[path] || 0
  if (path) {
    const prefix = path + '/'
    for (const k of Object.keys(counts)) {
      if (k.startsWith(prefix)) total += counts[k] || 0
    }
  } else {
    // 根目录：所有目录的文件都属于根汇总
    for (const k of Object.keys(counts)) total += counts[k] || 0
  }
  return h('span', { class: 'tree-label' }, [
    h('span', null, name),
    total > 0 ? h('span', { class: 'dir-count' }, total) : null,
  ])
}

function handleSelect(keys: string[]) {
  const k = keys[0] ?? ''
  selected.value = k
  emit('refresh-files')
}

async function fetchDirectories() {
  loading.value = true
  try {
    const res = await apiClient.get<Directory[]>('/files/directories')
    directories.value = res.data
  } catch {
    message.error('获取目录列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateModal(parentPath: string) {
  dialog.create({
    title: '新建目录',
    content: () =>
      h('div', { style: 'padding: 8px 0' }, [
        h('p', { style: 'color:#86909c;font-size:13px;margin:0 0 8px' }, `父目录：${parentPath || '根目录'}`),
        h('input', {
          id: '__dir_name_input',
          placeholder: '输入目录名（支持多级如 projA/sub）',
          style: 'width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:6px;outline:none',
          autofocus: true,
        }),
      ]),
    positiveText: '创建',
    negativeText: '取消',
    onPositiveClick: async () => {
      const input = document.getElementById('__dir_name_input') as HTMLInputElement
      const name = input?.value?.trim() || ''
      if (!name) {
        message.warning('目录名不能为空')
        return false
      }
      const fullPath = parentPath ? `${parentPath}/${name}` : name
      try {
        await apiClient.post('/files/directories', { path: fullPath })
        message.success('目录已创建')
        await fetchDirectories()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '创建失败')
        return false
      }
    },
  })
}

function confirmDelete(dir: Directory) {
  dialog.warning({
    title: '删除目录',
    content: `确认删除目录「${dir.path}」？该目录下的文件会移回根目录。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.delete('/files/directories', { params: { path: dir.path } })
        message.success('目录已删除')
        if (selected.value === dir.path) selected.value = ''
        await fetchDirectories()
        emit('refresh-files')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}

const contextMenuOptions = (dir: Directory) => [
  { label: '新建子目录', key: 'create' },
  { label: '删除目录', key: 'delete' },
]

/** 重命名目录 — TODO: 后端重命名端点就绪后接入 PUT /files/directories/rename */
function renameDirectory(dir: Directory) {
  message.info('重命名功能即将上线')
}

/** 悬浮内联操作的下拉选项 —— 系统目录仅保留新建子目录 */
function inlineMenuOptions(dir: Directory) {
  if (dir.is_system) {
    return [{ label: '新建子目录', key: 'create', icon: () => h(NIcon, null, { default: () => h(AddOutline) }) }]
  }
  return [
    { label: '重命名', key: 'rename', icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) },
    { label: '删除目录', key: 'delete', icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) },
  ]
}

function handleInlineMenu(key: string, dir: Directory) {
  if (key === 'create') openCreateModal(dir.path)
  else if (key === 'rename') renameDirectory(dir)
  else if (key === 'delete') confirmDelete(dir)
}

/** 系统目录前缀锁图标 */
function renderPrefix({ option }: { option: TreeOption }) {
  const path = String(option.key ?? '')
  const dir = path ? directories.value.find((d) => d.path === path) : null
  if (dir?.is_system) {
    return h(NIcon, { size: 13, color: '#86909c', style: 'margin-right:4px' }, { default: () => h(LockClosedOutline) })
  }
  return null
}

/** 节点悬浮时右侧内联显示 + / ⋯ */
function renderSuffix({ option }: { option: TreeOption }) {
  const path = String(option.key ?? '')
  const dir = path ? directories.value.find((d) => d.path === path) : null
  const buttons: ReturnType<typeof h>[] = []

  buttons.push(
    h(
      NButton,
      {
        size: 'tiny',
        quaternary: true,
        title: '新建子目录',
        onClick: (e: MouseEvent) => {
          e.stopPropagation()
          openCreateModal(path)
        },
      },
      { icon: () => h(NIcon, null, { default: () => h(AddOutline) }) },
    ),
  )

  if (dir) {
    buttons.push(
      h(
        NDropdown,
        {
          trigger: 'click',
          options: inlineMenuOptions(dir),
          placement: 'bottom-end',
          onSelect: (key: string) => handleInlineMenu(key, dir),
        },
        {
          default: () =>
            h(
              NButton,
              {
                size: 'tiny',
                quaternary: true,
                title: '更多操作',
                onClick: (e: MouseEvent) => e.stopPropagation(),
              },
              { icon: () => h(NIcon, null, { default: () => h(EllipsisHorizontalOutline) }) },
            ),
        },
      ),
    )
  }

  return h('div', { class: 'inline-actions', onClick: (e: MouseEvent) => e.stopPropagation() }, buttons)
}

function handleContextMenu(option: TreeOption, e: MouseEvent) {
  e.preventDefault()
  const path = String(option.key ?? '')
  // 根目录只允许新建
  if (!path) {
    openCreateModal('')
    return
  }
  const dir = directories.value.find((d) => d.path === path)
  if (!dir) return
  // 系统目录锁定：仅允许新建子目录，禁止删除/重命名
  if (dir.is_system) {
    openCreateModal(dir.path)
    return
  }
  // 用 dropdown 太复杂，直接弹菜单选择 — 这里简化为右键即弹新建/删除选项
  dialog.create({
    title: `目录：${dir.name}`,
    content: '选择操作',
    action: () =>
      h('div', { style: 'display:flex;gap:8px;justify-content:flex-end' }, [
        h(NButton, { onClick: () => { openCreateModal(dir.path) } }, { default: () => '新建子目录' }),
        h(NButton, { type: 'error', ghost: true, onClick: () => confirmDelete(dir) }, { default: () => '删除目录' }),
      ]),
  })
}

function nodeProps({ option }: { option: TreeOption }) {
  return {
    onContextmenu: (e: MouseEvent) => handleContextMenu(option, e),
  }
}

defineExpose({ refresh: fetchDirectories, openCreateModal })
onMounted(fetchDirectories)
</script>

<template>
  <div class="directory-tree">
    <div class="tree-header">
      <span class="tree-title">
        <NIcon :size="16"><FolderOpenOutline /></NIcon>
        目录
      </span>
      <NButton size="tiny" quaternary title="在根目录下新建" @click="openCreateModal('')">
        <template #icon><NIcon><AddOutline /></NIcon></template>
      </NButton>
    </div>
    <NSpin :show="loading">
      <NTree
        block-line
        expand-on-click
        :data="treeData"
        :selected-keys="selectedKeys"
        :default-expanded-keys="['']"
        :render-prefix="renderPrefix"
        :render-label="renderLabel"
        :render-suffix="renderSuffix"
        @update:selected-keys="handleSelect"
        :node-props="nodeProps"
      />
    </NSpin>
  </div>
</template>

<style scoped>
.directory-tree {
  width: 240px;
  flex-shrink: 0;
  padding: 12px;
  box-sizing: border-box;
}
.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.tree-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-text-2, #4e5969);
}
.tree-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dir-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  font-size: 10px;
  font-weight: 600;
  color: var(--neutral-text-3, #86909c);
  background: var(--neutral-bg, #f2f3f8);
  border-radius: 8px;
  font-variant-numeric: tabular-nums;
}
/* 悬浮内联操作：默认隐藏，hover 节点时显现 */
.inline-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
  margin-left: 4px;
}
.directory-tree :deep(.n-tree-node:hover) .inline-actions,
.directory-tree :deep(.n-tree-node--selected) .inline-actions {
  opacity: 1;
}
</style>
