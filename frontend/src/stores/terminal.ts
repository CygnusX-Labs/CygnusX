import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  TerminalSession,
  CreateTerminalRequest,
  TerminalImage,
  TerminalResources,
} from '@/types/terminal'
import {
  createTerminalSession,
  listTerminalSessions,
  deleteTerminalSession,
  listTerminalImages,
} from '@/api/terminal'

const DEFAULT_MIN_MEMORY_MB = 256
const DEFAULT_MAX_MEMORY_MB = 4096
const DEFAULT_MIN_CPU_CORES = 0.5
const DEFAULT_MAX_CPU_CORES = 4.0

export const useTerminalStore = defineStore('terminal', () => {
  const sessions = ref<TerminalSession[]>([])
  const currentSession = ref<TerminalSession | null>(null)
  const images = ref<TerminalImage[]>([])
  const selectedImageId = ref<string | null>(null)
  const customMemoryMb = ref<number | null>(null)
  const customCpuCores = ref<number | null>(null)
  const loading = ref(false)

  const enabledImages = computed(() => images.value.filter((img) => img.enabled))
  const selectedImage = computed(() =>
    enabledImages.value.find((img) => img.id === selectedImageId.value),
  )

  const memoryRange = computed(() => ({
    min: selectedImage.value?.resources.memory_mb
      ? Math.min(selectedImage.value.resources.memory_mb, DEFAULT_MIN_MEMORY_MB)
      : DEFAULT_MIN_MEMORY_MB,
    max: DEFAULT_MAX_MEMORY_MB,
    step: 128,
  }))

  const cpuRange = computed(() => ({
    min: selectedImage.value?.resources.cpu_cores
      ? Math.min(selectedImage.value.resources.cpu_cores, DEFAULT_MIN_CPU_CORES)
      : DEFAULT_MIN_CPU_CORES,
    max: DEFAULT_MAX_CPU_CORES,
    step: 0.5,
  }))

  const effectiveMemoryMb = computed(() => customMemoryMb.value ?? selectedImage.value?.resources.memory_mb ?? 512)
  const effectiveCpuCores = computed(() => customCpuCores.value ?? selectedImage.value?.resources.cpu_cores ?? 1.0)

  function resetCustomResources() {
    customMemoryMb.value = null
    customCpuCores.value = null
  }

  async function fetchSessions() {
    try {
      sessions.value = await listTerminalSessions()
    } catch {
      sessions.value = []
    }
  }

  async function fetchImages() {
    try {
      images.value = await listTerminalImages()
      // 默认选中第一个启用镜像，或保持当前选择
      if (!selectedImageId.value || !enabledImages.value.some((img) => img.id === selectedImageId.value)) {
        selectedImageId.value = enabledImages.value[0]?.id ?? null
      }
    } catch {
      images.value = []
      selectedImageId.value = null
    }
  }

  async function createSession(req?: CreateTerminalRequest) {
    loading.value = true
    try {
      const request: CreateTerminalRequest = { ...req }
      if (selectedImageId.value) {
        request.image_id = selectedImageId.value
      }
      const resources: Partial<TerminalResources> = {}
      if (customMemoryMb.value != null) {
        resources.memory_mb = customMemoryMb.value
      }
      if (customCpuCores.value != null) {
        resources.cpu_cores = customCpuCores.value
      }
      if (Object.keys(resources).length > 0) {
        request.resources = resources
      }
      const session = await createTerminalSession(request)
      currentSession.value = session
      sessions.value.push(session)
      return session
    } finally {
      loading.value = false
    }
  }

  async function destroySession(sessionId: string) {
    try {
      await deleteTerminalSession(sessionId)
    } finally {
      if (currentSession.value?.session_id === sessionId) {
        currentSession.value = null
      }
      sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    }
  }

  return {
    sessions,
    currentSession,
    images,
    selectedImageId,
    customMemoryMb,
    customCpuCores,
    loading,
    enabledImages,
    selectedImage,
    memoryRange,
    cpuRange,
    effectiveMemoryMb,
    effectiveCpuCores,
    resetCustomResources,
    fetchSessions,
    fetchImages,
    createSession,
    destroySession,
  }
})
