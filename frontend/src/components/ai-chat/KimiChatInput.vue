<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { NButton, NIcon, NTooltip, NPopover, useMessage, NTag } from 'naive-ui'
import {
  ArrowUpOutline,
  BulbOutline,
  AttachOutline,
  GlobeOutline,
  TerminalOutline,
  SparklesOutline,
  TrashOutline,
  PauseOutline,
  PlayOutline,
  RefreshOutline,
  PersonOutline,
  ExtensionPuzzleOutline,
  DocumentTextOutline,
} from '@vicons/ionicons5'
import SlashCommandMenu from './SlashCommandMenu.vue'
import MentionMenu from './MentionMenu.vue'
import PromptSidebar from './PromptSidebar.vue'
import { useChatStore } from '@/stores/chat'
import { useSiteConfigStore } from '@/stores/site-config'
import { useAgentHubStore } from '@/stores/agentHub'
import { matchWorkbenchIntent } from '@/config/aiIntents'
import apiClient from '@/api/client'
import type { DataFile } from '@/types'
import type { AgentTemplate, SkillItem } from '@/types/agent'
import type { FileAttachment, MentionItem } from './types'

interface Props {
  modelValue: string
  placeholder?: string
  disabled?: boolean
  /** 是否正在流式输出 */
  isStreaming?: boolean
  /** 是否已暂停 */
  isPaused?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '输入消息，@ 引用工作区文件或指定智能体 / 技能...',
  disabled: false,
  isStreaming: false,
  isPaused: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [
    content: string,
    options: {
      attachments?: FileAttachment[]
      enableWebSearch?: boolean
      enableCodeExecution?: boolean
      workbenchIntent?: boolean
      /** @ 显式指定的智能体（本条消息转交给该专家回答） */
      explicitAgentId?: string
      /** @ 挂载到本次对话的技能名 */
      skillNames?: string[]
    },
  ]
  triggerSandbox: []
  pause: []
  resume: []
  regenerate: []
}>()

const chatStore = useChatStore()
const siteConfigStore = useSiteConfigStore()
const agentHub = useAgentHubStore()
const message = useMessage()

const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()
const isFocused = ref(false)
const showSlashMenu = ref(false)
const slashQuery = ref('')
const slashMenuPosition = ref({ top: 0, left: 0 })
const showPromptSidebar = ref(false)
const showClearConfirm = ref(false)
const attachments = ref<FileAttachment[]>([])
const uploading = ref(false)

// ===== @ 引用状态 =====
const showMentionMenu = ref(false)
const mentionQuery = ref('')
const mentionActiveIndex = ref(0)
const mentionPosition = ref({ top: 0, left: 0 })
const workspaceFiles = ref<DataFile[]>([])
const mentionLoading = ref(false)
const mentionError = ref(false)
/** @ 显式指定的智能体（随下一条消息发送） */
const pendingAgent = ref<AgentTemplate | null>(null)
/** @ 挂载的技能（随下一条消息发送） */
const pendingSkills = ref<SkillItem[]>([])

const localValue = ref(props.modelValue)

watch(localValue, (val) => {
  emit('update:modelValue', val)
})

watch(
  () => props.modelValue,
  (val) => {
    if (val !== localValue.value) {
      localValue.value = val
    }
  }
)

watch(localValue, () => {
  nextTick(autoResize)
  detectSlashCommand()
  detectMention()
})

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

const canSend = computed(
  () =>
    localValue.value.trim().length > 0 ||
    attachments.value.length > 0 ||
    pendingAgent.value !== null ||
    pendingSkills.value.length > 0,
)

