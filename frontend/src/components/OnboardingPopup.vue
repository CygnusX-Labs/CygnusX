<script setup lang="ts">
import { ref } from 'vue'
import logoImg from '@/assets/ChatGPT_logo.png'

interface Props {
  visible: boolean
}
const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'go-knowledge', dontShow: boolean): void
  (e: 'skip', dontShow: boolean): void
}>()

const dontShowAgain = ref(false)

function close() {
  emit('update:visible', false)
}

function handleGoKnowledge() {
  emit('go-knowledge', dontShowAgain.value)
  close()
}

function handleSkip() {
  emit('skip', dontShowAgain.value)
  close()
}
</script>

<template>
  <Transition
    enter-active-class="transition-opacity duration-300"
    leave-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div
      v-if="props.visible"
      class="fixed inset-0 z-[3000] flex items-center justify-center bg-black/50 p-4"
    >
      <!-- 弹窗主体 -->
      <div
        class="relative w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl"
        style="animation: scaleIn 0.4s ease-out both"
      >
        <!-- 顶部主视觉图：上下浮动 -->
        <div class="flex justify-center pt-8 pb-2">
          <img
            :src="logoImg"
            alt="OmicHub Mascot"
            class="h-48 w-auto select-none drop-shadow-md animate-soft-float"
            draggable="false"
          />
        </div>

        <!-- 欢迎文案 -->
        <div class="px-8 pb-2 text-center">
          <h1 class="text-2xl font-bold text-gray-900">
            欢迎来到 OmicHub 🚀
          </h1>
          <p class="mt-2 mb-4 text-sm text-gray-500">
            开启你的高效多组学探索之旅！
          </p>
        </div>

        <!-- 核心快捷导航卡片 -->
        <div class="px-8">
          <div
            role="button"
            tabindex="0"
            class="flex cursor-pointer items-center gap-4 rounded-xl border border-gray-200 bg-white p-4 transition-all hover:border-blue-500 hover:bg-blue-50"
            @click="handleGoKnowledge"
            @keyup.enter="handleGoKnowledge"
          >
            <span class="text-3xl">📚</span>
            <div class="flex-1 text-left">
              <div class="font-bold text-gray-900">实验室知识库</div>
              <div class="mt-0.5 text-xs text-gray-400">
                查阅组内标准操作规范与服务器使用指南
              </div>
            </div>
            <span class="text-gray-300 transition-colors group-hover:text-blue-500">→</span>
          </div>
        </div>

        <!-- 底部操作与免打扰区 -->
        <div class="flex items-center justify-between px-8 py-6">
          <!-- 左侧：不再提示 -->
          <label class="flex cursor-pointer select-none items-center gap-2 text-xs text-gray-400">
            <input
              v-model="dontShowAgain"
              type="checkbox"
              class="h-3.5 w-3.5 cursor-pointer accent-blue-600"
            />
            <span>不再提示 (Don't show this again)</span>
          </label>

          <!-- 右侧：按钮组 -->
          <div class="flex items-center gap-3">
            <button
              type="button"
              class="rounded-lg border border-blue-600 px-4 py-2 text-sm font-medium text-blue-600 transition-colors hover:bg-blue-50"
              @click="handleSkip"
            >
              直接体验
            </button>
            <button
              type="button"
              class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
              @click="handleGoKnowledge"
            >
              前往知识库
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>
