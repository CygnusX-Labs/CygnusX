// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, type App } from 'vue'
import DownloadsView from '../DownloadsView.vue'
import apiClient from '@/api/client'

vi.mock('@/api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/PageHeader.vue', () => ({ default: { template: '<div />' } }))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  const container = defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    NAlert: container, NTabs: container, NTabPane: container, NIcon: container,
    NPopconfirm: container, NSpin: container,
    NSelect: defineComponent({ props: ['options'], setup: p => () => h('div', { 'data-options': JSON.stringify(p.options) }) }),
    NButton: defineComponent({ props: ['disabled', 'type'], setup: (p, { slots }) => () => h('button', { disabled: p.disabled, 'data-type': p.type }, slots.default?.()) }),
    useMessage: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  }
})

let app: App | undefined
let root: HTMLDivElement

afterEach(() => { app?.unmount(); root?.remove(); vi.clearAllMocks() })

describe('server-owned download capabilities', () => {
  it('uses server method choices and keeps unaccepted execution disabled', async () => {
    vi.mocked(apiClient.get).mockImplementation(async url => ({ data: url === '/downloads/capabilities'
      ? { sources: [{ source_type: 'sra', supported_methods: ['ftp'] }], write_enabled: false }
      : { items: [] } }) as never)
    root = document.createElement('div'); document.body.append(root)
    app = createApp(DownloadsView); app.mount(root)
    await vi.waitFor(() => expect([...root.querySelectorAll('[data-options]')].some(el =>
      el.getAttribute('data-options') === '[{"label":"FTP","value":"ftp"}]')).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/downloads/capabilities')
    expect([...root.querySelectorAll<HTMLButtonElement>('button[data-type="primary"]')].every(button => button.disabled)).toBe(true)
    expect(root.textContent).toContain('暂不开放执行')
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('fails closed when capability lookup fails', async () => {
    vi.mocked(apiClient.get).mockImplementation(async url => {
      if (url === '/downloads/capabilities') throw new Error('unavailable')
      return { data: { items: [] } } as never
    })
    root = document.createElement('div'); document.body.append(root)
    app = createApp(DownloadsView); app.mount(root)
    await vi.waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/downloads/capabilities'))
    expect(root.querySelector('button[data-type="primary"]')?.hasAttribute('disabled')).toBe(true)
    expect(apiClient.post).not.toHaveBeenCalled()
  })
})
