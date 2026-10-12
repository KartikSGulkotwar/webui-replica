import { describe, expect, it } from 'vitest'
import { describeArgs } from './tools'

describe('describeArgs', () => {
  it('shows a single string argument on its own', () => {
    expect(describeArgs({ expression: '23*47' })).toBe('23*47')
  })

  it('shows nothing for no arguments', () => {
    expect(describeArgs({})).toBe('')
  })

  it('falls back to JSON for anything else', () => {
    expect(describeArgs({ a: 1, b: 'x' })).toBe('{"a":1,"b":"x"}')
    expect(describeArgs('raw')).toBe('"raw"')
    expect(describeArgs(undefined)).toBe('')
  })
})
