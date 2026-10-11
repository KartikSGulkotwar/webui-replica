import { apiFetch } from './client'
import type {
  Conversation,
  ConversationDetail,
  ConversationPatch,
  Message,
  Rating,
  ShareInfo,
  SharedChat,
} from '../types/api'

const path = (id: string) => `/api/conversations/${encodeURIComponent(id)}`

export function listConversations(params: { q?: string; archived?: boolean } = {}) {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.archived) search.set('archived', 'true')
  const qs = search.toString()
  return apiFetch<Conversation[]>(`/api/conversations${qs ? `?${qs}` : ''}`)
}

export const getConversation = (id: string) => apiFetch<ConversationDetail>(path(id))

export const createConversation = (body: { title?: string; system_prompt?: string } = {}) =>
  apiFetch<Conversation>('/api/conversations', { method: 'POST', body: JSON.stringify(body) })

export const updateConversation = (id: string, patch: ConversationPatch) =>
  apiFetch<Conversation>(path(id), { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteConversation = (id: string) => apiFetch<void>(path(id), { method: 'DELETE' })

export const rateMessage = (
  conversationId: string,
  messageId: number,
  rating: Rating | null,
  comment?: string,
) =>
  apiFetch<Message>(`${path(conversationId)}/messages/${messageId}/rating`, {
    method: 'PUT',
    body: JSON.stringify({ rating, comment }),
  })

export const shareConversation = (id: string) =>
  apiFetch<ShareInfo>(`${path(id)}/share`, { method: 'POST' })

export const unshareConversation = (id: string) =>
  apiFetch<void>(`${path(id)}/share`, { method: 'DELETE' })

export const getSharedChat = (shareId: string) =>
  apiFetch<SharedChat>(`/api/shared/${encodeURIComponent(shareId)}`)

export const exportAllConversations = () =>
  apiFetch<ConversationDetail[]>('/api/conversations/export')