function handleKeydown(e: KeyboardEvent) {
  // @ 补全面板打开时，优先接管方向键 / Enter / Esc
  if (showMentionMenu.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      mentionActiveIndex.value = (mentionActiveIndex.value + 1) % Math.max(mentionItems.value.length, 1)
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      mentionActiveIndex.value =
        (mentionActiveIndex.value - 1 + mentionItems.value.length) % Math.max(mentionItems.value.length, 1)
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const item = mentionItems.value[mentionActiveIndex.value]
      if (item) selectMention(item)
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      showMentionMenu.value = false
      return
    }
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (canSend.value && !props.disabled) {
      handleSend()
    }
  }
  if (e.key === 'Escape') {
    showSlashMenu.value = false
  }
  if (e.key === '/' && localValue.value === '') {
    nextTick(() => {
      showSlashMenu.value = true
      slashQuery.value = ''
      updateSlashMenuPosition()
    })
  }
}

function detectSlashCommand() {
  const text = localValue.value
  const lastLine = text.split('\n').pop() || ''

  if (lastLine.startsWith('/')) {
    showSlashMenu.value = true
    slashQuery.value = lastLine.slice(1)
    updateSlashMenuPosition()
  } else {
    showSlashMenu.value = false
  }
}

// ===== @ 引用：检测 / 数据 / 选择 =====

/** 提取光标处活跃的 @ 查询词；不在 @ 上下文中返回 null */
function readMentionQuery(): string | null {
  const el = textareaRef.value
  const text = localValue.value
  const caret = el?.selectionStart ?? text.length
  const before = text.slice(0, caret)
  // @ 需在行首或空白后，且到光标间不含空白
  const m = before.match(/(?:^|[\s\n])@([\w./\-@一-龥]*)$/)
  return m ? m[1] : null
}

function detectMention() {
  const q = readMentionQuery()
  if (q === null) {
    showMentionMenu.value = false
    return
  }
  // 与 slash 菜单互斥
  showSlashMenu.value = false
  showMentionMenu.value = true
  mentionQuery.value = q
  mentionActiveIndex.value = 0
  updateMentionPosition()
  ensureMentionData()
}

function updateMentionPosition() {
  const el = textareaRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  mentionPosition.value = {
    top: Math.max(8, rect.top - 360),
    left: rect.left + 12,
  }
}

/** 首次打开 @ 面板时加载工作区文件与智能体 / 技能资产 */
async function ensureMentionData() {
  if (!workspaceFiles.value.length && !mentionLoading.value) {
    await loadWorkspaceFiles()
  }
  if (!agentHub.agents.length) agentHub.fetchAgents()
  if (!agentHub.skills.length) agentHub.fetchSkills()
}

async function loadWorkspaceFiles() {
  mentionLoading.value = true
  mentionError.value = false
  try {
    const res = await apiClient.get<{ items: DataFile[]; total: number }>('/files')
    workspaceFiles.value = res.data.items || []
  } catch (e) {
    mentionError.value = true
    console.error('加载工作区文件失败:', e)
  } finally {
    mentionLoading.value = false
  }
}

/** 简单模糊匹配：名称 / 路径包含查询词（不区分大小写） */
function fuzzyMatch(text: string, q: string): boolean {
  if (!q) return true
  return text.toLowerCase().includes(q.toLowerCase())
}

const mentionItems = computed<MentionItem[]>(() => {
  const q = mentionQuery.value
  const files: MentionItem[] = workspaceFiles.value
    .filter((f) => fuzzyMatch(`${f.original_name} ${f.directory || ''}`, q))
    .slice(0, 30)
    .map((f) => ({
      kind: 'file' as const,
      key: `file-${f.id}`,
      name: f.original_name,
      description: f.directory ? `${f.directory}/ · ${formatBytes(f.size)}` : formatBytes(f.size),
      file: f,
    }))

  const agents: MentionItem[] = agentHub.activeAgents
    .filter((a) => fuzzyMatch(`${a.name} ${a.description}`, q))
    .slice(0, 8)
    .map((a) => ({
      kind: 'agent' as const,
      key: `agent-${a.id}`,
      name: a.name,
      description: a.description || '智能体',
      agent: a,
    }))

  const skills: MentionItem[] = agentHub.skills
    .filter((s) => s.is_active && fuzzyMatch(`${s.name} ${s.description}`, q))
    .slice(0, 8)
    .map((s) => ({
      kind: 'skill' as const,
      key: `skill-${s.id}`,
      name: s.name,
      description: s.description || '技能',
      skill: s,
    }))

  return [...files, ...agents, ...skills]
})

