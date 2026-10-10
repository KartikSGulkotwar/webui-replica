import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { getModels } from '../api/models'
import type { ModelInfo } from '../types/api'

const STORAGE_KEY = 'webui.selectedModel'

export function useModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: getModels,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

/**
 * The model used for the next message. Remembered across reloads; falls back to
 * the first available model if the remembered one is gone.
 */
export function useSelectedModel(models: ModelInfo[] | undefined) {
  const [stored, setStored] = useState<string | null>(readStored)

  const selected = useMemo(() => {
    if (!models || models.length === 0) return null
    return models.find((m) => m.id === stored) ?? models[0]
  }, [models, stored])

  useEffect(() => {
    try {
      if (stored) localStorage.setItem(STORAGE_KEY, stored)
    } catch {
      // storage unavailable (private mode); selection just won't persist
    }
  }, [stored])

  return { selected, select: setStored }
}
