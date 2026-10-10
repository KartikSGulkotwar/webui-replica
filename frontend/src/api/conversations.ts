import { apiFetch } from './client'
import type { Conversation, ConversationDetail } from '../types/api'

const path = (id: string) => `/api/conversations/${encodeURIComponent(id)}`

export const listConversations = () => apiFetch<Conversation[]>('/api/conversations')

export const getConversation = (id: string) => apiFetch<ConversationDetail>(path(id))

export const createConversation = (title?: string) =>
  apiFetch<Conversation>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })

export const renameConversation = (id: string, title: string) =>
  apiFetch<Conversation>(path(id), { method: 'PATCH', body: JSON.stringify({ title }) })

export const deleteConversation = (id: string) => apiFetch<void>(path(id), { method: 'DELETE' })
