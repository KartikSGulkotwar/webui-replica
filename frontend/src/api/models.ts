import { apiFetch } from './client'
import type { ModelsResponse } from '../types/api'

export const getModels = () => apiFetch<ModelsResponse>('/api/models')
