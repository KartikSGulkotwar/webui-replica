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
  {
    signal,
    onEvent,
    onOpen,
  }: {
    signal: AbortSignal
    onEvent: (event: StreamEvent) => void
    /** Called once the backend accepted the request (user message is saved). */
    onOpen?: () => void
  },
): Promise<void> {
  const resp = await fetch(apiUrl('/api/chat/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok) throw await toApiError(resp)
  if (!resp.body) throw new Error('This browser does not support streaming responses')
  onOpen?.()

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

/** A one-off streamed AI text (notes, channels): calls onDelta as it arrives,
 * resolves with the whole text, rejects on an error event. */
export async function streamText(
  path: string,
  body: unknown,
  { signal, onDelta }: { signal?: AbortSignal; onDelta: (delta: string) => void },
): Promise<string> {
  const resp = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok) throw await toApiError(resp)
  if (!resp.body) throw new Error('This browser does not support streaming responses')
  let text = ''
  let failure: string | null = null
  const parser = createSSEParser((data) => {
    try {
      const event = JSON.parse(data) as { delta?: string; error?: string }
      if (event.delta) {
        text += event.delta
        onDelta(event.delta)
      }
      if (event.error) failure = event.error
    } catch {
      // ignore malformed events
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
  if (failure) throw new Error(failure)
  return text
}
