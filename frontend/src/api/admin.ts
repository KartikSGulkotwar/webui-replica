import { apiFetch } from './client'
import type { AdminSettings, User, UserRole } from '../types/api'

export const listUsers = () => apiFetch<User[]>('/api/admin/users')

export const setUserRole = (id: string, role: UserRole) =>
  apiFetch<User>(`/api/admin/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  })

export const deleteUser = (id: string) =>
  apiFetch<void>(`/api/admin/users/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const getAdminSettings = () => apiFetch<AdminSettings>('/api/admin/settings')

export const saveAdminSettings = (body: AdminSettings) =>
  apiFetch<AdminSettings>('/api/admin/settings', { method: 'PUT', body: JSON.stringify(body) })
