import type { ProviderKind } from '../types/api'

export interface Preset {
  label: string
  kind: ProviderKind
  base_url: string
  needsKey: boolean
}

/**
 * Provider URLs are called by the backend, not the browser. When the backend runs
 * in Docker, "localhost" is the container itself, so local servers need
 * host.docker.internal (or the compose service name for the bundled Ollama).
 */
export function getPresets(inDocker: boolean): Preset[] {
  const host = inDocker ? 'host.docker.internal' : 'localhost'
  return [
    {
      label: 'Ollama',
      kind: 'ollama',
      base_url: inDocker ? 'http://ollama:11434' : 'http://localhost:11434',
      needsKey: false,
    },
    ...REMOTE_PRESETS,
    {
      label: 'LM Studio',
      kind: 'openai_compat',
      base_url: `http://${host}:1234/v1`,
      needsKey: false,
    },
  ]
}

const REMOTE_PRESETS: Preset[] = [
  {
    label: 'Groq',
    kind: 'openai_compat',
    base_url: 'https://api.groq.com/openai/v1',
    needsKey: true,
  },
  {
    label: 'OpenRouter',
    kind: 'openai_compat',
    base_url: 'https://openrouter.ai/api/v1',
    needsKey: true,
  },
  { label: 'OpenAI', kind: 'openai_compat', base_url: 'https://api.openai.com/v1', needsKey: true },
  {
    label: 'Together',
    kind: 'openai_compat',
    base_url: 'https://api.together.xyz/v1',
    needsKey: true,
  },
]

export const KIND_LABELS: Record<ProviderKind, string> = {
  ollama: 'Ollama',
  openai_compat: 'OpenAI-compatible',
}
