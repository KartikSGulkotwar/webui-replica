import { apiFetch } from './client'
import type { WebSearchEngine, WebSearchSettings, WebSearchTestResult } from '../types/api'

export const getWebSearchSettings = () => apiFetch<WebSearchSettings>('/api/admin/web-search')

export const saveWebSearchSettings = (body: {
  engine: WebSearchEngine
  base_url: string
  result_count: number
  /** Omit to keep the saved key; "" removes it. */
  api_key?: string
}) =>
  apiFetch<WebSearchSettings>('/api/admin/web-search', {
    method: 'PUT',
    body: JSON.stringify(body),
  })

export const testWebSearch = (query: string) =>
  apiFetch<WebSearchTestResult>('/api/admin/web-search/test', {
    method: 'POST',
    body: JSON.stringify({ query }),
  })
