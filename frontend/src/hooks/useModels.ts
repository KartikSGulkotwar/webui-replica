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
 * The model used for the next message. Remembered across reloads; otherwise the
 * deployment's default model, then the first available one.
 */
export function useSelectedModel(models: ModelInfo[] | undefined, defaultModel?: string | null) {
  const [stored, setStored] = useState<string | null>(readStored)

  const selected = useMemo(() => {
    if (!models || models.length === 0) return null
    return (
      models.find((m) => m.id === stored) ?? models.find((m) => m.id === defaultModel) ?? models[0]
    )
  }, [models, stored, defaultModel])

  useEffect(() => {
    try {
      if (stored) localStorage.setItem(STORAGE_KEY, stored)
    } catch {
      // storage unavailable (private mode); selection just won't persist
    }
  }, [stored])

  return { selected, select: setStored }
}
