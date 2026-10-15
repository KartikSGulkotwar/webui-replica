import { describe, expect, it } from 'vitest'
import { splitForSpeech, toSpeakable } from './speechText'

describe('toSpeakable', () => {
  it('drops markdown, links, code and citations', () => {
    const md = [
      '## Result',
      'Use **Python** and see [the docs](https://docs.python.org) [1]【2†L1-L3】.',
      '- one',
      '- two',
      '```py',
      'print(1)',
      '```',
      'Done: https://example.com',
    ].join('\n')
    expect(toSpeakable(md)).toBe(
      'Result\nUse Python and see the docs .\none\ntwo\n (code omitted) \nDone:',
    )
  })
})

describe('splitForSpeech', () => {
  it('keeps short text whole and splits long text at sentences', () => {
    expect(splitForSpeech('Hi there. How are you?')).toEqual(['Hi there. How are you?'])
    const long = 'First sentence is here. Second one follows. Third ends it.'
    expect(splitForSpeech(long, 30)).toEqual([
      'First sentence is here.',
      'Second one follows.',
      'Third ends it.',
    ])
  })
})
