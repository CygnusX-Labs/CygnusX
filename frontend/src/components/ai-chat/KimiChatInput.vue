<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { NButton, NIcon, NTooltip, NDropdown } from 'naive-ui'
import {
  AddOutline,
  ArrowUpOutline,
  ChevronDownOutline,
  ExtensionPuzzleOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import SlashCommandMenu from './SlashCommandMenu.vue'
import type { ModelOption, PluginOption } from './types'

interface Props {
  modelValue: string
  placeholder?: string
  agentMode?: boolean
  selectedModel?: string
  models?: ModelOption[]
  plugins?: PluginOption[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '输入 "/" 唤起插件和技能...',
  agentMode: false,
  selectedModel: 'kimi-k2',
  models: () => [],
  plugins: () => [],
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [content: string]
  toggleAgent: []
  selectModel: [modelId: string]
  selectPlugin: [pluginId: string]
  uploadFile: [file: File]
}>()

const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()
const isFocused = ref(false)
const showSlashMenu = ref(false)
const slashQuery = ref('')
const slashMenuPosition = ref({ top: 0, left: 0 })

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

const selectedModelName = computed(() => {
  const model = props.models.find((m) => m.id === props.selectedModel)
  return model?.name || '选择模型'
})

const modelDropdownOptions = computed(() => {
  return props.models.map((m) => ({
    key: m.id,
    label: `${m.id === props.selectedModel ? '✓ ' : ''}${m.name} - ${m.description}`,
  }))
})

const pluginOptions = computed(() => {
  return props.plugins.map((p) => ({
    key: p.id,
    label: `${p.icon} ${p.name} - ${p.description}`,
  }))
})

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

function triggerFileUpload() {
  fileInputRef.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const files = target.files
  if (files && files.length > 0) {
    emit('uploadFile', files[0])
    target.value = ''
  }
}

function handleModelSelect(key: string) {
  emit('selectModel', key)
}

function handlePluginSelect(key: string) {
  emit('selectPlugin', key)
}
</script>

<template>
  <div class="kimi-chat-input" :class="{ focused: isFocused, disabled }">
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
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button text class="toolbar-btn" @click="triggerFileUpload">
              <template #icon>
                <n-icon size="18"><AddOutline /></n-icon>
              </template>
            </n-button>
          </template>
          上传文件
        </n-tooltip>
        <input
          ref="fileInputRef"
          type="file"
          multiple
          style="display: none"
          @change="handleFileChange"
        />

        <n-button
          text
          class="toolbar-btn agent-btn"
          :class="{ active: agentMode }"
          :title="agentMode ? '关闭 Agent 模式' : '开启 Agent 模式'"
          @click="$emit('toggleAgent')"
        >
          <template #icon>
            <n-icon size="16"><SparklesOutline /></n-icon>
          </template>
          <span class="btn-label">Agent</span>
        </n-button>

        <n-dropdown :options="pluginOptions" trigger="click" @select="handlePluginSelect">
          <n-button text class="toolbar-btn plugin-btn" title="选择插件">
            <template #icon>
              <n-icon size="16"><ExtensionPuzzleOutline /></n-icon>
            </template>
            <span class="btn-label">插件</span>
          </n-button>
        </n-dropdown>
      </div>

      <div class="toolbar-right">
        <n-dropdown :options="modelDropdownOptions" trigger="click" @select="handleModelSelect">
          <n-button text class="toolbar-btn model-btn">
            <span class="model-name">{{ selectedModelName }}</span>
            <n-icon size="14"><ChevronDownOutline /></n-icon>
          </n-button>
        </n-dropdown>

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
  </div>
</template>

<style scoped lang="scss">
.kimi-chat-input {
  background: var(--chat-input-bg);
  border: 1px solid var(--chat-input-border);
  border-radius: 20px;
  padding: 12px 16px;
  transition: all 0.3s ease;

  &.focused {
    border-color: var(--chat-accent);
    box-shadow: 0 0 0 2px rgba(79, 142, 247, 0.15);
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
      transition: all 0.2s ease;

      &:hover {
        color: var(--chat-text-primary);
        background: var(--chat-surface-hover);
      }

      &.agent-btn.active {
        color: var(--chat-accent);
        background: rgba(79, 142, 247, 0.1);
      }

      .btn-label {
        margin-left: 4px;
        font-size: 13px;
      }

      &.model-btn {
        .model-name {
          margin-right: 4px;
          font-size: 13px;
        }
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
