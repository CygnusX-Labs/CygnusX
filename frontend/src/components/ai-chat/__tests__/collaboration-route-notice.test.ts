// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { createApp, h } from 'vue'
import { NMessageProvider } from 'naive-ui'
import CollaborationRouteNotice from '../CollaborationRouteNotice.vue'
import type { CollaborationRouteInfo } from '../types'

function mountNotice(route: CollaborationRouteInfo) {
  const el = document.createElement('div')
  document.body.appendChild(el)
  createApp({
    render: () => h(NMessageProvider, null, {
      default: () => h(CollaborationRouteNotice, { route }),
    }),
  }).mount(el)
  return el
}

describe('CollaborationRouteNotice', () => {
  it('hides internal clarification phrasing for direct-answer routes', () => {
    const el = mountNotice({
      intent: 'chat',
      label: '直接回答',
      reason: '用户问题缺乏上下文和具体领域信息，需要通用助手先进行追问以补全上下文。',
      confidence: 0.9,
      available: true,
      degraded: false,
      message: '',
    })

    expect(el.textContent).toContain('当前助手将直接处理你的问题。')
    expect(el.textContent).not.toContain('缺乏上下文')
  })
})
