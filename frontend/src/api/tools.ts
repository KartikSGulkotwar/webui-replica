import { apiFetch } from './client'
import type { ToolInfo } from '../types/api'

export const listTools = () => apiFetch<ToolInfo[]>('/api/tools')

/** Every built-in tool, enabled or not (admins only). */
export const listAllTools = () => apiFetch<ToolInfo[]>('/api/tools?all=true')
