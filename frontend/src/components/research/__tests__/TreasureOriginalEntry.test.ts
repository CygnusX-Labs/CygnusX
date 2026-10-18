// @vitest-environment jsdom
import { createApp } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import TreasureMouseView from '@/views/TreasureMouseView.vue'

vi.mock('@/views/TreasureResearchWorkbench.vue', () => ({ default: { template: '<div>平台工作台</div>' } }))

describe('native treasure entry', () => {
  it('renders the native workbench without a legacy application entry', () => {
    const host = document.createElement('div')
    const app = createApp(TreasureMouseView)
    app.mount(host)
    try {
      expect(host.querySelector('iframe')).toBeNull()
      expect(host.querySelector('a[href*="treasure-mouse"]')).toBeNull()
      expect(host.textContent).toContain('平台工作台')
    } finally { app.unmount() }
  })
})
