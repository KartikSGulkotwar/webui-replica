import { useEffect, useMemo, useRef, useState } from 'react'
import type { ModelInfo, ModelsResponse } from '../types/api'
import { CheckIcon, ChevronDownIcon, SearchIcon } from './icons'

interface Props {
  data: ModelsResponse | undefined
  isLoading: boolean
  isError: boolean
  selected: ModelInfo | null
  onSelect: (id: string) => void
}

function HealthDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-500'}`}
      aria-label={ok ? 'online' : 'offline'}
    />
  )
}

export default function ModelSelector({ data, isLoading, isError, selected, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const groups = useMemo(() => {
    if (!data) return []
    const q = query.trim().toLowerCase()
    return data.providers.map((provider) => ({
      provider,
      models: data.models.filter(
        (m) => m.provider_id === provider.id && (!q || m.name.toLowerCase().includes(q)),
      ),
    }))
  }, [data, query])

  const selectedProvider = data?.providers.find((p) => p.id === selected?.provider_id)

  let label: React.ReactNode
  if (isLoading) label = <span className="text-zinc-500">Loading models…</span>
  else if (isError) label = <span className="text-red-500">Models unavailable</span>
  else if (!selected) label = <span className="text-zinc-500">No models</span>
  else
    label = (
      <>
        <HealthDot ok={selectedProvider?.ok ?? true} />
        <span className="truncate font-medium">{selected.name}</span>
        <span className="hidden truncate text-zinc-500 sm:inline">· {selected.provider_name}</span>
      </>
    )

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={isLoading}
        className="flex min-w-0 max-w-[60vw] items-center gap-2 rounded-lg px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:cursor-wait dark:hover:bg-zinc-800 sm:max-w-md"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {label}
        <ChevronDownIcon className="shrink-0 text-zinc-500" />
      </button>

      {open && (
        <div className="absolute left-0 z-20 mt-1 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center gap-2 border-b border-zinc-200 px-3 dark:border-zinc-800">
            <SearchIcon className="text-zinc-400" />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models"
              className="w-full bg-transparent py-2.5 text-sm outline-none placeholder:text-zinc-400"
            />
          </div>
          <div className="max-h-80 overflow-y-auto py-1" role="listbox">
            {isError && (
              <p className="px-3 py-4 text-sm text-red-500">Could not load models from the backend.</p>
            )}
            {data && data.providers.length === 0 && (
              <p className="px-3 py-4 text-sm text-zinc-500">
                No providers configured. Set <code>OLLAMA_BASE_URL</code> or{' '}
                <code>OPENAI_COMPAT_BASE_URL</code> on the backend.
              </p>
            )}
            {groups.map(({ provider, models }) => (
              <div key={provider.id} className="py-1">
                <div className="flex items-center gap-2 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  <HealthDot ok={provider.ok} />
                  {provider.name}
                </div>
                {!provider.ok && (
                  <p className="px-3 pb-1 text-xs text-red-500" title={provider.error ?? undefined}>
                    {provider.error ?? 'Unavailable'}
                  </p>
                )}
                {provider.ok && models.length === 0 && (
                  <p className="px-3 pb-1 text-xs text-zinc-500">
                    {query
                      ? 'No matches'
                      : provider.kind === 'ollama'
                        ? 'No models installed. Run: ollama pull <model>'
                        : 'No models available'}
                  </p>
                )}
                {models.map((m) => {
                  const active = m.id === selected?.id
                  return (
                    <button
                      key={m.id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => {
                        onSelect(m.id)
                        setOpen(false)
                        setQuery('')
                      }}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800 ${
                        active ? 'font-medium' : ''
                      }`}
                    >
                      <span className="truncate">{m.name}</span>
                      {active && <CheckIcon className="shrink-0 text-indigo-500" />}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
