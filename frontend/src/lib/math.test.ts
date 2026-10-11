import { describe, expect, it } from 'vitest'
import { hasMath, normalizeMath } from './math'

describe('normalizeMath', () => {
  it('converts inline \\( \\) to $$ $$', () => {
    expect(normalizeMath('Area is \\( \\pi r^2 \\).')).toBe('Area is $$\\pi r^2$$.')
  })

  it('converts display \\[ \\] to a $$ block', () => {
    expect(normalizeMath('Sum:\\[ \\sum_{i=1}^n i \\]done')).toBe(
      'Sum:\n$$\n\\sum_{i=1}^n i\n$$\ndone',
    )
  })

  it('handles multi-line display math', () => {
    expect(normalizeMath('\\[\na + b\n= c\n\\]')).toBe('\n$$\na + b\n= c\n$$\n')
  })

  it('leaves fenced and inline code alone', () => {
    const md = 'Use `\\(x\\)` or\n```\nprint("\\[1\\]")\n```\nthen \\(y\\)'
    expect(normalizeMath(md)).toBe('Use `\\(x\\)` or\n```\nprint("\\[1\\]")\n```\nthen $$y$$')
  })

  it('leaves dollar amounts and existing $$ math untouched', () => {
    expect(normalizeMath('It costs $5 and $10.')).toBe('It costs $5 and $10.')
    expect(normalizeMath('$$E = mc^2$$')).toBe('$$E = mc^2$$')
  })

  it('handles an unclosed code fence while streaming', () => {
    expect(normalizeMath('```py\n\\(not math\\)')).toBe('```py\n\\(not math\\)')
  })
})

describe('hasMath', () => {
  it.each([
    ['plain text with $5 prices', false],
    ['inline \\(x^2\\)', true],
    ['display \\[x\\]', true],
    ['$$E=mc^2$$', true],
  ])('%s → %s', (text, expected) => {
    expect(hasMath(text)).toBe(expected)
  })
})
