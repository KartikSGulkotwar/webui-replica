import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import type { HealthResponse } from '../types/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiFetch<HealthResponse>('/api/health'),
    refetchInterval: 30_000,
  })
}
