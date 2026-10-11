import { ApiError, apiFetch } from './client'
import type { User } from '../types/api'

/** The signed-in user, or null when signed out. */
export async function getMe(): Promise<User | null> {
  try {
    return await apiFetch<User>('/api/auth/me')
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null
    throw err
  }
}

export const signup = (body: { name: string; email: string; password: string }) =>
  apiFetch<User>('/api/auth/signup', { method: 'POST', body: JSON.stringify(body) })

export const login = (body: { email: string; password: string }) =>
  apiFetch<User>('/api/auth/login', { method: 'POST', body: JSON.stringify(body) })

export const continueAsGuest = () => apiFetch<User>('/api/auth/guest', { method: 'POST' })

export const logout = () => apiFetch<void>('/api/auth/logout', { method: 'POST' })

export const updateMe = (body: {
  name?: string
  current_password?: string
  new_password?: string
}) => apiFetch<User>('/api/auth/me', { method: 'PATCH', body: JSON.stringify(body) })

/** Full-page navigation: the provider redirects back to the backend. */
export const oauthLoginUrl = (provider: string) =>
  `${import.meta.env.VITE_API_URL ?? ''}/api/auth/oauth/${provider}/login`
