import { apiFetch } from './client'
import type { AdminModel, CustomModel, CustomModelInput } from '../types/api'

const path = (id: string) => `/api/custom-models/${encodeURIComponent(id)}`

export const listCustomModels = () => apiFetch<CustomModel[]>('/api/custom-models')

export const createCustomModel = (body: CustomModelInput) =>
  apiFetch<CustomModel>('/api/custom-models', { method: 'POST', body: JSON.stringify(body) })

export const updateCustomModel = (id: string, body: CustomModelInput) =>
  apiFetch<CustomModel>(path(id), { method: 'PUT', body: JSON.stringify(body) })

export const deleteCustomModel = (id: string) => apiFetch<void>(path(id), { method: 'DELETE' })

export const listAdminModels = () => apiFetch<AdminModel[]>('/api/admin/models')

export const updateAdminModel = (body: {
  model_id: string
  hidden: boolean
  display_name?: string | null
}) => apiFetch<void>('/api/admin/models', { method: 'PUT', body: JSON.stringify(body) })
