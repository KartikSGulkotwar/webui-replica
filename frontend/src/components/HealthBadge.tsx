import type { ProviderHealth } from '../types/api'

export default function HealthBadge({
  health,
  checking,
}: {
  health: ProviderHealth | undefined
  checking: boolean
}) {
  if (checking) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-zinc-500">
        <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-400" />
        Checking…
      </span>
    )
  }
  if (!health) return null
  if (health.ok) {
    const details = [
      health.model_count != null &&
        `${health.model_count} model${health.model_count === 1 ? '' : 's'}`,
      health.latency_ms != null && `${health.latency_ms} ms`,
    ].filter(Boolean)
    return (
      <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        Connected{details.length ? ` · ${details.join(' · ')}` : ''}
      </span>
    )
  }
  return (
    <span className="flex min-w-0 items-start gap-1.5 text-xs text-red-600 dark:text-red-400">
      <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-red-500" />
      <span className="break-words">{health.error ?? 'Unavailable'}</span>
    </span>
  )
}
