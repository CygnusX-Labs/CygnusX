// @vitest-environment jsdom
import { createApp } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import TreasureMouseView from '@/views/TreasureMouseView.vue'

vi.mock('@/views/TreasureResearchWorkbench.vue', () => ({ default: { template: '<div>平台工作台</div>' } }))

describe('original treasure entry', () => {
  it('opens the original app without requiring the native research API', () => {
    const host = document.createElement('div')
    const app = createApp(TreasureMouseView)
    app.mount(host)
    try {
      expect(host.querySelector('iframe')?.getAttribute('src')).toBe('/treasure-mouse/')
      expect(host.querySelector('button')?.getAttribute('aria-pressed')).toBe('true')
      expect(host.textContent).not.toContain('平台工作台')
    } finally { app.unmount() }
  })
})
