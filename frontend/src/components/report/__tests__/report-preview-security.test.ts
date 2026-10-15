// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { NMessageProvider } from 'naive-ui'
import ReportPreviewModal from '@/components/report/ReportPreviewModal.vue'
import type { Report } from '@/types/report'

const calls = vi.hoisted(() => ({ preview: vi.fn(), download: vi.fn() }))
vi.mock('@/api/report', () => ({ reportApi: { previewReport: calls.preview }, downloadReportFile: calls.download }))
const report = { id: 'report-1', title: '证据报告', report_kind: 'reproducibility',
  evidence_partial: true, version: 1, template_version: 'audit-v1.0.0', files: [] } as unknown as Report

describe('HTML 预览隔离', () => {
  it('恶意脚本只进入空 sandbox 的 opaque origin iframe', async () => {
    const payload = '<script>parent.localStorage.getItem("token")</script>'
    calls.preview.mockResolvedValue({ data: payload })
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp({ render: () => h(NMessageProvider, null, {
      default: () => h(ReportPreviewModal, { report }),
    }) })
    app.mount(host)
    try {
      await Promise.resolve()
      await nextTick()
      const iframe = document.querySelector('iframe')!
      expect(iframe).not.toBeNull()
      expect(iframe.getAttribute('sandbox')).toBe('')
      expect(iframe.getAttribute('srcdoc')).toBe(payload)
      expect(host.querySelector('script')).toBeNull()
      expect(document.body.textContent).toContain('not_run')
    } finally { app.unmount(); host.remove() }
  })
})
