import type { ModelInfo } from '../types/api'

/** Human label for a namespaced model id, using the model list when available. */
export function modelLabel(modelId: string, models: ModelInfo[] | undefined) {
  const known = models?.find((m) => m.id === modelId)
  if (known) return { name: known.name, provider: known.provider_name }
  const idx = modelId.indexOf(':')
  return idx === -1
    ? { name: modelId, provider: '' }
    : { name: modelId.slice(idx + 1), provider: modelId.slice(0, idx) }
}
