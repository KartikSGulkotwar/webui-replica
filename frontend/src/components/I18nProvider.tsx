import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  format,
  I18nContext,
  initialLanguage,
  LANGUAGE_STORAGE_KEY,
  LANGUAGES,
  type Language,
  type T,
} from '../lib/i18n'
import en from '../locales/en'

/** Holds the interface language; `useT()` reads it. */
export default function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(initialLanguage)
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])
  const setLanguage = useCallback((l: Language) => {
    setLanguageState(l)
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, l)
    } catch {
      // the choice lasts for this visit only
    }
  }, [])
  const t = useCallback<T>(
    (key, vars) => format(LANGUAGES[language].messages[key] ?? en[key], vars),
    [language],
  )
  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
