import { apiFetch, apiUrl } from './client'
import type { ImageEngine, ImageSettings } from '../types/api'

/** Where a generated image is served (owner only, or anyone once its chat is shared). */
export const imageUrl = (id: string) => apiUrl(`/api/images/${id}`)

export const getImageSettings = () => apiFetch<ImageSettings>('/api/admin/images')

export const saveImageSettings = (body: {
  engine: ImageEngine
  base_url: string
  model: string
  size: string
  /** Omit to keep the saved key; "" removes it. */
  api_key?: string
}) => apiFetch<ImageSettings>('/api/admin/images', { method: 'PUT', body: JSON.stringify(body) })

export const testImage = (prompt: string) =>
  apiFetch<{ ok: boolean; data_url?: string; error?: string }>('/api/admin/images/test', {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
