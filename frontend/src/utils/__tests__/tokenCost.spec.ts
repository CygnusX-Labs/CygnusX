// @vitest-environment jsdom

import { describe, expect, it, beforeEach } from 'vitest'
import {
  DEFAULT_TOKEN_PRICING,
  formatTokensInM,
  loadTokenPricing,
  resolvePricing,
  saveTokenPricing,
  summarizeUsage,
} from '../tokenCost'

describe('tokenCost', () => {
  beforeEach(() => localStorage.clear())

  it('round-trips pricing through localStorage with defaults', () => {
    expect(loadTokenPricing()).toEqual(DEFAULT_TOKEN_PRICING)
    saveTokenPricing({ inputPerM: 2.5, outputPerM: 10 })
    expect(loadTokenPricing()).toEqual({ inputPerM: 2.5, outputPerM: 10 })
  })

  it('falls back to defaults on corrupted storage', () => {
    localStorage.setItem('ai_token_pricing', '{broken')
    expect(loadTokenPricing()).toEqual(DEFAULT_TOKEN_PRICING)
  })

  it('formats tokens in M/K units', () => {
    expect(formatTokensInM(0)).toBe('0')
    expect(formatTokensInM(850)).toBe('850')
    expect(formatTokensInM(12_340)).toBe('12.3K')
    expect(formatTokensInM(2_450_000)).toBe('2.45M')
  })

  it('summarizes usage and cost across messages', () => {
    const usage = summarizeUsage(
      [
        { tokens: { input: 1_000_000, output: 200_000, total: 1_200_000 } },
        { tokens: { input: 500_000, output: 100_000 } },
        {},
      ],
      { inputPerM: 2, outputPerM: 8 },
    )
    expect(usage.input).toBe(1_500_000)
    expect(usage.output).toBe(300_000)
    expect(usage.total).toBe(1_800_000)
    // 1.5 * 2 + 0.3 * 8 = 5.4
    expect(usage.cost).toBeCloseTo(5.4)
  })

  it('resolves model pricing over global fallback per field', () => {
    const globalPricing = { inputPerM: 1, outputPerM: 2 }
    // 模型全配置：完全覆盖
    expect(resolvePricing(globalPricing, { input: 4, output: 12 })).toEqual({ inputPerM: 4, outputPerM: 12 })
    // 部分配置：缺省字段回退全局
    expect(resolvePricing(globalPricing, { input: 4, output: null })).toEqual({ inputPerM: 4, outputPerM: 2 })
    // 未配置：全局兜底
    expect(resolvePricing(globalPricing, null)).toEqual(globalPricing)
    expect(resolvePricing(globalPricing, { input: null, output: undefined })).toEqual(globalPricing)
  })
})
