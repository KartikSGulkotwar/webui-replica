import { describe, expect, it } from 'vitest'
import { modelLabel } from './models'
import type { ModelInfo } from '../types/api'

const models: ModelInfo[] = [
  {
    id: 'anthropic:claude-opus-5-5',
    name: 'claude-opus-5-5',
    provider_id: 'anthropic',
    provider_name: 'Anthropic',
    provider_kind: 'anthropic',
  },
]

describe('modelLabel', () => {
  it('uses the model list', () => {
    expect(modelLabel('anthropic:claude-opus-5-5', models)).toEqual({
      name: 'claude-opus-5-5',
      provider: 'Anthropic',
    })
  })

  it("names the provider for a model that isn't listed (refusal fallback)", () => {
    expect(modelLabel('anthropic:claude-opus-4-8', models)).toEqual({
      name: 'claude-opus-4-8',
      provider: 'Anthropic',
    })
  })

  it('falls back to the raw id parts', () => {
    expect(modelLabel('gone:model:tag', models)).toEqual({ name: 'model:tag', provider: 'gone' })
    expect(modelLabel('bare', undefined)).toEqual({ name: 'bare', provider: '' })
  })
})
