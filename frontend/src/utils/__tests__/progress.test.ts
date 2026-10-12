import { describe, expect, it } from 'vitest'
import { normalizeProgress } from '../progress'

describe('normalizeProgress', () => {
  it.each([
    [0, 0],
    [0.45, 45],
    [1, 100],
    [45, 45],
    [100, 100],
    [null, 0],
    [Number.NaN, 0],
    [-0.5, 0],
    [1000, 100],
  ])('normalizes %s to %s%', (input, expected) => {
    expect(normalizeProgress(input)).toBe(expected)
  })
})
