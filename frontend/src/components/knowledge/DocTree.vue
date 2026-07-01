<script setup lang="ts">
import { h } from 'vue'
import { NTree, NIcon } from 'naive-ui'
import type { TreeOption } from 'naive-ui'
import { FolderOutline, DocumentTextOutline } from '@vicons/ionicons5'
import type { DocTreeNode } from '@/types/knowledge'

const props = defineProps<{
  treeData: DocTreeNode[]
  activeId?: string
}>()

const emit = defineEmits<{
  select: [docId: string]
}>()

function toTreeOption(node: DocTreeNode): TreeOption {
  return {
    key: node.key,
    label: node.label,
    isLeaf: !node.isCategory,
    children: node.children?.map(toTreeOption),
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
  return h(
    'span',
    { class: ['tree-label', selected ? 'tree-label--active' : ''] },
    [
      h(NIcon, { size: 15, class: 'tree-icon' }, {
        default: () => h(node.isCategory ? FolderOutline : DocumentTextOutline),
      }),
      node.label,
    ],
  )
}

function handleSelect(keys: string[]) {
  // 找到叶子节点（有 docId）才触发选中
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
      :selected-keys="activeId ? [activeId] : []"
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

.doc-tree :deep(.n-tree-node-content) {
  padding: 2px 0;
}

.tree-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--neutral-text-2);
  transition: color 0.2s ease;
}

.tree-label--active {
  color: var(--arco-primary);
  font-weight: 500;
}

.tree-icon {
  color: var(--neutral-text-3);
}

.tree-label--active .tree-icon {
  color: var(--arco-primary);
}
</style>
