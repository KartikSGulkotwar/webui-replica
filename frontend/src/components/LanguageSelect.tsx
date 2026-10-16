import { LANGUAGES, useI18n, type Language } from '../lib/i18n'

/** Pick the interface language (kept in this browser). */
export default function LanguageSelect({ compact }: { compact?: boolean }) {
  const { language, setLanguage, t } = useI18n()
  return (
    <select
      value={language}
      onChange={(e) => setLanguage(e.target.value as Language)}
      aria-label={t('account.language')}
      className={
        compact
          ? 'rounded-md border border-zinc-200 bg-transparent px-2 py-1 text-xs text-zinc-500 dark:border-zinc-800'
          : 'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-900 sm:w-64'
      }
    >
      {(Object.keys(LANGUAGES) as Language[]).map((code) => (
        <option key={code} value={code}>
          {LANGUAGES[code].label}
        </option>
      ))}
    </select>
  )
}