function formatBytes(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)}KB`
  return `${size}B`
}

/** 把光标处活跃的 @查询词 替换为 @名称 + 空格，返回是否替换成功 */
function replaceMentionToken(name: string): void {
  const el = textareaRef.value
  const text = localValue.value
  const caret = el?.selectionStart ?? text.length
  const before = text.slice(0, caret).replace(/@([\w./\-@一-龥]*)$/, `@${name} `)
  localValue.value = before + text.slice(caret)
  nextTick(() => {
    if (el) {
      const pos = before.length
      el.focus()
      el.setSelectionRange(pos, pos)
    }
  })
}

function selectMention(item: MentionItem) {
  if (item.kind === 'file' && item.file) {
    const f = item.file
    const fileId = `file://${f.id}`
    // 去重：已引用则不重复添加
    if (!attachments.value.some((a) => a.file_id === fileId)) {
      attachments.value.push({
        name: f.original_name,
        size: f.size,
        type: 'application/octet-stream',
        url: `/api/v1/files/${f.id}/download`,
        file_id: fileId,
        source: 'workspace',
      })
    }
    replaceMentionToken(f.original_name)
  } else if (item.kind === 'agent' && item.agent) {
    pendingAgent.value = item.agent
    replaceMentionToken(item.agent.name)
  } else if (item.kind === 'skill' && item.skill) {
    if (!pendingSkills.value.some((s) => s.id === item.skill!.id)) {
      pendingSkills.value.push(item.skill)
    }
    replaceMentionToken(item.skill.name)
  }
  showMentionMenu.value = false
}

function removePendingAgent() {
  pendingAgent.value = null
}

function removePendingSkill(idx: number) {
  pendingSkills.value.splice(idx, 1)
}

function updateSlashMenuPosition() {
  if (!textareaRef.value) return
  const rect = textareaRef.value.getBoundingClientRect()
  slashMenuPosition.value = {
    top: rect.top - 220,
    left: rect.left + 20,
  }
}

function handleSlashSelect(command: string) {
  const text = localValue.value
  const lines = text.split('\n')
  lines[lines.length - 1] = command + ' '
  localValue.value = lines.join('\n')
  showSlashMenu.value = false
  nextTick(() => textareaRef.value?.focus())
}

function handleSend() {
  const content = localValue.value.trim()
  const hasPayload =
    content.length > 0 ||
    attachments.value.length > 0 ||
    pendingAgent.value !== null ||
    pendingSkills.value.length > 0
  if (!hasPayload || props.disabled) return

  // Feature 5: 意图匹配 → 自动切换工作台模式
  const workbenchIntent = matchWorkbenchIntent(content)
  if (workbenchIntent) {
    message.info('已为您切换至工作台模式，便于跟踪任务进度')
  }

  emit('send', content, {
    attachments: attachments.value.length ? [...attachments.value] : undefined,
    enableWebSearch: chatStore.enableWebSearch,
    workbenchIntent,
    explicitAgentId: pendingAgent.value?.id,
    skillNames: pendingSkills.value.length ? pendingSkills.value.map((s) => s.name) : undefined,
  })
  localValue.value = ''
  attachments.value = []
  pendingAgent.value = null
  pendingSkills.value = []
  showMentionMenu.value = false
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

function handlePause() {
  emit('pause')
}

function handleResume() {
  emit('resume')
}

function handleRegenerate() {
  emit('regenerate')
}

let blurTimer: ReturnType<typeof setTimeout> | null = null

function handleBlur() {
  if (blurTimer) clearTimeout(blurTimer)
  blurTimer = setTimeout(() => {
    isFocused.value = false
    showSlashMenu.value = false
    showMentionMenu.value = false
  }, 200)
}

function handleAttach() {
  fileInputRef.value?.click()
}

async function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length) return
  uploading.value = true
  for (const file of Array.from(files)) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await apiClient.post('/files/chat-upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      attachments.value.push({
        name: file.name,
        size: file.size,
        type: file.type || 'application/octet-stream',
        url: res.data.url,
        file_id: res.data.id,
      })
    } catch (err: any) {
      message.error(`上传 ${file.name} 失败: ${err?.response?.data?.detail || err.message}`)
    }
  }
  uploading.value = false
  input.value = ''
}

