<script setup lang="ts">
import { h } from 'vue'
import { NTree, NIcon, NBadge } from 'naive-ui'
import type { TreeOption } from 'naive-ui'
import { FolderOutline, DocumentTextOutline } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import type { DocTreeNode, KnowledgeDocStatus } from '@/types/knowledge'

const props = defineProps<{
  treeData: DocTreeNode[]
  activeId?: string
}>()

const emit = defineEmits<{
  select: [docId: string]
}>()

const authStore = useAuthStore()

function toTreeOption(node: DocTreeNode): TreeOption {
  return {
    key: node.key,
    label: node.label,
    isLeaf: !node.isCategory,
    children: node.children?.map(toTreeOption),
    // 透传自定义字段给 renderLabel
    docId: node.docId,
    isCategory: node.isCategory,
    status: node.status,
  } as TreeOption
}

const treeOptions = () => props.treeData.map(toTreeOption)

function renderSwitcherIcon() {
  return h(NIcon, null, { default: () => h(FolderOutline) })
}

function renderLabel({
  option,
  selected,
}: {
  option: TreeOption
  checked: boolean
  selected: boolean
}) {
  const node = option as unknown as DocTreeNode
  const isDoc = !node.isCategory
  const status = node.status as KnowledgeDocStatus | undefined

  // 状态可见性：pending/rejected 仅自己/管理员可见（简化：仅管理员可见 rejected，
  // pending 对所有人都可见但用橙色点提示"有版本在审核"；实际项目中可再细化）
  const showStatus = isDoc && status && status !== 'published'

  return h(
    'span',
    { class: ['tree-label', selected ? 'tree-label--active' : ''] },
    [
      h(NIcon, { size: 15, class: 'tree-icon' }, {
        default: () => h(node.isCategory ? FolderOutline : DocumentTextOutline),
      }),
      h('span', { class: 'tree-label-text' }, node.label),
      showStatus
        ? h(NBadge, {
            dot: true,
            type: status === 'rejected' ? 'error' : 'warning',
            class: 'tree-status-dot',
          })
        : null,
    ],
  )
}

function handleSelect(keys: string[]) {
  const key = keys[0]
  const node = findNode(props.treeData, key)
  if (node?.docId) {
    emit('select', node.docId)
  }
}

function findNode(nodes: DocTreeNode[], key: string): DocTreeNode | undefined {
  for (const n of nodes) {
    if (n.key === key) return n
    if (n.children) {
      const found = findNode(n.children, key)
      if (found) return found
    }
  }
  return undefined
}
</script>

<template>
  <div class="doc-tree">
    <NTree
      block-line
      expand-on-click
      :data="treeOptions()"
      :selected-keys="activeId ? [`doc:${activeId}`] : []"
      :render-switcher-icon="renderSwitcherIcon"
      :render-label="renderLabel"
      @update:selected-keys="handleSelect"
    />
  </div>
</template>

<style scoped>
.doc-tree {
  user-select: none;
}

.doc-tree :deep(.n-tree-node) {
  margin-bottom: 2px;
}

.doc-tree :deep(.n-tree-node-content) {
  padding: 2px 0;
}

.doc-tree :deep(.n-tree-node-switcher) {
  padding: 0 2px;
}

.tree-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--neutral-text-2);
  transition: color 0.2s ease;
  width: 100%;
}

.tree-label--active {
  color: var(--arco-primary);
  font-weight: 500;
}

.tree-label-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-icon {
  color: var(--neutral-text-3);
  flex-shrink: 0;
}

.tree-label--active .tree-icon {
  color: var(--arco-primary);
}

.tree-status-dot {
  flex-shrink: 0;
  margin-left: auto;
}

/* 让 badge 点更紧凑 */
.doc-tree :deep(.n-badge-dot) {
  width: 6px;
  height: 6px;
}
</style>
