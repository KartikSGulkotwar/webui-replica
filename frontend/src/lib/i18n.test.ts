import { describe, expect, it } from 'vitest'
import en from '../locales/en'
import { format, LANGUAGES } from './i18n'

describe('i18n', () => {
  it('fills in placeholders', () => {
    expect(format('Continue with {provider}', { provider: 'GitHub' })).toBe('Continue with GitHub')
    expect(format('No {x}', {})).toBe('No {x}')
  })

  it('translates every key, keeping the same placeholders', () => {
    const placeholders = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join()
    for (const [code, { messages }] of Object.entries(LANGUAGES)) {
      for (const [key, text] of Object.entries(en)) {
        const translated = messages[key as keyof typeof en]
        expect(translated, `${code}:${key}`).toBeTruthy()
        expect(placeholders(translated), `${code}:${key}`).toBe(placeholders(text))
      }
    }
  })
})
