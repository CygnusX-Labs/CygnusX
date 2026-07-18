<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NSpin,
  NTag,
  NSpace,
  NTooltip,
  NIcon,
  NEmpty,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  ArrowBackOutline,
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
const terminalEnabled = computed(() => store.terminalEnabled)

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

const selectedImageLabel = computed(() => {
  if (!selectedImage.value) return '未选择'
  return `${selectedImage.value.icon} ${selectedImage.value.name}`
})

const preinstalledToolCount = computed(() => {
  const desc = selectedImage.value?.description ?? ''
  const tools = desc
    .split(/[、，,]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return Math.max(tools.length, selectedImage.value?.tags.length ?? 0)
})

const imageSizeGb = computed(() => {
  if (!selectedImage.value) return '0.0'
  const memoryFactor = selectedImage.value.resources.memory_mb / 1024
  const toolFactor = preinstalledToolCount.value * 0.03
  const estimate = Math.max(1.2, Math.min(4.8, 0.75 + memoryFactor * 0.55 + toolFactor))
  return estimate.toFixed(1)
})

const estimatedStartupSeconds = computed(() => {
  if (!selectedImage.value) return 0
  return Math.max(3, Math.min(9, Math.ceil(2 + memoryMb.value / 2048 + cpuCores.value / 4)))
})

const mountDirectory = computed(() => '/home/omichub/workspace')

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
  if (!terminalEnabled.value) {
    message.warning('云端沙盒终端已关闭')
    return
  }
  if (!selectedImage.value) {
    message.warning('请先选择一个镜像')
    return
  }
  try {
    await store.createSession()
    message.success('沙盒终端已启动')
    startCountdown()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || e?.message || '启动沙盒终端失败')
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
  <div class="terminal-page" :class="{ 'terminal-fullscreen': fullScreen }" role="main" aria-label="云端沙盒终端">
    <div v-if="session" class="terminal-header session-header">
      <div class="header-left">
        <NIcon :size="20" color="#2e5bff">
          <TerminalOutline />
        </NIcon>
        <span class="header-title">云端沙盒终端</span>
        <NTag :type="statusType" size="small" round role="status" aria-live="polite">
          {{ session.status }}
        </NTag>
        <span class="session-id">{{ session.session_id }}</span>
        <span v-if="session.image_name" class="image-name">{{ session.image_name }}</span>
      </div>
      <div class="header-right">
        <NSpace align="center" :size="8">
          <NIcon :size="14" color="#6b7280">
            <TimeOutline />
          </NIcon>
          <span class="remaining-time">{{ remainingMinutes }}分钟</span>
        </NSpace>
        <NButton quaternary size="small" @click="fullScreen = !fullScreen">
          <template #icon>
            <NIcon>
              <ContractOutline v-if="fullScreen" />
              <ExpandOutline v-else />
            </NIcon>
          </template>
        </NButton>
        <NButton type="error" size="small" quaternary @click="handleDestroy">
          <template #icon>
            <NIcon>
              <TrashOutline />
            </NIcon>
          </template>
        </NButton>
      </div>
    </div>

    <div v-else class="page-header">
      <NTooltip placement="bottom" :delay="300">
        <template #trigger>
          <NButton circle secondary size="large" class="back-button" aria-label="返回工具箱" @click="router.push('/tools')">
            <template #icon><NIcon :size="22"><ArrowBackOutline /></NIcon></template>
          </NButton>
        </template>
        返回工具箱
      </NTooltip>
      <div class="page-title-group">
        <h1 class="page-title">云端沙盒终端</h1>
        <p class="page-subtitle">选择预装工具链的镜像，启动一个隔离、用完即毁的沙盒终端</p>
      </div>
    </div>

    <div class="terminal-body">
      <div v-if="loading" class="terminal-loading">
        <NSpin size="large" />
        <p class="loading-text">正在启动隔离容器...</p>
        <p v-if="selectedImage" class="loading-desc">镜像：{{ selectedImage.name }}</p>
      </div>

      <div v-else-if="session?.ws_url" class="terminal-content">
        <XTerminal :session-id="session.session_id" />
      </div>

      <div v-else class="terminal-selector">
        <div class="main-layout">
          <aside class="left-column">
            <section class="config-card">
              <div class="card-heading">
                <h2>选择分析环境</h2>
                <p>点击镜像卡片切换预装工具链</p>
              </div>
              <ImageSelector v-model="store.selectedImageId" :images="images" />
              <NEmpty
                v-if="images.length === 0 && !loading"
                class="empty-state"
                description="暂无可用镜像，请联系管理员配置 terminal_images.yaml"
              />
            </section>

            <section class="config-card">
              <div class="card-heading">
                <h2>资源设置</h2>
                <p>资源调整会实时同步到右侧启动预览</p>
              </div>
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
            </section>
          </aside>

          <main class="right-column">
            <div class="stats-row">
              <div class="stat-card">
                <span class="stat-label">镜像大小</span>
                <span class="stat-value">{{ imageSizeGb }}<span class="stat-unit">GB</span></span>
              </div>
              <div class="stat-card">
                <span class="stat-label">预装工具</span>
                <span class="stat-value">{{ preinstalledToolCount }}<span class="stat-unit">个</span></span>
              </div>
              <div class="stat-card">
                <span class="stat-label">预计启动</span>
                <span class="stat-value">{{ estimatedStartupSeconds }}<span class="stat-unit">秒</span></span>
              </div>
            </div>

            <section class="preview-panel">
              <div class="preview-title">
                <NIcon :size="18">
                  <TerminalOutline />
                </NIcon>
                启动配置预览
              </div>

              <div class="preview-row">
                <span class="preview-key">分析镜像</span>
                <span class="preview-val">{{ selectedImageLabel }}</span>
              </div>
              <div class="preview-row">
                <span class="preview-key">分配内存</span>
                <span class="preview-val">{{ memoryMb }} MB</span>
              </div>
              <div class="preview-row">
                <span class="preview-key">分配 CPU</span>
                <span class="preview-val">{{ cpuCores }} 核</span>
              </div>
              <div class="preview-row">
                <span class="preview-key">挂载目录</span>
                <span class="preview-val monospace">{{ mountDirectory }}</span>
              </div>
              <div class="preview-row">
                <span class="preview-key">网络模式</span>
                <span class="preview-val">隔离桥接网络</span>
              </div>
              <div class="preview-row">
                <span class="preview-key">生命周期</span>
                <span class="preview-val danger">用完即毁</span>
              </div>

              <NButton
                type="primary"
                size="large"
                block
                class="launch-button"
                :disabled="!selectedImage || !terminalEnabled"
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
            </section>
          </main>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.terminal-page {
  --terminal-bg: #f5f6fa;
  --terminal-card: #fff;
  --terminal-primary: #2e5bff;
  --terminal-primary-light: #e8eeff;
  --terminal-text: #1f2937;
  --terminal-subtext: #6b7280;
  --terminal-border: #e5e7eb;
  --terminal-soft-border: #f3f4f6;
  --terminal-shadow: 0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--terminal-bg);
}

