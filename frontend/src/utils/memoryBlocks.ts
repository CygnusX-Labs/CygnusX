import type { MemoryBlock } from '@/types/memory'

export function groupMemoryBlocks(blocks: MemoryBlock[]) {
  const groups = new Map<string, { key: string; label: string; blocks: MemoryBlock[] }>()
  for (const block of blocks) {
    const key = block.block_name !== 'current_focus' ? 'personal' : block.project_id || 'general'
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: key === 'personal' ? '共享个人记忆' : key === 'general' ? '通用焦点（无项目）' : `项目 ${key}`,
        blocks: [],
      })
    }
    groups.get(key)!.blocks.push(block)
  }
  return [...groups.values()]
}
