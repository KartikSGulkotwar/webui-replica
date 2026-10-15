import { apiFetch } from './client'
import { streamText } from './stream'
import type { Conversation, Note, NoteAiAction, NoteSummary } from '../types/api'

export const listNotes = (q = '') =>
  apiFetch<NoteSummary[]>(`/api/notes${q ? `?q=${encodeURIComponent(q)}` : ''}`)

export const createNote = (body: { title?: string; content?: string } = {}) =>
  apiFetch<Note>('/api/notes', { method: 'POST', body: JSON.stringify(body) })

export const getNote = (id: string) => apiFetch<Note>(`/api/notes/${id}`)

export const updateNote = (
  id: string,
  patch: Partial<Pick<Note, 'title' | 'content' | 'pinned'>>,
) => apiFetch<Note>(`/api/notes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteNote = (id: string) => apiFetch<void>(`/api/notes/${id}`, { method: 'DELETE' })

export const noteAi = (
  id: string,
  body: { action: NoteAiAction; model_id: string; text?: string; instruction?: string },
  options: { signal?: AbortSignal; onDelta: (delta: string) => void },
) => streamText(`/api/notes/${id}/ai`, body, options)

export const chatAboutNote = (id: string) =>
  apiFetch<Conversation>(`/api/notes/${id}/chat`, { method: 'POST' })
