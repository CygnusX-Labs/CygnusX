<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { NIcon } from 'naive-ui'
import {
  SearchOutline,
  AnalyticsOutline,
  FolderOutline,
  CodeSlashOutline,
  ExtensionPuzzleOutline,
  RocketOutline,
  BarChartOutline,
  GridOutline,
  DocumentTextOutline,
  HelpCircleOutline,
} from '@vicons/ionicons5'

interface Props {
  query?: string
  position: { top: number; left: number }
}

const props = withDefaults(defineProps<Props>(), {
  query: '',
})

const emit = defineEmits<{
  select: [command: string]
  close: []
}>()

const menuRef = ref<HTMLDivElement>()
const searchRef = ref<HTMLInputElement>()
const listRef = ref<HTMLDivElement>()
const searchQuery = ref(props.query)
const selectedIndex = ref(0)

interface Command {
  id: string
  name: string
  description: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: any
  shortcut?: string
  isCategory?: boolean
}

const commands: Command[] = [
  { id: 'category-analysis', name: '分析', isCategory: true, icon: null, description: '' },
  { id: '/analysis', name: '分析流程', description: '启动生物信息分析流程', icon: AnalyticsOutline, shortcut: '/analysis' },
  { id: '/rna', name: 'RNA-seq 分析', description: '差异表达基因分析', icon: BarChartOutline, shortcut: '/rna' },
  { id: '/go', name: 'GO 富集分析', description: '基因功能富集分析', icon: BarChartOutline, shortcut: '/go' },
  { id: '/kegg', name: 'KEGG 通路分析', description: '代谢通路富集分析', icon: BarChartOutline, shortcut: '/kegg' },

  { id: 'category-data', name: '数据', isCategory: true, icon: null, description: '' },
  { id: '/data', name: '查询项目数据', description: '查看您的实验数据', icon: FolderOutline, shortcut: '/data' },
  { id: '/task', name: '查看分析任务', description: '查看正在运行的任务', icon: DocumentTextOutline, shortcut: '/task' },

  { id: 'category-tools', name: '工具', isCategory: true, icon: null, description: '' },
  { id: '/code', name: '代码执行', description: '在沙盒中执行 Python/R 代码', icon: CodeSlashOutline, shortcut: '/code' },
  { id: '/search', name: '文献搜索', description: '搜索 PubMed 等数据库', icon: SearchOutline, shortcut: '/search' },
  { id: '/plugin', name: '插件市场', description: '浏览可用插件', icon: ExtensionPuzzleOutline, shortcut: '/plugin' },
  { id: '/agent', name: 'Agent 模式', description: '切换到 Agent 自主模式', icon: RocketOutline, shortcut: '/agent' },

  { id: 'category-help', name: '帮助', isCategory: true, icon: null, description: '' },
  { id: '/help', name: '使用帮助', description: '查看 AI 助手使用指南', icon: HelpCircleOutline, shortcut: '/help' },
  { id: '/grid', name: '数据表格', description: '查看数据表格视图', icon: GridOutline, shortcut: '/grid' },
]

const filteredCommands = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  if (!q) return commands

  const filtered = commands.filter((cmd) => {
    if (cmd.isCategory) return false
    return (
      cmd.name.toLowerCase().includes(q) ||
      cmd.description.toLowerCase().includes(q) ||
      cmd.id.toLowerCase().includes(q)
    )
  })

  const result: Command[] = []
  for (let i = 0; i < commands.length; i++) {
    const cmd = commands[i]
    if (cmd.isCategory) {
      const hasChildren = commands.slice(i + 1).some((c) => !c.isCategory && filtered.includes(c))
      if (hasChildren) result.push(cmd)
    } else if (filtered.includes(cmd)) {
      result.push(cmd)
    }
  }
  return result
})

function handleMenuKeydown(e: KeyboardEvent) {
  const items = filteredCommands.value.filter((c) => !c.isCategory)
  const itemCount = items.length

  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      selectedIndex.value = (selectedIndex.value + 1) % Math.max(itemCount, 1)
      scrollToSelected()
      break
    case 'ArrowUp':
      e.preventDefault()
      selectedIndex.value = (selectedIndex.value - 1 + itemCount) % Math.max(itemCount, 1)
      scrollToSelected()
      break
    case 'Enter': {
      e.preventDefault()
      const selected = items[selectedIndex.value]
      if (selected) handleSelect(selected)
      break
    }
    case 'Escape':
      e.preventDefault()
      emit('close')
      break
  }
}