function removeAttachment(idx: number) {
  attachments.value.splice(idx, 1)
}

function handleWebSearchToggle() {
  chatStore.toggleWebSearch()
}

function handleSandboxStub() {
  message.info('代码执行请在生成代码后点击代码块“运行”按钮')
}

function handlePromptSelect(content: string) {
  localValue.value = content
  nextTick(() => {
    textareaRef.value?.focus()
    autoResize()
  })
}

function handleClearConfirm() {
  localValue.value = ''
  showClearConfirm.value = false
  nextTick(() => {
    if (textareaRef.value) textareaRef.value.style.height = 'auto'
  })
}

onMounted(() => {
  siteConfigStore.fetchSiteConfig()
})

onUnmounted(() => {
  if (blurTimer) clearTimeout(blurTimer)
})
</script>

<template>
  <div
    class="kimi-chat-input"
    :class="{ focused: isFocused, disabled, 'deep-thinking': chatStore.deepThinking }"
  >
    <div class="input-wrapper">
      <textarea
        ref="textareaRef"
        v-model="localValue"
        class="chat-textarea"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @focus="isFocused = true"
        @blur="handleBlur"
        @keydown="handleKeydown"
      />
    </div>

    <input
      ref="fileInputRef"
      type="file"
      multiple
      style="display: none"
      @change="handleFileChange"
    />

    <div
      v-if="attachments.length || pendingAgent || pendingSkills.length"
      class="ref-bar"
    >
      <!-- @ 指定的智能体 -->
      <NTag
        v-if="pendingAgent"
        size="small"
        round
        closable
        class="ref-chip ref-agent"
        @close="removePendingAgent"
      >
        <template #icon>
          <n-icon><PersonOutline /></n-icon>
        </template>
        {{ pendingAgent.name }}
      </NTag>

      <!-- @ 挂载的技能 -->
      <NTag
        v-for="(sk, idx) in pendingSkills"
        :key="`skill-${sk.id}`"
        size="small"
        round
        closable
        class="ref-chip ref-skill"
        @close="removePendingSkill(idx)"
      >
        <template #icon>
          <n-icon><ExtensionPuzzleOutline /></n-icon>
        </template>
        {{ sk.name }}
      </NTag>

      <!-- 附件 / @ 引用的工作区文件 -->
      <NTag
        v-for="(att, idx) in attachments"
        :key="`att-${idx}`"
        size="small"
        round
        closable
        class="ref-chip"
        :class="{ 'ref-file': att.source === 'workspace' }"
        :disabled="uploading"
        @close="removeAttachment(idx)"
      >
        <template v-if="att.source === 'workspace'" #icon>
          <n-icon><DocumentTextOutline /></n-icon>
        </template>
        {{ att.name }}
      </NTag>
    </div>

    <SlashCommandMenu
      v-if="showSlashMenu"
      :query="slashQuery"
      :position="slashMenuPosition"
      @select="handleSlashSelect"
      @close="showSlashMenu = false"
    />

    <MentionMenu
      v-if="showMentionMenu"
      :items="mentionItems"
      :active-index="mentionActiveIndex"
      :position="mentionPosition"
      :loading="mentionLoading"
      :error="mentionError"
      @select="selectMention"
      @hover="mentionActiveIndex = $event"
      @retry="loadWorkspaceFiles"
      @close="showMentionMenu = false"
    />

    <div class="input-toolbar">
      <div class="toolbar-left">
        <!-- 提示词模板 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn" @click="showPromptSidebar = true">
              <n-icon size="18"><BulbOutline /></n-icon>
            </n-button>
          </template>
          提示词模板
        </n-tooltip>

        <!-- 附件上传 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn" :loading="uploading" @click="handleAttach">
              <n-icon size="18"><AttachOutline /></n-icon>
            </n-button>
          </template>
          上传文件
        </n-tooltip>

        <!-- 联网搜索 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              text
              class="toolbar-btn"
              :class="{ active: chatStore.enableWebSearch }"
              @click="handleWebSearchToggle"
            >
              <n-icon size="18"><GlobeOutline /></n-icon>
            </n-button>
          </template>
          {{ chatStore.enableWebSearch ? '关闭联网搜索' : '开启联网搜索' }}
        </n-tooltip>

        <!-- 代码执行提示 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn" @click="handleSandboxStub">
              <n-icon size="18"><TerminalOutline /></n-icon>
            </n-button>
          </template>
          代码执行
        </n-tooltip>

        <!-- 深度思考 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              text
              class="toolbar-btn deep-thinking-btn"
              :class="{ active: chatStore.deepThinking }"
              @click="chatStore.toggleDeepThinking()"
            >
              <n-icon size="18"><SparklesOutline /></n-icon>
              <span class="btn-label">深度思考</span>
            </n-button>
          </template>
          {{ chatStore.deepThinking ? '关闭深度思考' : '开启深度思考' }}
        </n-tooltip>
      </div>

      <div class="toolbar-right">
        <!-- 清空 -->
        <n-popover v-model:show="showClearConfirm" trigger="click" placement="top-end" :width="200">
          <template #trigger>
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-button text class="toolbar-btn clear-btn" :disabled="!localValue">
                  <n-icon size="18"><TrashOutline /></n-icon>
                </n-button>
              </template>
              清空输入
            </n-tooltip>
          </template>
          <div style="text-align: center">
            <p style="margin: 0 0 10px; font-size: 13px">确认清空输入框内容？</p>
            <div style="display: flex; gap: 8px; justify-content: center">
              <n-button size="small" @click="showClearConfirm = false">取消</n-button>
              <n-button size="small" type="error" @click="handleClearConfirm">确认清空</n-button>
            </div>
          </div>
        </n-popover>

        <!-- 流式输出中：暂停按钮 -->
        <n-tooltip v-if="isStreaming" trigger="hover">
          <template #trigger>
            <n-button circle class="send-btn pause-btn" @click="handlePause">
              <template #icon>
                <n-icon size="18"><PauseOutline /></n-icon>
              </template>
            </n-button>
          </template>
          暂停生成
        </n-tooltip>

        <!-- 已暂停：继续 + 重新生成 -->
        <template v-else-if="isPaused">
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-button circle class="send-btn resume-btn" @click="handleResume">
                <template #icon>
                  <n-icon size="18"><PlayOutline /></n-icon>
                </template>
              </n-button>
            </template>
            继续生成
          </n-tooltip>
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-button circle class="send-btn regenerate-btn" @click="handleRegenerate">
                <template #icon>
                  <n-icon size="18"><RefreshOutline /></n-icon>
                </template>
              </n-button>
            </template>
            重新生成
          </n-tooltip>
        </template>

        <!-- 默认：发送按钮 -->
        <n-button
          v-else
          circle
          class="send-btn"
          :class="{ active: canSend }"
          :disabled="!canSend || disabled"
          @click="handleSend"
        >
          <template #icon>
            <n-icon size="18"><ArrowUpOutline /></n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <div class="input-hint">
      <template v-if="isPaused">
        <span class="paused-hint">生成已暂停</span>
      </template>
      <template v-else>
        {{ siteConfigStore.aiInputHint }}
      </template>
    </div>

    <PromptSidebar
      :visible="showPromptSidebar"
      @close="showPromptSidebar = false"
      @select="handlePromptSelect"
    />
  </div>
