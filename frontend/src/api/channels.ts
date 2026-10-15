import { apiFetch } from './client'
import { streamText } from './stream'
import type { Channel, ChannelMessage, ChannelMessagePage } from '../types/api'

const base = (id: string) => `/api/channels/${id}`

export const listChannels = () => apiFetch<Channel[]>('/api/channels')

export const createChannel = (body: { name: string; description: string }) =>
  apiFetch<Channel>('/api/channels', { method: 'POST', body: JSON.stringify(body) })

export const updateChannel = (id: string, body: { name: string; description: string }) =>
  apiFetch<Channel>(base(id), { method: 'PATCH', body: JSON.stringify(body) })

export const deleteChannel = (id: string) => apiFetch<void>(base(id), { method: 'DELETE' })

export const getMessages = (id: string, params: { before?: number; since?: string } = {}) => {
  const q = new URLSearchParams()
  if (params.before) q.set('before', String(params.before))
  if (params.since) q.set('since', params.since)
  return apiFetch<ChannelMessagePage>(`${base(id)}/messages${q.size ? `?${q}` : ''}`)
}

export const postMessage = (id: string, body: { content: string; reply_to?: number | null }) =>
  apiFetch<ChannelMessage>(`${base(id)}/messages`, { method: 'POST', body: JSON.stringify(body) })

export const editMessage = (id: string, messageId: number, content: string) =>
  apiFetch<ChannelMessage>(`${base(id)}/messages/${messageId}`, {
    method: 'PATCH',
    body: JSON.stringify({ content }),
  })

export const deleteMessage = (id: string, messageId: number) =>
  apiFetch<void>(`${base(id)}/messages/${messageId}`, { method: 'DELETE' })

export const toggleReaction = (id: string, messageId: number, emoji: string) =>
  apiFetch<ChannelMessage>(`${base(id)}/messages/${messageId}/reactions`, {
    method: 'PUT',
    body: JSON.stringify({ emoji }),
  })

export const askModel = (
  id: string,
  body: { model_id: string; message_id: number },
  options: { signal?: AbortSignal; onDelta: (delta: string) => void },
) => streamText(`${base(id)}/ai`, body, options)
