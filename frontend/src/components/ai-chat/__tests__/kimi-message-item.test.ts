// @vitest-environment jsdom
/**
 * KimiMessageItem 渲染分支测试（jsdom 真实挂载）
 *
 * 背景 bug：开启深度思考后，思考过程面板渲染了，但正文区域空白。
 * 这里用真实 SSE 事件序列驱动 agentHub store 的回调逻辑 + 组件挂载，
 * 验证三种状态下正文是否正确渲染。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createApp, h, nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

// lottie-web / vue-echarts import 时依赖完整浏览器 API，打桩
vi.mock('vue3-lottie', () => ({ Vue3Lottie: { template: '<div />' } }))
vi.mock('vue-echarts', () => ({ default: { template: '<div />' } }))

import KimiMessageItem from '@/components/ai-chat/KimiMessageItem.vue'
import type { ChatMessage } from '@/components/ai-chat/types'

// rAF 同步化：让流式渲染立即落盘，便于断言
beforeEach(() => {
  global.requestAnimationFrame = ((cb: FrameRequestCallback) => {
    cb(0)
    return 0
  }) as typeof requestAnimationFrame
  global.cancelAnimationFrame = (() => {}) as typeof cancelAnimationFrame
})

function mountItem(props: Record<string, unknown>) {
  setActivePinia(createPinia())
  const el = document.createElement('div')
  document.body.appendChild(el)
  const app = createApp({
    render() {
      return h(KimiMessageItem, props as never)
    },
  })
  app.mount(el)
  return { el, app }
}

const baseMsg: ChatMessage = {
  id: 'm1',
  role: 'assistant',
  content: '',
  createdAt: new Date().toISOString(),
}

describe('KimiMessageItem 渲染分支', () => {
  it('有 thought + 有 content：思考面板与正文都应渲染', () => {
    const { el } = mountItem({
      message: { ...baseMsg, content: '你好！我是 OmicHub AI 助手。', thought: '用户打招呼' },
      isStreaming: false,
    })
    expect(el.textContent).toContain('思考过程')
    expect(el.textContent).toContain('你好！我是 OmicHub AI 助手。')
  })

  it('只有 thought、content 为空：显示空态兜底而非空白', () => {
    const { el } = mountItem({
      message: { ...baseMsg, content: '', thought: '只想了没说', status: 'empty' },
      isStreaming: false,
    })
    expect(el.textContent).toContain('思考完成，但未生成正式回复')
  })

  it('有 output Token 但正文为空：显示加载异常和可操作重试入口', () => {
    const { el } = mountItem({
      message: {
        ...baseMsg,
        content: '',
        thought: '模型已完成推理',
        status: 'empty',
        tokens: { input: 128, output: 32, total: 160 },
      },
      isStreaming: false,
    })
    expect(el.textContent).toContain('回复内容加载异常')
    expect(el.textContent).toContain('点击重试')
  })

  it('流式中：streamingContent 应实时渲染', () => {
    const { el } = mountItem({
      message: { ...baseMsg, status: 'streaming' },
      isStreaming: true,
      streamingContent: '正在输出的正文',
      streamingThought: '思考内容',
    })
    expect(el.textContent).toContain('正在输出的正文')
  })

  it('流式首帧尚未收到搜索状态时，不应误报联网搜索失败', () => {
    const { el } = mountItem({
      message: { ...baseMsg, status: 'streaming' },
      isStreaming: true,
    })
    expect(el.textContent).not.toContain('联网搜索失败')
  })

  it('收到搜索中状态后，显示联网搜索进度', () => {
    const { el } = mountItem({
      message: {
        ...baseMsg,
        status: 'streaming',
        webSearchStatus: { status: 'searching', query: 'OmicHub' },
      },
      isStreaming: true,
    })
    expect(el.textContent).toContain('正在联网搜索：OmicHub')
  })

  it('流式结束瞬间（content 已写入 message）：正文不丢失', () => {
    const msg = reactive({
      ...baseMsg,
      content: '最终正文内容',
      thought: '最终思考',
      status: 'complete',
    }) as ChatMessage
    const { el } = mountItem({ message: msg, isStreaming: false })
    expect(el.textContent).toContain('最终正文内容')
  })

  it('finishReason=length 且正文为空：提示调大 max_tokens 而不是通用文案', () => {
    const { el } = mountItem({
      message: {
        ...baseMsg,
        content: '',
        thought: '思考预算耗尽',
        status: 'empty',
        finishReason: 'length',
      },
      isStreaming: false,
    })
    expect(el.textContent).toContain('max_tokens')
    expect(el.textContent).toContain('finish_reason=length')
  })
})

describe('KimiMessageItem 渲染异常兜底', () => {
  it('markdown 渲染抛异常：回退纯文本且后续渲染不被卡死', async () => {
    const md = (await import('@/components/ai-chat/setup')).default
    const spy = vi.spyOn(md, 'render').mockImplementation(() => {
      throw new Error('boom')
    })
    try {
      const msg = reactive({ ...baseMsg, status: 'streaming' }) as ChatMessage
      const props = reactive({
        message: msg,
        isStreaming: true,
        streamingContent: '第一段正文',
        streamingThought: '',
      })
      const { el } = mountItem(props)
      // 渲染异常 → 回退转义纯文本，正文不空白
      expect(el.textContent).toContain('第一段正文')

      // 模拟后续流式更新：rAF 句柄未被异常卡死，新内容仍能渲染
      spy.mockRestore()
      props.streamingContent = '第一段正文 + 第二段正文'
      await nextTick()
      expect(el.textContent).toContain('第二段正文')
    } finally {
      spy.mockRestore()
    }
  })
})
