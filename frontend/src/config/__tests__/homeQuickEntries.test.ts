// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import router from '@/router'
import {
  defaultHomeQuickEntries,
  normalizeHomeQuickEntries,
} from '../homeQuickEntries'

describe('home quick entries', () => {
  it('keeps the six research destinations in the product order', () => {
    expect(defaultHomeQuickEntries.map(({ key, to }) => [key, to])).toEqual([
      ['treasure-mouse', '/treasure-mouse'],
      ['files', '/files'],
      ['flows', '/flows'],
      ['ai', '/ai'],
      ['tasks', '/tasks'],
      ['reports', '/reports'],
    ])
  })

  it('normalizes content-only entries to valid internal routes', () => {
    const normalized = normalizeHomeQuickEntries([
      { key: 'treasure-mouse', title: '科研寻宝鼠', desc: '探索' },
      { key: 'files', title: '科研数据管理', desc: '导入' },
      { key: 'flows', title: '多组学分析', desc: '计算' },
      { key: 'ai', title: '星尘 AI 助手', desc: '规划' },
      { key: 'tasks', title: '计算任务中心', desc: '执行' },
      { key: 'reports', title: '报告与证据', desc: '交付' },
    ])

    expect(normalized).toHaveLength(6)
    expect(normalized.every(({ to }) => to.startsWith('/') && !to.startsWith('//'))).toBe(true)
  })

  it('resolves every homepage destination through the application router', () => {
    for (const entry of defaultHomeQuickEntries) {
      expect(router.resolve(entry.to).matched.length, entry.to).toBeGreaterThan(0)
    }
  })
})
