import { apiFetch } from './client'
import type {
  AppConfig,
  Provider,
  ProviderHealth,
  ProviderInput,
  ProviderKind,
  ProviderPatch,
} from '../types/api'

const path = (id: string) => `/api/providers/${encodeURIComponent(id)}`

export const getConfig = () => apiFetch<AppConfig>('/api/config')

export const listProviders = () => apiFetch<Provider[]>('/api/providers')

export const createProvider = (body: ProviderInput) =>
  apiFetch<Provider>('/api/providers', { method: 'POST', body: JSON.stringify(body) })

export const updateProvider = (id: string, body: ProviderPatch) =>
  apiFetch<Provider>(path(id), { method: 'PATCH', body: JSON.stringify(body) })

export const deleteProvider = (id: string) => apiFetch<void>(path(id), { method: 'DELETE' })

export const checkProviderHealth = (id: string) => apiFetch<ProviderHealth>(`${path(id)}/health`)

export const testConnection = (body: {
  kind: ProviderKind
  base_url: string
  api_key?: string
  provider_id?: string
}) =>
  apiFetch<ProviderHealth>('/api/providers/test', { method: 'POST', body: JSON.stringify(body) })
