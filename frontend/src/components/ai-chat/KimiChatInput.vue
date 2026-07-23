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
} from '@vicons/ionicons5'
import SlashCommandMenu from './SlashCommandMenu.vue'
import PromptSidebar from './PromptSidebar.vue'
import { useChatStore } from '@/stores/chat'
import { useSiteConfigStore } from '@/stores/site-config'
import apiClient from '@/api/client'
import type { FileAttachment } from './types'

interface Props {
  modelValue: string
  placeholder?: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '输入消息，或点击左侧工具唤起能力...',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [content: string, options: { attachments?: FileAttachment[]; enableWebSearch?: boolean; enableCodeExecution?: boolean }]
  triggerSandbox: []
}>()

const chatStore = useChatStore()
const siteConfigStore = useSiteConfigStore()
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
})

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

const canSend = computed(() => localValue.value.trim().length > 0 || attachments.value.length > 0)

function handleKeydown(e: KeyboardEvent) {
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
  if ((!content && !attachments.value.length) || props.disabled) return
  emit('send', content, {
    attachments: attachments.value.length ? [...attachments.value] : undefined,
    enableWebSearch: chatStore.enableWebSearch,
  })
  localValue.value = ''
  attachments.value = []
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

let blurTimer: ReturnType<typeof setTimeout> | null = null

function handleBlur() {
  if (blurTimer) clearTimeout(blurTimer)
  blurTimer = setTimeout(() => {
    isFocused.value = false
    showSlashMenu.value = false
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

    <div v-if="attachments.length" class="attachment-list">
      <NTag
        v-for="(att, idx) in attachments"
        :key="idx"
        size="small"
        round
        closable
        :disabled="uploading"
        @close="removeAttachment(idx)"
      >
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

        <n-button
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
      {{ siteConfigStore.aiInputHint }}
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

  .attachment-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
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
    }
  }

  .input-hint {
    text-align: center;
    font-size: 12px;
    color: var(--chat-text-muted);
    margin-top: 8px;
    line-height: 1.4;
  }
}
</style>
