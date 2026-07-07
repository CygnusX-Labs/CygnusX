<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NCard,
  NSpin,
  NTag,
  NSpace,
  NIcon,
  NEmpty,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  TerminalOutline,
  ExpandOutline,
  ContractOutline,
  TrashOutline,
  TimeOutline,
  PlayOutline,
} from '@vicons/ionicons5'
import XTerminal from '@/components/terminal/XTerminal.vue'
import ImageSelector from '@/components/terminal/ImageSelector.vue'
import ResourceSettings from '@/components/terminal/ResourceSettings.vue'
import { useTerminalStore } from '@/stores/terminal'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const store = useTerminalStore()

const fullScreen = ref(false)
const remainingMinutes = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const session = computed(() => store.currentSession)
const loading = computed(() => store.loading)
const images = computed(() => store.enabledImages)
const selectedImage = computed(() => store.selectedImage)
const memoryRange = computed(() => store.memoryRange)
const cpuRange = computed(() => store.cpuRange)

const memoryMb = computed({
  get: () => store.effectiveMemoryMb,
  set: (val: number) => {
    store.customMemoryMb = val
  },
})

const cpuCores = computed({
  get: () => store.effectiveCpuCores,
  set: (val: number) => {
    store.customCpuCores = val
  },
})

const statusType = computed(() => {
  switch (session.value?.status) {
    case 'running':
      return 'success'
    case 'idle':
      return 'warning'
    case 'creating':
      return 'info'
    case 'error':
      return 'error'
    default:
      return 'default'
  }
})

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    if (!session.value?.expires_at) return
    const remaining = Math.max(
      0,
      Math.floor((new Date(session.value.expires_at).getTime() - Date.now()) / 60000),
    )
    remainingMinutes.value = remaining
  }, 60000)
}

async function handleCreate() {
  if (!selectedImage.value) {
    message.warning('请先选择一个镜像')
    return
  }
  try {
    await store.createSession()
    message.success('沙盒终端已启动')
    startCountdown()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '启动沙盒终端失败')
  }
}

function handleDestroy() {
  dialog.warning({
    title: '销毁终端会话',
    content: '确定要销毁当前终端会话吗？容器将被立即停止并删除。',
    positiveText: '销毁',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (session.value) {
        try {
          await store.destroySession(session.value.session_id)
          message.success('终端会话已销毁')
        } catch {
          message.error('销毁失败')
        }
      }
      if (countdownTimer) clearInterval(countdownTimer)
      router.push('/tools')
    },
  })
}

onMounted(async () => {
  await store.fetchImages()
  if (session.value) {
    startCountdown()
  }
})

onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})

watch(
  () => session.value?.expires_at,
  () => {
    if (session.value?.expires_at) {
      const remaining = Math.max(
        0,
        Math.floor((new Date(session.value.expires_at).getTime() - Date.now()) / 60000),
      )
      remainingMinutes.value = remaining
    }
  },
)
</script>

<template>
  <div class="terminal-page" :class="{ 'terminal-fullscreen': fullScreen }">
    <div class="terminal-header">
      <div class="header-left">
        <NIcon :size="20" color="#0dbc79">
          <TerminalOutline />
        </NIcon>
        <span class="header-title">云端沙盒终端</span>
        <NTag v-if="session" :type="statusType" size="small" round>
          {{ session.status }}
        </NTag>
        <span v-if="session" class="session-id">{{ session.session_id }}</span>
        <span v-if="session?.image_name" class="image-name">{{ session.image_name }}</span>
      </div>
      <div class="header-right">
        <NSpace v-if="session" align="center" :size="8">
          <NIcon :size="14" color="#86909c">
            <TimeOutline />
          </NIcon>
          <span class="remaining-time">{{ remainingMinutes }}分钟</span>
        </NSpace>
        <NButton
          quaternary
          size="small"
          @click="fullScreen = !fullScreen"
        >
          <template #icon>
            <NIcon>
              <ContractOutline v-if="fullScreen" />
              <ExpandOutline v-else />
            </NIcon>
          </template>
        </NButton>
        <NButton
          type="error"
          size="small"
          quaternary
          @click="handleDestroy"
          :disabled="!session"
        >
          <template #icon>
            <NIcon>
              <TrashOutline />
            </NIcon>
          </template>
        </NButton>
      </div>
    </div>

    <div class="terminal-body">
      <!-- 加载中 -->
      <div v-if="loading" class="terminal-loading">
        <NSpin size="large" />
        <p class="loading-text">正在启动隔离容器...</p>
        <p v-if="selectedImage" class="loading-desc">镜像：{{ selectedImage.name }}</p>
      </div>

      <!-- 终端运行中 -->
      <div v-else-if="session?.ws_url" class="terminal-content">
        <XTerminal :session-id="session.session_id" />
      </div>

      <!-- 镜像选择页 -->
      <div v-else class="terminal-selector">
        <div class="selector-header">
          <NIcon :size="32" color="#0dbc79">
            <TerminalOutline />
          </NIcon>
          <div class="selector-titles">
            <h2 class="selector-title">选择分析环境</h2>
            <p class="selector-subtitle">选择预装工具链的镜像，启动一个隔离、用完即毁的沙盒终端</p>
          </div>
        </div>

        <NCard content-style="padding: 20px" class="selector-card">
          <ImageSelector
            v-model="store.selectedImageId"
            :images="images"
          />

          <ResourceSettings
            v-model:memory-mb="memoryMb"
            v-model:cpu-cores="cpuCores"
            :memory-min="memoryRange.min"
            :memory-max="memoryRange.max"
            :memory-step="memoryRange.step"
            :cpu-min="cpuRange.min"
            :cpu-max="cpuRange.max"
            :cpu-step="cpuRange.step"
            :disabled="loading"
          />

          <div class="selector-actions">
            <NButton
              type="primary"
              size="large"
              :disabled="!selectedImage"
              :loading="loading"
              @click="handleCreate"
            >
              <template #icon>
                <NIcon>
                  <PlayOutline />
                </NIcon>
              </template>
              启动 {{ selectedImage?.name || '终端' }}
            </NButton>
          </div>
        </NCard>

        <NEmpty v-if="images.length === 0 && !loading" description="暂无可用镜像，请联系管理员配置 terminal_images.yaml" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.terminal-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--n-color, #fff);
}

.terminal-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: #1e1e1e;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--n-border-color, #e0e0e6);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--neutral-text-1);
}

.session-id {
  font-size: 12px;
  color: var(--neutral-text-3);
  font-family: monospace;
}

.image-name {
  font-size: 12px;
  color: var(--neutral-text-2);
  background: var(--neutral-fill-2);
  padding: 2px 8px;
  border-radius: 4px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.remaining-time {
  font-size: 12px;
  color: var(--neutral-text-3);
}

.terminal-body {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: auto;
}

.terminal-content {
  width: 100%;
  height: 100%;
}

.terminal-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
}

.loading-text {
  font-size: 14px;
  color: var(--neutral-text-3);
  margin: 0;
}

.loading-desc {
  font-size: 12px;
  color: var(--neutral-text-2);
  margin: 0;
}

.terminal-selector {
  padding: 24px;
  max-width: 1000px;
  margin: 0 auto;
  width: 100%;
}

.selector-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.selector-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.selector-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  color: var(--neutral-text-1);
}

.selector-subtitle {
  font-size: 13px;
  color: var(--neutral-text-3);
  margin: 0;
}

.selector-card {
  margin-bottom: 20px;
}

.selector-actions {
  display: flex;
  justify-content: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--n-border-color, #e0e0e6);
}
</style>
