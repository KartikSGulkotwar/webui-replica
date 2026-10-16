import { createContext, useContext } from 'react'
import en, { type MessageKey, type Messages } from '../locales/en'
import es from '../locales/es'
import fr from '../locales/fr'
import hi from '../locales/hi'

export const LANGUAGES = {
  en: { label: 'English', messages: en },
  hi: { label: 'हिन्दी (Hindi)', messages: hi },
  es: { label: 'Español (Spanish)', messages: es },
  fr: { label: 'Français (French)', messages: fr },
} satisfies Record<string, { label: string; messages: Messages }>

export type Language = keyof typeof LANGUAGES
export const LANGUAGE_STORAGE_KEY = 'webui.language'

/** Saved choice, else the browser's language if we have it, else English. */
export function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (saved && saved in LANGUAGES) return saved as Language
  } catch {
    // storage unavailable
  }
  const browser = (typeof navigator !== 'undefined' ? navigator.language : 'en').split('-')[0]
  return browser in LANGUAGES ? (browser as Language) : 'en'
}

/** "Hello {name}" + {name: "Ana"} → "Hello Ana". */
export function format(template: string, vars?: Record<string, string | number>): string {
  return vars
    ? template.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
    : template
}

export type T = (key: MessageKey, vars?: Record<string, string | number>) => string

export interface I18n {
  language: Language
  setLanguage: (l: Language) => void
  t: T
}

export const I18nContext = createContext<I18n | null>(null)

export function useI18n(): I18n {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}

/** The translate function for the current language. */
export const useT = () => useI18n().t
