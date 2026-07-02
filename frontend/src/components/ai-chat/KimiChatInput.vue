<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { NButton, NIcon, NTooltip, NPopover, useMessage } from 'naive-ui'
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
  send: [content: string]
  uploadFile: [file: File]
  toggleWebSearch: []
  triggerSandbox: []
}>()

const chatStore = useChatStore()
const message = useMessage()

const textareaRef = ref<HTMLTextAreaElement>()
const isFocused = ref(false)
const showSlashMenu = ref(false)
const slashQuery = ref('')
const slashMenuPosition = ref({ top: 0, left: 0 })
const showPromptSidebar = ref(false)
const showClearConfirm = ref(false)

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

const canSend = computed(() => localValue.value.trim().length > 0)

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
  if (!content || props.disabled) return
  emit('send', content)
  localValue.value = ''
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

function handleBlur() {
  setTimeout(() => {
    isFocused.value = false
    showSlashMenu.value = false
  }, 200)
}

// 占位功能（后端依赖，本轮提示开发中）
function handleAttachStub() {
  message.info('文件上传功能开发中')
}
function handleWebSearchStub() {
  message.info('联网搜索功能开发中')
}
function handleSandboxStub() {
  message.info('代码沙盒功能开发中')
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

        <!-- 附件上传（占位） -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn" @click="handleAttachStub">
              <n-icon size="18"><AttachOutline /></n-icon>
            </n-button>
          </template>
          上传文件
        </n-tooltip>

        <!-- 联网搜索（占位） -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn" @click="handleWebSearchStub">
              <n-icon size="18"><GlobeOutline /></n-icon>
            </n-button>
          </template>
          联网搜索
        </n-tooltip>

        <!-- 代码沙盒（占位） -->
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

    .send-btn {
      width: 32px;
      height: 32px;
      color: var(--chat-text-muted);
      background: var(--chat-surface);
      transition: all 0.2s ease;

      &:hover,
      &.active {
        color: #fff;
        background: var(--chat-accent);
      }

      &:disabled {
        opacity: 0.4;
      }
    }
  }
}
</style>
