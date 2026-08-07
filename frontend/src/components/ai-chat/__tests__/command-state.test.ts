import { describe, expect, it } from 'vitest'
import { resolveStarCommandContext } from '../commandState'

describe('Star AI command context', () => {
  it('解析模式、权限和目标命令', () => {
    expect(resolveStarCommandContext('/plan /analysis /goal 设计 RNA-seq 流程', {
      mode: 'chat',
      permission: 'safe',
    })).toEqual({ mode: 'plan', permission: 'analysis', goal: '设计 RNA-seq 流程' })
  })

  it('手动输入未选择的命令也能覆盖默认状态', () => {
    expect(resolveStarCommandContext('请先 /research 再回答 /read', {
      mode: 'chat',
      permission: 'safe',
    })).toEqual({ mode: 'research', permission: 'read', goal: undefined })
  })

  it('没有命令时保留当前状态', () => {
    expect(resolveStarCommandContext('解释这个结果', {
      mode: 'plan',
      permission: 'analysis',
    })).toEqual({ mode: 'plan', permission: 'analysis', goal: undefined })
  })
})
