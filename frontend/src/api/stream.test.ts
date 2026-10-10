import { describe, expect, it } from 'vitest'
import { createSSEParser } from './stream'

function collect(chunks: string[]): string[] {
  const out: string[] = []
  const parser = createSSEParser((d) => out.push(d))
  chunks.forEach((c) => parser.feed(c))
  parser.flush()
  return out
}

describe('createSSEParser', () => {
  it('parses complete events', () => {
    expect(collect(['data: {"delta":"a"}\n\ndata: {"delta":"b"}\n\n'])).toEqual([
      '{"delta":"a"}',
      '{"delta":"b"}',
    ])
  })

  it('reassembles events split across chunks', () => {
    expect(collect(['da', 'ta: {"del', 'ta":"x"}\n', '\ndata: {"done":true}\n\n'])).toEqual([
      '{"delta":"x"}',
      '{"done":true}',
    ])
  })

  it('handles CRLF line endings', () => {
    expect(collect(['data: 1\r\n\r\ndata: 2\r\n\r\n'])).toEqual(['1', '2'])
  })

  it('ignores comments and non-data fields', () => {
    expect(collect([': keep-alive\n\nevent: ping\n\ndata: ok\n\n'])).toEqual(['ok'])
  })

  it('flushes a trailing event without a blank line', () => {
    expect(collect(['data: last'])).toEqual(['last'])
  })

  it('keeps unicode intact', () => {
    expect(collect(['data: {"delta":"héllo 👋"}\n\n'])).toEqual(['{"delta":"héllo 👋"}'])
  })
})
