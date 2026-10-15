import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import { reportApi } from '@/api/report'
import type { ReportJob } from '@/types/report'

const labels: Record<ReportJob['status'], string> = {
  queued: '等待报告生成',
  collecting: '正在采集执行证据',
  rendering: '正在渲染报告',
  publishing: '正在校验并归档报告',
  ready: '报告已归档',
  failed: '报告生成失败',
}

export function useReproducibleReport(taskId: Ref<string>, onReady: (job: ReportJob) => void) {
  const job = ref<ReportJob | null>(null)
  const generating = ref(false)
  const error = ref('')
  const statusText = computed(() => job.value ? labels[job.value.status] : '')
  let timer: ReturnType<typeof setTimeout> | null = null
  let epoch = 0
  let disposed = false
  const storageKey = () => `cygnusx:report-job:${taskId.value}`
  function stop() {
    if (timer) clearTimeout(timer)
    timer = null
  }
  function schedule(token: number) {
    stop()
    timer = setTimeout(() => { void poll(token) }, 2000)
  }
  function accept(next: ReportJob, token: number) {
    if (disposed || token !== epoch) return
    job.value = next
    if (next.status === 'ready' && next.report_id) {
      stop()
      generating.value = false
      sessionStorage.removeItem(storageKey())
      onReady(next)
    } else if (next.status === 'failed') {
      stop()
      generating.value = false
      error.value = next.error_message || '报告生成失败，请联系管理员。'
    } else {
      generating.value = true
      sessionStorage.setItem(storageKey(), next.id)
      schedule(token)
    }
  }
  async function poll(token: number) {
    if (!job.value || disposed || token !== epoch) return
    try {
      const response = await reportApi.getReportJob(job.value.id)
      if (token === epoch) error.value = ''
      accept(response.data, token)
    } catch (cause) {
      if (disposed || token !== epoch) return
      const status = (cause as { response?: { status?: number } }).response?.status
      if (status === 403 || status === 404) {
        stop()
        generating.value = false
        sessionStorage.removeItem(storageKey())
        error.value = '报告生成记录不存在或无权查看。'
      } else {
        error.value = '暂时无法查询状态，正在自动重试；报告仍在后台生成。'
        schedule(token)
      }
    }
  }
  async function generate() {
    if (generating.value || disposed) return
    const token = ++epoch
    error.value = ''
    generating.value = true
    try {
      const response = job.value?.status === 'failed' && job.value.retryable
        ? await reportApi.retryReportJob(job.value.id)
        : await reportApi.createReproducibilityReport(taskId.value)
      accept(response.data, token)
    } catch {
      if (token !== epoch || disposed) return
      generating.value = false
      error.value = '无法请求生成报告，请检查任务状态后重试。'
    }
  }
  watch(taskId, async () => {
    const token = ++epoch
    stop()
    job.value = null
    error.value = ''
    generating.value = false
    const id = sessionStorage.getItem(storageKey())
    if (id) {
      generating.value = true
      job.value = { id } as ReportJob
      await poll(token)
    }
  }, { immediate: true })
  onScopeDispose(() => { disposed = true; ++epoch; stop() })
  return { job, generating, error, statusText, generate }
}
