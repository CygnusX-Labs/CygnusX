// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Announcement } from '@/types/announcement'
import AnnouncementBanner from '../AnnouncementBanner.vue'

const api = vi.hoisted(() => ({ getActive: vi.fn(), getAiTokenRate: vi.fn() }))
vi.mock('@/api/announcements', () => ({ announcementApi: { getActive: api.getActive } }))
vi.mock('@/api/cookies', () => ({ cookieApi: { getAiTokenRate: api.getAiTokenRate } }))

const announcement: Announcement = {
  id: 'rna-atac-ready',
  title: 'RNA-seq / ATAC-seq 分析已就绪',
  description: '选择分析流程，开始研究',
  type: 'feature',
  link: '/flows',
  button_text: '开始分析',
  dismiss_behavior: 'daily',
  start_time: '2026-10-01T00:00:00Z',
  priority: 1,
  is_enabled: true,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

let app: ReturnType<typeof createApp> | undefined
let host: HTMLDivElement | undefined
function unmount() {
  app?.unmount()
  host?.remove()
}
async function mount(rememberDismissal = true) {
  unmount()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/flows'].map(path => ({ path, component: { render: () => h('div') } })),
  })
  await router.push('/')
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(AnnouncementBanner, { rememberDismissal }) })
  app.use(router)
  app.mount(host)
  for (let i = 0; i < 8; i++) {
    await Promise.resolve()
    await nextTick()
  }
  return { page: host, router }
}
function close(page: HTMLDivElement) {
  page.querySelector<HTMLButtonElement>('.banner-close')!.click()
}

beforeEach(() => {
  localStorage.clear()
  api.getActive.mockResolvedValue([{ ...announcement }])
  api.getAiTokenRate.mockResolvedValue({})
})
afterEach(() => {
  unmount()
  app = undefined
  host = undefined
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('homepage announcement dismissal', () => {
  it('persists across remounts and days, and reappears when content changes', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-21T12:00:00Z'))
    close((await mount()).page)
    expect(localStorage.length).toBe(1)
    expect((await mount()).page.querySelector('.announcement-banner')).toBeNull()
    vi.setSystemTime(new Date('2026-10-22T12:00:00Z'))
    expect((await mount()).page.querySelector('.announcement-banner')).toBeNull()
    api.getActive.mockResolvedValue([{ ...announcement, description: '新增分析能力' }])
    expect((await mount()).page.textContent).toContain('新增分析能力')
  })

  it('ignores regenerated timestamps and shows a new announcement ID', async () => {
    close((await mount()).page)
    api.getActive.mockResolvedValue([{ ...announcement, updated_at: new Date().toISOString() }])
    expect((await mount()).page.querySelector('.announcement-banner')).toBeNull()
    api.getActive.mockResolvedValue([{ ...announcement, id: 'rna-atac-ready-v2' }])
    expect((await mount()).page.querySelector('.announcement-banner')).not.toBeNull()
  })

  it('preserves daily and non-dismissible policies outside the homepage override', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-21T12:00:00Z'))
    close((await mount(false)).page)
    expect((await mount(false)).page.querySelector('.announcement-banner')).toBeNull()
    vi.setSystemTime(new Date('2026-10-22T12:00:00Z'))
    expect((await mount(false)).page.querySelector('.announcement-banner')).not.toBeNull()
    api.getActive.mockResolvedValue([{ ...announcement, dismiss_behavior: 'none' }])
    expect((await mount()).page.querySelector('.banner-close')).toBeNull()
  })

  it('keeps the action destination and still closes when storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    const { page, router } = await mount()
    page.querySelector<HTMLButtonElement>('.banner-btn')!.click()
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/flows'))
    close(page)
    await nextTick()
    await vi.waitFor(() => expect(page.querySelector('.announcement-banner')).toBeNull())
  })
})
