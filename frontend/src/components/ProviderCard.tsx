import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { checkProviderHealth } from '../api/providers'
import { useDeleteProvider, useUpdateProvider } from '../hooks/useProviders'
import { KIND_LABELS } from '../lib/providerPresets'
import type { Provider } from '../types/api'
import HealthBadge from './HealthBadge'

interface Props {
  provider: Provider
  readOnly: boolean
  onEdit: () => void
}

const smallButton =
  'rounded-lg border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'

export default function ProviderCard({ provider, readOnly, onEdit }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const update = useUpdateProvider()
  const remove = useDeleteProvider()

  const health = useQuery({
    queryKey: ['provider-health', provider.id, provider.updated_at],
    queryFn: () => checkProviderHealth(provider.id),
    staleTime: 30_000,
    retry: false,
  })

  const error = update.error ?? remove.error

  return (
    <li
      className={`rounded-xl border border-zinc-200 p-4 dark:border-zinc-800 ${
        provider.enabled ? '' : 'opacity-70'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{provider.name}</h3>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              {KIND_LABELS[provider.kind]}
            </span>
            {!provider.enabled && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                Disabled
              </span>
            )}
          </div>
          <p className="mt-1 truncate font-mono text-xs text-zinc-500" title={provider.base_url}>
            {provider.base_url}
          </p>
          {provider.kind === 'openai_compat' && (
            <p className="mt-1 text-xs text-zinc-500">
              {provider.has_key ? 'API key saved (encrypted)' : 'No API key'}
            </p>
          )}
          <div className="mt-2">
            <HealthBadge
              health={
                health.isError
                  ? {
                      ok: false,
                      error: errorMessage(health.error),
                      latency_ms: null,
                      model_count: null,
                    }
                  : health.data
              }
              checking={health.isFetching}
            />
          </div>
        </div>

        <label
          className={`relative inline-flex shrink-0 items-center ${readOnly ? 'cursor-not-allowed' : 'cursor-pointer'}`}
          title={provider.enabled ? 'Disable' : 'Enable'}
        >
          <input
            type="checkbox"
            role="switch"
            className="peer sr-only"
            checked={provider.enabled}
            disabled={readOnly || update.isPending}
            onChange={(e) =>
              update.mutate({ id: provider.id, patch: { enabled: e.target.checked } })
            }
            aria-label={`${provider.enabled ? 'Disable' : 'Enable'} ${provider.name}`}
          />
          <span className="h-5 w-9 rounded-full bg-zinc-300 transition peer-checked:bg-indigo-600 peer-focus-visible:ring-2 peer-focus-visible:ring-indigo-500 peer-disabled:opacity-50 dark:bg-zinc-700" />
          <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-4" />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={smallButton}
          onClick={() => health.refetch()}
          disabled={health.isFetching}
        >
          Test connection
        </button>
        {!readOnly && (
          <>
            <button type="button" className={smallButton} onClick={onEdit}>
              Edit
            </button>
            {confirmDelete ? (
              <span className="flex items-center gap-2 text-xs">
                <span className="text-red-600 dark:text-red-400">Delete {provider.name}?</span>
                <button
                  type="button"
                  className="rounded-lg bg-red-600 px-2.5 py-1 text-xs text-white hover:bg-red-500 disabled:opacity-50"
                  onClick={() => remove.mutate(provider.id)}
                  disabled={remove.isPending}
                >
                  Delete
                </button>
                <button
                  type="button"
                  className={smallButton}
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                className={`${smallButton} text-red-600 dark:text-red-400`}
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </button>
            )}
          </>
        )}
      </div>

      {error && (
        <p className="mt-2 text-xs text-red-500" role="alert">
          {errorMessage(error)}
        </p>
      )}
    </li>
  )
}
