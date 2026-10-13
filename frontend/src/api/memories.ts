import { apiFetch } from './client'
import type { MemoryItem, MemoryList } from '../types/api'

export const listMemories = () => apiFetch<MemoryList>('/api/memories')

export const setMemoryEnabled = (enabled: boolean) =>
  apiFetch<{ enabled: boolean }>('/api/memories/settings', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })

export const addMemory = (content: string) =>
  apiFetch<MemoryItem>('/api/memories', { method: 'POST', body: JSON.stringify({ content }) })

export const editMemory = (id: number, content: string) =>
  apiFetch<MemoryItem>(`/api/memories/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ content }),
  })

export const deleteMemory = (id: number) =>
  apiFetch<void>(`/api/memories/${id}`, { method: 'DELETE' })

export const deleteAllMemories = () => apiFetch<void>('/api/memories', { method: 'DELETE' })