.terminal-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: #1e1e1e;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px 0;
  flex-shrink: 0;
}

.back-button {
  height: 36px;
  border-radius: 8px;
}

:deep(.back-button:hover) {
  color: var(--terminal-primary);
  border-color: #c7d2fe;
  background: var(--terminal-primary-light);
}

.page-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.page-title {
  margin: 0;
  color: var(--terminal-text);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0;
}

.page-subtitle {
  margin: 0;
  color: var(--terminal-subtext);
  font-size: 13px;
  line-height: 1.45;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--terminal-border);
  background: #fff;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.header-title {
  color: var(--terminal-text);
  font-size: 15px;
  font-weight: 600;
}

.session-id {
  color: var(--terminal-subtext);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.image-name {
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--terminal-primary-light);
  color: var(--terminal-primary);
  font-size: 12px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.remaining-time {
  color: var(--terminal-subtext);
  font-size: 12px;
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
  margin: 0;
  color: var(--terminal-subtext);
  font-size: 14px;
}

.loading-desc {
  margin: 0;
  color: var(--terminal-subtext);
  font-size: 12px;
}

.terminal-selector {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 20px;
}

.main-layout {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.left-column,
.right-column {
  min-width: 0;
}

.left-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.right-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-card,
.preview-panel,
.stat-card {
  background: var(--terminal-card);
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  box-shadow: var(--terminal-shadow);
}

.config-card {
  padding: 20px;
}

.card-heading {
  margin-bottom: 16px;
}

.card-heading h2 {
  margin: 0;
  color: var(--terminal-text);
  font-size: 15px;
  font-weight: 700;
}

.card-heading p {
  margin: 5px 0 0;
  color: var(--terminal-subtext);
  font-size: 12px;
  line-height: 1.45;
}

.empty-state {
  margin-top: 16px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 104px;
  padding: 20px;
}

.stat-label {
  color: var(--terminal-subtext);
  font-size: 12px;
}

.stat-value {
  color: var(--terminal-text);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.stat-unit {
  margin-left: 2px;
  color: var(--terminal-subtext);
  font-size: 14px;
  font-weight: 500;
}

.preview-panel {
  padding: 24px;
}

.preview-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  color: var(--terminal-text);
  font-size: 15px;
  font-weight: 700;
}

.preview-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 46px;
  padding: 12px 0;
  border-bottom: 1px solid var(--terminal-soft-border);
}

.preview-key {
  flex: 0 0 auto;
  color: var(--terminal-subtext);
  font-size: 13px;
}

.preview-val {
  min-width: 0;
  color: var(--terminal-text);
  font-size: 13px;
  font-weight: 700;
  text-align: right;
  word-break: break-word;
}

.preview-val.monospace {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.preview-val.danger {
  color: #dc2626;
}

.launch-button {
  height: 48px;
  margin-top: 20px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(46, 91, 255, 0.25);
}

:deep(.launch-button.n-button--disabled) {
  box-shadow: none;
}

@media (max-width: 900px) {
  .page-header {
    align-items: flex-start;
    padding: 14px 16px 0;
  }

  .terminal-selector {
    padding: 16px;
  }

  .main-layout {
    grid-template-columns: 1fr;
  }

  .right-column {
    order: 1;
  }

  .left-column {
    order: 2;
  }

  .stats-row {
    grid-template-columns: 1fr;
  }
}
</style>
