import { describe, expect, it } from 'vitest'
import { normalizeAgentStreamEvent } from '@/composables/useAgentChatStream'

describe('Agent SSE 事件归一化', () => {
  it.each([
    [{ type: 'text', content: 'content 字段' }, 'content 字段'],
    [{ event: 'delta', delta: 'delta 字段' }, 'delta 字段'],
    [{ type: 'message', text: 'text 字段' }, 'text 字段'],
    [{ type: 'done', answer: 'answer 字段' }, 'answer 字段'],
    [{ choices: [{ delta: { content: 'OpenAI delta' } }] }, 'OpenAI delta'],
    [{ data: { message: { content: '嵌套 message' } } }, '嵌套 message'],
  ])('兼容正文别名 %#', (raw, expected) => {
    expect(normalizeAgentStreamEvent(raw).content).toBe(expected)
  })

  it('将 reasoning_content 与正文分离', () => {
    const event = normalizeAgentStreamEvent({
      type: 'reasoning',
      delta: { reasoning_content: '推理内容' },
    })
    expect(event.reasoning).toBe('推理内容')
    expect(event.content).toBe('')
    expect(event.isReasoning).toBe(true)
  })
})