</template>

<style scoped lang="scss">
.kimi-chat-input {
  background: var(--chat-input-bg);
  border: 1px solid var(--chat-input-border);
  border-radius: 20px;
  padding: 12px 16px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;

  &.focused {
    border-color: var(--chat-accent);
    box-shadow: 0 0 0 2px rgba(79, 142, 247, 0.15);
  }

  &.deep-thinking {
    border-color: var(--chat-deep-thinking);
    box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.3);
  }

  &.disabled {
    opacity: 0.6;
    pointer-events: none;
  }

  .input-wrapper {
    margin-bottom: 8px;
  }

  .ref-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;

    .ref-chip {
      max-width: 240px;
    }

    .ref-file {
      color: var(--arco-primary, #4c6fff);
      background: var(--arco-primary-light, rgba(76, 111, 255, 0.12));
    }

    .ref-agent {
      color: var(--icon-visualization, #8b5cf6);
      background: var(--icon-purple-bg, rgba(139, 92, 246, 0.12));
    }

    .ref-skill {
      color: #059669;
      background: var(--icon-green-bg, rgba(5, 150, 105, 0.12));
    }
  }

  .chat-textarea {
    width: 100%;
    min-height: 24px;
    max-height: 200px;
    background: transparent;
    border: none;
    outline: none;
    color: var(--chat-text-primary);
    font-size: 15px;
    line-height: 1.6;
    resize: none;
    font-family: inherit;

    &::placeholder {
      color: var(--chat-text-muted);
    }

    &::-webkit-scrollbar {
      width: 4px;
    }

    &::-webkit-scrollbar-thumb {
      background: var(--chat-border);
      border-radius: 2px;
    }
  }

  .input-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1px solid var(--chat-border);
    padding-top: 8px;

    .toolbar-left,
    .toolbar-right {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .toolbar-btn {
      color: var(--chat-text-secondary);
      padding: 4px 8px;
      border-radius: 8px;
      transition: all 0.15s ease;

      &:hover {
        color: var(--chat-text-primary);
        background: var(--chat-surface-hover);
      }

      &.active {
        color: var(--chat-accent);
        background: rgba(79, 142, 247, 0.12);
      }

      .btn-label {
        margin-left: 4px;
        font-size: 13px;
      }

      &.deep-thinking-btn.active {
        color: var(--chat-deep-thinking);
        background: rgba(245, 158, 11, 0.12);
      }

      &.clear-btn:hover {
        color: var(--chat-error);
      }
    }

    .toolbar-left > :nth-child(1) .toolbar-btn { color: #4C6FFF; background: var(--icon-blue-bg); }
    .toolbar-left > :nth-child(2) .toolbar-btn { color: #8B5CF6; background: var(--icon-purple-bg); }
    .toolbar-left > :nth-child(3) .toolbar-btn { color: #0891B2; background: var(--icon-cyan-bg); }
    .toolbar-left > :nth-child(4) .toolbar-btn { color: #059669; background: var(--icon-green-bg); }
    .toolbar-left > :nth-child(5) .toolbar-btn { color: #D97706; background: var(--icon-orange-bg); }

    .send-btn {
      width: 32px;
      height: 32px;
      color: var(--chat-text-muted);
      background: var(--chat-surface);
      transition: all 0.2s ease;

      &:hover,
      &.active {
        color: #fff;
        background: var(--brand-gradient);
      }

      &:disabled {
        opacity: 0.4;
      }

      &.pause-btn {
        color: #fff;
        background: var(--arco-warning, #FF7D00);
        animation: pause-pulse 1.6s ease-in-out infinite;
      }

      &.resume-btn {
        color: #fff;
        background: var(--arco-success, #00B42A);
      }

      &.regenerate-btn {
        color: var(--chat-text-secondary);
        background: var(--chat-surface);

        &:hover {
          color: #fff;
          background: var(--brand-gradient);
        }
      }
    }
  }

  .input-hint {
    text-align: center;
    font-size: 12px;
    color: var(--chat-text-muted);
    margin-top: 8px;
    line-height: 1.4;
  }

  .paused-hint {
    color: var(--arco-warning, #FF7D00);
    font-weight: 500;
  }
}

@keyframes pause-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

@media (prefers-reduced-motion: reduce) {
  .pause-btn {
    animation: none !important;
  }
}
</style>
