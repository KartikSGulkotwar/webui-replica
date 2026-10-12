import type { ModelInfo } from '../types/api'

/** Human label for a namespaced model id, using the model list when available. */
export function modelLabel(modelId: string, models: ModelInfo[] | undefined) {
  const known = models?.find((m) => m.id === modelId)
  if (known) {
    const name = known.emoji ? `${known.emoji} ${known.name}` : known.name
    return { name, provider: known.provider_name }
  }
  const idx = modelId.indexOf(':')
  if (idx === -1) return { name: modelId, provider: '' }
  const providerId = modelId.slice(0, idx)
  // A custom model that's gone or hidden: show its ID readably.
  if (providerId === 'persona') return { name: modelId.slice(idx + 1), provider: 'Custom' }
  // A model that isn't listed (e.g. a refusal fallback, or one since removed):
  // still show its provider's display name.
  const provider = models?.find((m) => m.provider_id === providerId)?.provider_name ?? providerId
  return { name: modelId.slice(idx + 1), provider }
}
