// @vitest-environment jsdom
/**
 * 复现「回复后正文/tokens 不显示，刷新后才出现」的前端 bug。
 *
 * 现有测试都是「按目标状态新鲜挂载」，无法捕获真实浏览器里
 * 同一个 KimiMessageItem 实例从 streaming → done 的活体切换。
 * 这里让同一实例经历：
 *   1. 流式中：isStreaming=true, streamingContent 增长, message.content=''
 *   2. 结束：isStreaming=false, message.content=最终正文, streamingContent 复位为 ''
 * 并断言切换后 DOM 立即出现正文与 tokens（无需刷新/重挂载）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createApp, h, nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue3-lottie', () => ({
  Vue3Lottie: { template: '<div />', methods: { setSpeed() {} } },
}))
vi.mock('vue-echarts', () => ({ default: { template: '<div />' } }))

import KimiMessageItem from '@/components/ai-chat/KimiMessageItem.vue'
import type { ChatMessage } from '@/components/ai-chat/types'

beforeEach(() => {
  global.requestAnimationFrame = ((cb: FrameRequestCallback) => { cb(0); return 0 }) as typeof requestAnimationFrame
  global.cancelAnimationFrame = (() => {}) as typeof cancelAnimationFrame
  setActivePinia(createPinia())
})

describe('KimiMessageItem 活体 streaming→done 切换', () => {
  it('同一实例流式结束后，正文与 tokens 立即渲染（无需刷新）', async () => {
    const message = reactive<ChatMessage>({
      id: 'msg-ai-1',
      role: 'assistant',
      content: '',
      thought: '',
      status: 'streaming',
      createdAt: new Date().toISOString(),
      tokens: { input: 0, output: 0, total: 0 },
    })
    const props = reactive({
      message,
      isStreaming: true,
      streamingContent: '',
      streamingThought: '',
    })

    const el = document.createElement('div')
    document.body.appendChild(el)
    const app = createApp({ render() { return h(KimiMessageItem, props as never) } })
    app.mount(el)
    await nextTick()

    // 1. 流式中：先来思考，再来正文（模拟真实事件顺序）
    props.streamingThought = '用户打招呼，应友好回应'
    await nextTick()
    props.streamingContent = '你好！我是'
    await nextTick()
    props.streamingContent = '你好！我是 OmicHub AI 助手。'
    await nextTick()
    expect(el.textContent).toContain('你好')

    // 2. 结束（store.onDone 的等效动作）：写回 message，复位 streaming 态
    message.content = '你好！我是 OmicHub AI 助手。'
    message.thought = '用户打招呼，应友好回应'
    message.status = 'complete'
    message.tokens = { input: 4208, output: 321, total: 4529 }
    props.isStreaming = false
    props.streamingContent = ''
    props.streamingThought = ''
    await nextTick()

    // 刷新前就应可见正文与 token
    expect(el.textContent).toContain('你好！我是 OmicHub AI 助手。')
    expect(el.textContent).toContain('Tokens:')
  })
})
