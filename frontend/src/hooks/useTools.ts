import { useQuery } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { listTools } from '../api/tools'

const STORAGE_KEY = 'webui.tools'

export const useToolList = () =>
  useQuery({ queryKey: ['tools'], queryFn: listTools, staleTime: 5 * 60_000 })

function readStored(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((v) => typeof v === 'string') : []
  } catch {
    return []
  }
}

/** Tools switched on for new messages; remembered in this browser. */
export function useSelectedTools() {
  const [selected, setSelected] = useState<string[]>(readStored)
  const toggle = useCallback((id: string) => {
    setSelected((current) => {
      const next = current.includes(id) ? current.filter((t) => t !== id) : [...current, id]
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        // storage unavailable; the choice lasts for this visit
      }
      return next
    })
  }, [])
  return { selected, toggle }
}
