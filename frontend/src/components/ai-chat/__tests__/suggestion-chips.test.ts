// @vitest-environment jsdom
import { createApp, h, nextTick, reactive } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SuggestionChips from '../SuggestionChips.vue'
import type { SuggestedFollowUp } from '@/utils/nextStepSuggestions'

const suggestions: SuggestedFollowUp[] = Array.from({ length: 6 }, (_, i) => ({
  label: i === 0 ? '探索 TP53 & β-catenin 数据集 <证据>' : `补充文献证据 ${i}`,
  prompt: `完整科研指令 ${i}：保留项目上下文、筛选条件以及所有变异证据。`,
  action: i === 1 ? 'prefill' : 'send',
}))
const cleanups: (() => void)[] = []
afterEach(() => { cleanups.splice(0).forEach((fn) => fn()) })
function mount(items = suggestions, disabled = false) {
  const props = reactive({ suggestions: items, disabled })
  const send = vi.fn(), prefill = vi.fn()
  const el = document.createElement('div')
  document.body.append(el)
  const app = createApp({ render: () => h(SuggestionChips, { ...props, onSend: send, onPrefill: prefill }) })
  app.mount(el)
  cleanups.push(() => { app.unmount(); el.remove() })
  return { el, props, send, prefill }
}

describe('SuggestionChips', () => {
  it.each([0, 1, 2, 4, 6])('展示 %i 条传入建议，空时没有占位', (count) => {
    const { el } = mount(suggestions.slice(0, count))
    expect(el.querySelectorAll('button')).toHaveLength(count)
    expect(el.textContent?.includes('你可以继续')).toBe(count > 0)
    expect(el.textContent).not.toContain('Enter')
  })
  it('显示完整混排标题，发送完整 prompt，保留 prefill 行为', async () => {
    const { el, send, prefill } = mount()
    const buttons = el.querySelectorAll('button')
    expect(buttons[0].textContent).toContain(suggestions[0].label)
    expect(buttons[0].getAttribute('aria-label')).toContain(suggestions[0].prompt)
    buttons[0].click()
    await nextTick()
    await nextTick()
    buttons[1].click()
    expect(send.mock.calls).toEqual([[suggestions[0].prompt]])
    expect(prefill.mock.calls).toEqual([[suggestions[1].prompt]])
  })
  it('阻止同帧重复提交，父级 busy 禁用所有交互，解除后可继续', async () => {
    const { el, props, send } = mount()
    const buttons = el.querySelectorAll('button')
    buttons[0].click()
    buttons[2].click()
    expect(send).toHaveBeenCalledTimes(1)
    props.disabled = true
    await nextTick()
    expect([...buttons].every((b) => b.disabled)).toBe(true)
    buttons[0].click()
    expect(send).toHaveBeenCalledTimes(1)
    props.disabled = false
    await nextTick()
    buttons[0].click()
    expect(send).toHaveBeenCalledTimes(2)
  })
})
