import { apiUrl, toApiError } from './client'
import type { ChatStreamRequest, StreamEvent } from '../types/api'

/**
 * Incremental parser for Server-Sent Events. Network chunks can split an event
 * anywhere, so text is buffered until a blank line ends the event.
 */
export function createSSEParser(onData: (data: string) => void) {
  let buffer = ''

  const emit = (raw: string) => {
    const data = raw
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (data) onData(data)
  }

  return {
    feed(chunk: string) {
      buffer = (buffer + chunk).replace(/\r\n/g, '\n')
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        emit(buffer.slice(0, idx))
        buffer = buffer.slice(idx + 2)
      }
    },
    flush() {
      if (buffer.trim()) emit(buffer)
      buffer = ''
    },
  }
}

export async function streamChat(
  body: ChatStreamRequest,
  { signal, onEvent }: { signal: AbortSignal; onEvent: (event: StreamEvent) => void },
): Promise<void> {
  const resp = await fetch(apiUrl('/api/chat/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok) throw await toApiError(resp)
  if (!resp.body) throw new Error('This browser does not support streaming responses')

  const parser = createSSEParser((data) => {
    try {
      onEvent(JSON.parse(data) as StreamEvent)
    } catch {
      // ignore malformed events rather than killing the stream
    }
  })
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    parser.feed(decoder.decode(value, { stream: true }))
  }
  parser.feed(decoder.decode())
  parser.flush()
}
