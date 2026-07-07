<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon, NTooltip } from 'naive-ui'
import {
  AddOutline, CloseOutline, ChatbubbleOutline, MenuOutline,
} from '@vicons/ionicons5'
import { useAgentHubStore } from '@/stores/agentHub'

const store = useAgentHubStore()

defineProps<{ collapsed?: boolean }>()
defineEmits<{
  toggleCollapse: []
  newChat: []
  selectSession: [id: string]
  deleteSession: [id: string]
}>()

const grouped = computed(() => store.groupedSessions)
</script>

<template>
  <aside class="agent-sidebar" :class="{ collapsed }">
    <div class="sidebar-top">
      <span v-if="!collapsed" class="brand">AI 助手 · 多智能体</span>
      <div class="nav-top-controls" :class="{ collapsed }">
        <NTooltip trigger="hover" placement="right">
          <template #trigger>
            <NButton text class="nav-icon-btn menu-btn" @click="$emit('toggleCollapse')">
              <NIcon size="18"><MenuOutline /></NIcon>
            </NButton>
          </template>
          {{ collapsed ? '展开菜单' : '折叠菜单' }}
        </NTooltip>
        <NTooltip trigger="hover" placement="right">
          <template #trigger>
            <NButton text class="nav-icon-btn add-btn" @click="$emit('newChat')">
              <NIcon size="18"><AddOutline /></NIcon>
            </NButton>
          </template>
          新建智能体对话
        </NTooltip>
      </div>
    </div>

    <div v-if="!collapsed" class="history">
      <div class="section-title">历史会话</div>
      <div v-if="!grouped.length" class="history-empty">暂无会话，从应用集市开始吧</div>
      <div v-for="g in grouped" :key="g.label" class="session-group">
        <div class="group-label">{{ g.label }}</div>
        <div
          v-for="s in g.sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === store.currentSessionId }"
          @click="$emit('selectSession', s.id)"
        >
          <NIcon size="14" class="s-icon"><ChatbubbleOutline /></NIcon>
          <span class="s-title">{{ s.title }}</span>
          <NButton text size="tiny" class="s-del" @click.stop="$emit('deleteSession', s.id)">
            <NIcon size="12"><CloseOutline /></NIcon>
          </NButton>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped lang="scss">
.agent-sidebar {
  width: var(--chat-sidebar-width, 260px);
  min-width: var(--chat-sidebar-width, 260px);
  height: 100%;
  background: var(--chat-sidebar-bg);
  border-right: 1px solid var(--chat-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width .25s ease, min-width .25s ease;
}
.agent-sidebar.collapsed { width: 60px; min-width: 60px; }

.sidebar-top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px;
}
.brand { font-size: 13px; font-weight: 600; }

.nav-top-controls {
  display: flex; align-items: center; gap: 10px;
}
.nav-top-controls.collapsed {
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.nav-icon-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  transition: all 0.2s ease;
  padding: 0;
}
.nav-icon-btn .n-icon {
  width: 18px;
  height: 18px;
  font-size: 18px;
}

.nav-icon-btn.menu-btn {
  color: var(--chat-text-muted, #86909c);
}
.nav-icon-btn.menu-btn:hover {
  background: var(--chat-surface-hover, rgba(0,0,0,.06));
  color: var(--chat-text-primary, #1d2129);
}

.nav-icon-btn.add-btn {
  background: var(--chat-accent, #165DFF);
  color: #fff;
}
.nav-icon-btn.add-btn:hover {
  background: var(--chat-accent-hover, #0e42d2);
  transform: scale(1.05);
}

.history { flex: 1; overflow-y: auto; padding: 0 8px; }
.section-title { font-size: 11px; color: var(--chat-text-muted, #999); padding: 8px 8px 4px; }
.history-empty { font-size: 12px; color: var(--chat-text-muted, #aaa); padding: 8px; }
.group-label { font-size: 11px; color: var(--chat-text-muted, #999); padding: 10px 8px 4px; }

.session-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
  transition: background .15s ease;
}
.session-item:hover { background: var(--chat-surface-hover, rgba(0,0,0,.04)); }
.session-item.active { background: rgba(79,142,247,.12); color: var(--chat-accent); }
.s-icon { flex-shrink: 0; opacity: .7; }
.s-title { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s-del { opacity: 0; transition: opacity .15s; }
.session-item:hover .s-del { opacity: 1; }
</style>