function handleSelect(command: Command) {
  if (command.isCategory) return
  emit('select', command.id)
}

function scrollToSelected() {
  nextTick(() => {
    const activeEl = listRef.value?.querySelector('.command-item.active')
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  })
}

onMounted(() => {
  nextTick(() => {
    searchRef.value?.focus()
    selectedIndex.value = 0
  })
})
</script>

<template>
  <div
    ref="menuRef"
    class="slash-command-menu"
    :style="{ top: position.top + 'px', left: position.left + 'px' }"
  >
    <div class="menu-search">
      <n-icon size="16" class="search-icon"><SearchOutline /></n-icon>
      <input
        ref="searchRef"
        v-model="searchQuery"
        class="search-input"
        placeholder="搜索命令..."
        @keydown="handleMenuKeydown"
      />
    </div>

    <div ref="listRef" class="command-list">
      <div
        v-for="(command, index) in filteredCommands"
        :key="command.id"
        class="command-item"
        :class="{ active: selectedIndex === index, category: command.isCategory }"
        @click="handleSelect(command)"
        @mouseenter="selectedIndex = index"
      >
        <template v-if="command.isCategory">
          <span class="category-label">{{ command.name }}</span>
        </template>
        <template v-else>
          <div class="command-icon">
            <n-icon size="18"><component :is="command.icon" /></n-icon>
          </div>
          <div class="command-info">
            <div class="command-name">{{ command.name }}</div>
            <div class="command-desc">{{ command.description }}</div>
          </div>
          <div class="command-shortcut">{{ command.shortcut || command.id }}</div>
        </template>
      </div>

      <div v-if="filteredCommands.length === 0" class="menu-empty">
        未找到匹配的命令
      </div>
    </div>

    <div class="menu-footer">
      <div class="footer-hint">
        <kbd>↑</kbd><kbd>↓</kbd> 导航
      </div>
      <div class="footer-hint">
        <kbd>Enter</kbd> 选择
      </div>
      <div class="footer-hint">
        <kbd>Esc</kbd> 关闭
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.slash-command-menu {
  position: fixed;
  z-index: 1000;
  width: 360px;
  background: var(--chat-surface);
  border: 1px solid var(--chat-border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  animation: menuPopup 0.2s ease-out;

  .menu-search {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--chat-border);

    .search-icon {
      color: var(--chat-text-muted);
      flex-shrink: 0;
    }

    .search-input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--chat-text-primary);
      font-size: 14px;

      &::placeholder {
        color: var(--chat-text-muted);
      }
    }
  }

  .command-list {
    max-height: 320px;
    overflow-y: auto;
    padding: 4px;

    .command-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
      color: var(--chat-text-primary);

      &:hover,
      &.active {
        background: var(--chat-surface-hover);
      }

      &.category {
        padding: 6px 12px;
        cursor: default;
        pointer-events: none;

        &:hover {
          background: transparent;
        }

        .category-label {
          font-size: 11px;
          color: var(--chat-text-muted);
          text-transform: uppercase;
          letter-spacing: 1px;
          font-weight: 500;
        }
      }

      .command-icon {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(79, 142, 247, 0.1);
        border-radius: 8px;
        color: var(--chat-accent);
        flex-shrink: 0;
      }

      .command-info {
        flex: 1;
        min-width: 0;

        .command-name {
          font-size: 14px;
          font-weight: 500;
        }

        .command-desc {
          font-size: 12px;
          color: var(--chat-text-muted);
          margin-top: 1px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
      }

      .command-shortcut {
        font-size: 12px;
        color: var(--chat-text-muted);
        font-family: 'Courier New', monospace;
        flex-shrink: 0;
      }
    }

    .menu-empty {
      padding: 24px;
      text-align: center;
      font-size: 13px;
      color: var(--chat-text-muted);
    }
  }

  .menu-footer {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 14px;
    border-top: 1px solid var(--chat-border);
    background: rgba(0, 0, 0, 0.2);

    .footer-hint {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      color: var(--chat-text-muted);

      kbd {
        display: inline-block;
        padding: 2px 6px;
        background: var(--chat-surface-hover);
        border: 1px solid var(--chat-border);
        border-radius: 4px;
        font-size: 10px;
        font-family: monospace;
      }
    }
  }
}

@keyframes menuPopup {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
</style>
