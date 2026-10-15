// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useReproducibleReport } from '@/composables/useReproducibleReport'
import type { ReportJob } from '@/types/report'

const calls = vi.hoisted(() => ({ create: vi.fn(), poll: vi.fn(), retry: vi.fn() }))
vi.mock('@/api/report', () => ({ reportApi: {
  createReproducibilityReport: calls.create,
  getReportJob: calls.poll,
  retryReportJob: calls.retry,
} }))

const job = (status: ReportJob['status'], extra: Partial<ReportJob> = {}): ReportJob => ({
  id: 'job-1', task_id: 'task-1', status, template_version: 'audit-v1.0.0',
  snapshot_id: null, report_id: null, error_message: '', error_code: null,
  retryable: false, evidence_partial: true, finished_at: null, attempt_count: 0,
  created_at: '', updated_at: '', ...extra,
})

const scopes: ReturnType<typeof effectScope>[] = []
function setup() {
  const scope = effectScope()
  scopes.push(scope)
  const ready = vi.fn()
  const taskId = ref('task-1')
  const report = scope.run(() => useReproducibleReport(taskId, ready))!
  return { report, ready, taskId, scope }
}
beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); sessionStorage.clear() })
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); vi.useRealTimers() })

describe('可复现报告交付', () => {
  it('一次点击自动轮询真实阶段并交付指定报告', async () => {
    calls.create.mockResolvedValue({ data: job('queued') })
    calls.poll.mockResolvedValueOnce({ data: job('publishing') })
      .mockResolvedValueOnce({ data: job('ready', { report_id: 'report-1' }) })
    const { report, ready } = setup()
    await report.generate()
    await report.generate()
    expect(calls.create).toHaveBeenCalledTimes(1)
    expect(report.statusText.value).toBe('等待报告生成')
    await vi.advanceTimersByTimeAsync(2000)
    expect(report.statusText.value).toBe('正在校验并归档报告')
    await vi.advanceTimersByTimeAsync(2000)
    expect(ready).toHaveBeenCalledWith(expect.objectContaining({ report_id: 'report-1', evidence_partial: true }))
    expect(report.generating.value).toBe(false)
    await vi.advanceTimersByTimeAsync(10000)
    expect(calls.poll).toHaveBeenCalledTimes(2)
  })
  it('查询短暂失败会继续轮询而不会再次生成', async () => {
    calls.create.mockResolvedValue({ data: job('collecting') })
    calls.poll.mockRejectedValueOnce(new Error('temporary'))
      .mockResolvedValueOnce({ data: job('ready', { report_id: 'report-1' }) })
    const { report, ready } = setup()
    await report.generate()
    await vi.advanceTimersByTimeAsync(2000)
    expect(report.error.value).toContain('自动重试')
    await vi.advanceTimersByTimeAsync(2000)
    expect(ready).toHaveBeenCalledTimes(1)
    expect(calls.create).toHaveBeenCalledTimes(1)
    expect(report.error.value).toBe('')
  })
  it('可重试失败复用同一快照 Job', async () => {
    calls.create.mockResolvedValue({ data: job('failed', { retryable: true, error_message: '文件暂不可用' }) })
    calls.retry.mockResolvedValue({ data: job('queued', { snapshot_id: 'snapshot-1' }) })
    const { report } = setup()
    await report.generate()
    expect(report.error.value).toBe('文件暂不可用')
    await report.generate()
    expect(calls.retry).toHaveBeenCalledWith('job-1')
    expect(calls.create).toHaveBeenCalledTimes(1)
  })
  it('离开页面不接收旧请求的完成回调', async () => {
    let resolve!: (result: { data: ReportJob }) => void
    calls.create.mockReturnValue(new Promise(r => { resolve = r }))
    const { report, ready, scope } = setup()
    const pending = report.generate()
    scope.stop()
    resolve({ data: job('ready', { report_id: 'report-1' }) })
    await pending
    expect(ready).not.toHaveBeenCalled()
    const before = calls.poll.mock.calls.length
    await vi.advanceTimersByTimeAsync(10000)
    expect(calls.poll).toHaveBeenCalledTimes(before)
  })
  it('重新打开任务页面可恢复后台 Job 轮询', async () => {
    sessionStorage.setItem('cygnusx:report-job:task-1', 'job-1')
    calls.poll.mockResolvedValue({ data: job('ready', { report_id: 'report-1' }) })
    const { ready } = setup()
    await Promise.resolve()
    await Promise.resolve()
    expect(calls.poll).toHaveBeenCalledWith('job-1')
    expect(ready).toHaveBeenCalledTimes(1)
    expect(calls.create).not.toHaveBeenCalled()
  })
  it('权限拒绝停止轮询并清理已保存的 Job', async () => {
    calls.create.mockResolvedValue({ data: job('queued') })
    calls.poll.mockRejectedValue({ response: { status: 404 } })
    const { report } = setup()
    await report.generate()
    await vi.advanceTimersByTimeAsync(2000)
    expect(report.generating.value).toBe(false)
    expect(report.error.value).toContain('无权查看')
    expect(sessionStorage.getItem('cygnusx:report-job:task-1')).toBeNull()
    const before = calls.poll.mock.calls.length
    await vi.advanceTimersByTimeAsync(10000)
    expect(calls.poll).toHaveBeenCalledTimes(before)
  })
})
