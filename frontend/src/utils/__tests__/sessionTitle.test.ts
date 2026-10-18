import { describe, expect, it } from 'vitest'
import { shouldGenerateSessionTitle } from '@/utils/sessionTitle'

describe('shouldGenerateSessionTitle', () => {
  it('generates on the first turn and every third turn through turn twelve', () => {
    expect([1, 2, 3, 4, 6, 9, 12].map(count => shouldGenerateSessionTitle(count)))
      .toEqual([true, false, true, false, true, true, true])
  })

  it('stops after twelve turns and preserves manually locked titles', () => {
    expect(shouldGenerateSessionTitle(13)).toBe(false)
    expect(shouldGenerateSessionTitle(1, true)).toBe(false)
    expect(shouldGenerateSessionTitle(0)).toBe(false)
  })
})
