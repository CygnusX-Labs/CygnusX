<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { NIcon, NSpin, NButton } from 'naive-ui'
import {
  AddOutline,
  PersonOutline,
  DocumentTextOutline,
  FolderOpenOutline,
  ExtensionPuzzleOutline,
} from '@vicons/ionicons5'
import type { MentionItem } from './types'

interface Props {
  items: MentionItem[]
  activeIndex: number
  position: { top: number; left: number }
  loading?: boolean
  error?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  error: false,
})

const emit = defineEmits<{
  select: [item: MentionItem]
  hover: [index: number]
  retry: []
  close: []
}>()

const listRef = ref<HTMLDivElement>()

// 激活项变化时滚动到可视区域
watch(
  () => props.activeIndex,
  () => {
    nextTick(() => {
      const el = listRef.value?.querySelector('.mention-item.active')
      el?.scrollIntoView({ block: 'nearest' })
    })
  },
)

function groupLabel(kind: MentionItem['kind']): string {
  return kind === 'file' ? '文件' : '智能体 / 技能'
}

function groupIcon(kind: MentionItem['kind']) {
  return kind === 'file' ? AddOutline : PersonOutline
}
</script>

<template>
  <div
    class="mention-menu"
    :style="{ top: position.top + 'px', left: position.left + 'px' }"
    @mousedown.prevent
  >
    <div class="menu-header">
      <span class="header-title">@ 引用</span>
      <span class="header-sub">选择文件或指定智能体 / 技能</span>
    </div>

    <div ref="listRef" class="mention-list" role="listbox" aria-label="@ 引用列表">
      <!-- 加载中 -->
      <div v-if="loading" class="menu-state">
        <n-spin size="small" />
        <span>正在加载工作区文件…</span>
      </div>

      <!-- 加载失败 -->
      <div v-else-if="error" class="menu-state error">
        <span>加载失败</span>
        <n-button size="tiny" quaternary type="primary" @click="emit('retry')">重试</n-button>
      </div>

      <!-- 空结果 -->
      <div v-else-if="items.length === 0" class="menu-state">
        <n-icon size="20" class="empty-icon"><FolderOpenOutline /></n-icon>
        <span>暂无可引用文件</span>
      </div>

      <!-- 分组列表 -->
      <template v-else>
        <template v-for="(item, index) in items" :key="item.key">
          <div
            v-if="index === 0 || items[index - 1].kind !== item.kind"
            class="mention-group"
          >
            <n-icon size="13"><component :is="groupIcon(item.kind)" /></n-icon>
            <span>{{ groupLabel(item.kind) }}</span>
          </div>
          <div
            class="mention-item"
            :class="{ active: index === activeIndex }"
            role="option"
            :aria-selected="index === activeIndex"
            @click="emit('select', item)"
            @mouseenter="emit('hover', index)"
          >
            <div class="item-icon" :class="`kind-${item.kind}`">
              <n-icon size="16">
                <component :is="item.kind === 'file' ? DocumentTextOutline : item.kind === 'agent' ? PersonOutline : ExtensionPuzzleOutline" />
              </n-icon>
            </div>
            <div class="item-info">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-desc">{{ item.description }}</div>
            </div>
            <span class="item-tag">{{ item.kind === 'file' ? '文件' : item.kind === 'agent' ? 'agent' : 'skill' }}</span>
          </div>
        </template>
      </template>
    </div>

    <div class="menu-footer">
      <span><kbd>↑</kbd><kbd>↓</kbd> 导航</span>
      <span><kbd>Enter</kbd> 选择</span>
      <span><kbd>Esc</kbd> 关闭</span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.mention-menu {
  position: fixed;
  z-index: 1000;
  width: 380px;
  max-width: calc(100vw - 32px);
  background: var(--chat-surface, var(--neutral-card));
  border: 1px solid var(--chat-border, var(--neutral-border));
  border-radius: 12px;
  box-shadow: var(--shadow-dropdown, 0 8px 32px rgba(0, 0, 0, 0.4));
  overflow: hidden;
  animation: mention-popup 0.18s ease-out;

  .menu-header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--chat-border, var(--neutral-border));

    .header-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--chat-text-primary, var(--neutral-text-1));
    }
    .header-sub {
      font-size: 12px;
      color: var(--chat-text-muted, var(--neutral-text-3));
    }
  }

  .mention-list {
    max-height: 320px;
    overflow-y: auto;
    padding: 4px;
  }

  .menu-state {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 28px 16px;
    font-size: 13px;
    color: var(--chat-text-muted, var(--neutral-text-3));

    .empty-icon {
      opacity: 0.6;
    }
    &.error {
      color: var(--arco-danger, #f53f3f);
    }
  }

  .mention-group {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px 4px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: var(--chat-text-muted, var(--neutral-text-3));
    text-transform: uppercase;
  }

  .mention-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background var(--motion-quick, 140ms) ease-out;
    color: var(--chat-text-primary, var(--neutral-text-1));

    &:hover,
    &.active {
      background: var(--chat-surface-hover, var(--neutral-hover));
    }

    .item-icon {
      width: 30px;
      height: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
      flex-shrink: 0;

      &.kind-file {
        background: var(--arco-primary-light, rgba(76, 111, 255, 0.12));
        color: var(--arco-primary, #4c6fff);
      }
      &.kind-agent {
        background: var(--icon-purple-bg, rgba(139, 92, 246, 0.12));
        color: var(--icon-visualization, #8b5cf6);
      }
      &.kind-skill {
        background: var(--icon-green-bg, rgba(5, 150, 105, 0.12));
        color: #059669;
      }
    }

    .item-info {
      flex: 1;
      min-width: 0;

      .item-name {
        font-size: 14px;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .item-desc {
        font-size: 12px;
        color: var(--chat-text-muted, var(--neutral-text-3));
        margin-top: 1px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }

    .item-tag {
      font-size: 11px;
      color: var(--chat-text-muted, var(--neutral-text-3));
      padding: 1px 6px;
      border: 1px solid var(--chat-border, var(--neutral-border));
      border-radius: 9999px;
      flex-shrink: 0;
    }
  }

  .menu-footer {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 14px;
    border-top: 1px solid var(--chat-border, var(--neutral-border));
    font-size: 11px;
    color: var(--chat-text-muted, var(--neutral-text-3));

    kbd {
      display: inline-block;
      padding: 1px 5px;
      margin: 0 1px;
      background: var(--chat-surface-hover, var(--neutral-hover));
      border: 1px solid var(--chat-border, var(--neutral-border));
      border-radius: 4px;
      font-size: 10px;
      font-family: monospace;
    }
  }
}

@keyframes mention-popup {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .mention-menu {
    animation: none;
  }
}
</style>
