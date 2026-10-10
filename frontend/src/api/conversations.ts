import { apiFetch } from './client'
import type { Conversation, ConversationDetail } from '../types/api'

export const getConversation = (id: string) =>
  apiFetch<ConversationDetail>(`/api/conversations/${encodeURIComponent(id)}`)

export const createConversation = (title?: string) =>
  apiFetch<Conversation>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
