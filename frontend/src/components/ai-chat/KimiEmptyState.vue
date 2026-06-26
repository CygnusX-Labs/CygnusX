<script setup lang="ts">
import { ref } from 'vue'
import KimiChatInput from './KimiChatInput.vue'
import type { QuickPrompt } from './types'

interface Props {
  logoText?: string
  quickPrompts?: QuickPrompt[]
}

withDefaults(defineProps<Props>(), {
  logoText: 'OMIC HUB',
  quickPrompts: () => [],
})

const emit = defineEmits<{
  sendPrompt: [prompt: string]
  uploadFile: [file: File]
}>()

const inputValue = ref('')

const logoMotion = {
  initial: { opacity: 0, y: 30, scale: 0.95 },
  enter: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 600, ease: 'easeOut' },
  },
}

const cardMotion = (index: number) => ({
  initial: { opacity: 0, y: 20 },
  enter: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 400,
      delay: 300 + index * 80,
      ease: 'easeOut',
    },
  },
})

const inputMotion = {
  initial: { opacity: 0, y: 20 },
  enter: {
    opacity: 1,
    y: 0,
    transition: { duration: 500, delay: 800, ease: 'easeOut' },
  },
}

function handlePromptClick(prompt: QuickPrompt) {
  emit('sendPrompt', prompt.text)
}

function handleSend(content: string) {
  emit('sendPrompt', content)
}
</script>

<template>
  <div class="kimi-empty-state">
    <div class="empty-content" v-motion="logoMotion">
      <div class="logo-container">
        <h1 class="main-logo">{{ logoText }}</h1>
        <div class="logo-subtitle">AI 智能助手</div>
      </div>

      <div class="quick-prompts">
        <div
          v-for="(prompt, index) in quickPrompts"
          :key="index"
          v-motion="cardMotion(index)"
          class="prompt-card"
          @click="handlePromptClick(prompt)"
        >
          <span class="prompt-icon">{{ prompt.icon }}</span>
          <span class="prompt-text">{{ prompt.text }}</span>
        </div>
      </div>
    </div>

    <div v-motion="inputMotion" class="empty-input-wrapper">
      <KimiChatInput
        v-model="inputValue"
        placeholder="输入 / 唤起插件和技能..."
        @send="handleSend"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.kimi-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 40px 24px;
  position: relative;
  overflow-y: auto;

  .empty-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 48px;
  }

  .logo-container {
    text-align: center;
    margin-bottom: 48px;

    .main-logo {
      font-size: 72px;
      font-weight: 800;
      letter-spacing: 12px;
      color: var(--chat-text-primary);
      margin: 0;
      animation: logoBreath 4s ease-in-out infinite;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    .logo-subtitle {
      font-size: 16px;
      color: var(--chat-text-secondary);
      margin-top: 8px;
      letter-spacing: 4px;
    }
  }

  .quick-prompts {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    max-width: 720px;
    width: 100%;
  }

  .prompt-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px;
    background: var(--chat-surface);
    border: 1px solid var(--chat-border);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.25s ease;
  }

  .prompt-card:hover {
    background: var(--chat-surface-hover);
    border-color: var(--chat-accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(79, 142, 247, 0.1);
  }

  .prompt-icon {
    font-size: 20px;
    flex-shrink: 0;
  }

  .prompt-text {
    font-size: 14px;
    color: var(--chat-text-secondary);
    line-height: 1.4;
  }

  .empty-input-wrapper {
    width: 100%;
    max-width: 760px;
    position: sticky;
    bottom: 0;
  }
}

@keyframes logoBreath {
  0%,
  100% {
    opacity: 1;
    text-shadow: 0 0 40px rgba(79, 142, 247, 0.15);
  }
  50% {
    opacity: 0.85;
    text-shadow: 0 0 60px rgba(79, 142, 247, 0.25);
  }
}

@media (max-width: 768px) {
  .quick-prompts {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .quick-prompts {
    grid-template-columns: 1fr;
  }
}
</style>
