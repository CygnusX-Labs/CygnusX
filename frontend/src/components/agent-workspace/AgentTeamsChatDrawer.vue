<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NAlert,
  NButton,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NIcon,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { OpenOutline, RefreshOutline } from '@vicons/ionicons5'
import { agentTeamsApi, type AgentTeamsChatRoom } from '@/api/agentTeams'

const message = useMessage()
const visible = ref(false)
const loading = ref(false)
const loadFailed = ref(false)
const room = ref<AgentTeamsChatRoom | null>(null)
const currentCaseId = ref('')

const elementUrl = computed(() => room.value?.element_url || '')
const roomAvailable = computed(() => room.value?.available && !!elementUrl.value)
const isCaseRoom = computed(() => room.value?.source === 'case')

async function loadRoom() {
  loading.value = true
  loadFailed.value = false
  try {
    room.value = await agentTeamsApi.getChatRoom(currentCaseId.value || undefined)
  } catch (cause: any) {
    loadFailed.value = true
    room.value = null
    message.error(cause?.response?.data?.detail || '无法读取协作聊天室配置。')
  } finally {
    loading.value = false
  }
}

async function open(caseId?: string) {
  currentCaseId.value = caseId || ''
  visible.value = true
  await loadRoom()
}

function openInNewWindow() {
  if (!elementUrl.value) return
  window.open(elementUrl.value, '_blank', 'noopener,noreferrer')
}

defineExpose({ open })
</script>

<template>
  <NDrawer v-model:show="visible" :width="'min(100vw, 980px)'" placement="right">
    <NDrawerContent closable>
      <template #header>
        <div class="chat-room-heading">
          <div>
            <strong>{{ isCaseRoom ? 'Case 协作房间' : 'AgentTeams 协作聊天室' }}</strong>
            <span>{{ isCaseRoom
              ? `当前展示 Case ${room?.case_id || currentCaseId} 关联的协作房间。`
              : '在当前 AI 助手页面中参与 Element / Matrix 协作房间。' }}</span>
          </div>
          <NTag :type="roomAvailable ? 'success' : 'default'" :bordered="false">
            {{ roomAvailable ? '聊天室已连接' : '尚未配置' }}
          </NTag>
          <NButton quaternary circle aria-label="刷新聊天室配置" :loading="loading" @click="loadRoom">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
          </NButton>
        </div>
      </template>

      <NSpin :show="loading">
        <section v-if="roomAvailable" class="chat-room-panel">
          <NAlert type="info" :show-icon="true">
            Element 的登录、房间成员与消息权限仍由 AgentTeams / Matrix 管理。OmicHub 不保存或下发 Matrix 密码、access token。
          </NAlert>
          <div class="chat-room-actions">
            <span>若浏览器阻止嵌入，请在新窗口中打开聊天室。</span>
            <NButton type="primary" size="small" @click="openInNewWindow">
              <template #icon><NIcon><OpenOutline /></NIcon></template>
              在新窗口打开
            </NButton>
          </div>
          <iframe
            class="element-frame"
            :src="elementUrl"
            title="AgentTeams Element 协作聊天室"
            allow="clipboard-read; clipboard-write; microphone; camera; fullscreen"
            referrerpolicy="strict-origin-when-cross-origin"
          />
        </section>

        <section v-else-if="loadFailed" class="chat-room-empty">
          <NEmpty description="聊天室配置暂时无法读取">
            <template #extra><NButton @click="loadRoom">重试</NButton></template>
          </NEmpty>
        </section>

        <section v-else class="chat-room-empty">
          <NEmpty description="AgentTeams Element 聊天室尚未配置">
            <template #extra>
              <p class="empty-note">请管理员在「设置 → AgentTeams Bridge」中填写已授权的 Element 房间地址。</p>
            </template>
          </NEmpty>
        </section>
      </NSpin>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.chat-room-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.chat-room-heading > div { display: grid; gap: 3px; min-width: 0; }
.chat-room-heading strong { color: var(--text-primary); font-size: 15px; }
.chat-room-heading span { color: var(--text-secondary); font-size: 12px; line-height: 1.45; }
.chat-room-panel { display: grid; min-height: calc(100vh - 128px); gap: 12px; }
.chat-room-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}
.element-frame {
  width: 100%;
  min-height: 0;
  height: calc(100vh - 252px);
  border: 1px solid var(--border-color, #e7e9ef);
  border-radius: 10px;
  background: var(--card-color, #fff);
}
.chat-room-empty {
  display: grid;
  place-items: center;
  min-height: min(58vh, 520px);
}
.empty-note { max-width: 360px; margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.55; text-align: center; }
@media (max-width: 640px) {
  .chat-room-heading span { display: none; }
  .chat-room-actions { align-items: flex-start; flex-direction: column; }
  .element-frame { height: calc(100vh - 286px); }
}
@media (prefers-reduced-transparency: reduce) {
  .element-frame { background: var(--body-color, #fff); }
}
</style>
