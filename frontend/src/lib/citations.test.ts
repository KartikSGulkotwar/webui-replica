import { describe, expect, it } from 'vitest'
import { normalizeCitations } from './citations'

describe('normalizeCitations', () => {
  it('turns 【n†…】 markers into [n]', () => {
    expect(normalizeCitations('Spain won【1†L1-L4】【2†L4-L7】.')).toBe('Spain won[1][2].')
    expect(normalizeCitations('See 【3】')).toBe('See [3]')
  })

  it('leaves other text alone', () => {
    expect(normalizeCitations('Already [1], and 【note】 stays')).toBe(
      'Already [1], and 【note】 stays',
    )
  })
})
