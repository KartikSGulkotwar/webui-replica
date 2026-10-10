import type { ProviderKind } from '../types/api'

export interface Preset {
  label: string
  kind: ProviderKind
  base_url: string
  needsKey: boolean
}

export const PRESETS: Preset[] = [
  { label: 'Ollama', kind: 'ollama', base_url: 'http://localhost:11434', needsKey: false },
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
  {
    label: 'LM Studio',
    kind: 'openai_compat',
    base_url: 'http://localhost:1234/v1',
    needsKey: false,
  },
]

export const KIND_LABELS: Record<ProviderKind, string> = {
  ollama: 'Ollama',
  openai_compat: 'OpenAI-compatible',
}
