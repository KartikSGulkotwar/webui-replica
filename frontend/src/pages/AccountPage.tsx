import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api/client'
import { exportAllConversations } from '../api/conversations'
import { downloadFile } from '../lib/exportChat'
import PageHeader from '../components/PageHeader'
import LanguageSelect from '../components/LanguageSelect'
import VoiceSettings from '../components/VoiceSettings'
import { useT } from '../lib/i18n'
import { useLogout, useMe, useUpdateMe } from '../hooks/useAuth'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-900'
const section = 'space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800'

export default function AccountPage() {
  const t = useT()
  useDocumentTitle(t('account.title'))
  const me = useMe()
  const logout = useLogout()
  const updateName = useUpdateMe()
  const updatePassword = useUpdateMe()
  const [name, setName] = useState(me.data?.name ?? '')
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const exportAll = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const all = await exportAllConversations()
      const date = new Date().toISOString().slice(0, 10)
      downloadFile(
        `webui-replica-chats-${date}.json`,
        JSON.stringify(all, null, 2),
        'application/json',
      )
    } catch (err) {
      setExportError(errorMessage(err))
    } finally {
      setExporting(false)
    }
  }

  const user = me.data
  if (!user) return null

  const saveName = (e: FormEvent) => {
    e.preventDefault()
    updateName.mutate({ name: name.trim() })
  }
  const savePassword = (e: FormEvent) => {
    e.preventDefault()
    updatePassword.mutate(
      { current_password: current || undefined, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
        },
      },
    )
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title={t('account.title')} />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-xl space-y-4 px-4 py-6">
          <div className={section}>
            <p className="text-sm">
              <span className="font-medium">{user.is_guest ? 'Guest account' : user.email}</span>
              <span className="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                {user.role}
              </span>
            </p>
            {user.is_guest && (
              <p className="text-sm text-zinc-500">
                Guest chats live in this browser’s session and are lost when you sign out.
              </p>
            )}
          </div>

          {!user.is_guest && (
            <form onSubmit={saveName} className={section}>
              <h2 className="font-semibold">{t('account.profile')}</h2>
              <div>
                <label htmlFor="acct-name" className="mb-1 block text-sm font-medium">
                  Name
                </label>
                <input
                  id="acct-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={100}
                  className={input}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="submit"
                  disabled={updateName.isPending || !name.trim() || name.trim() === user.name}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  Save
                </button>
                {updateName.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
                {updateName.isError && (
                  <span className="text-sm text-red-500">{errorMessage(updateName.error)}</span>
                )}
              </div>
            </form>
          )}

          {!user.is_guest && (
            <form onSubmit={savePassword} className={section}>
              <h2 className="font-semibold">
                {user.has_password ? t('account.changePassword') : t('account.setPassword')}
              </h2>
              {!user.has_password && (
                <p className="text-sm text-zinc-500">
                  You sign in with GitHub or Google. A password lets you sign in with your email
                  too.
                </p>
              )}
              {user.has_password && (
                <div>
                  <label htmlFor="acct-current" className="mb-1 block text-sm font-medium">
                    Current password
                  </label>
                  <input
                    id="acct-current"
                    type="password"
                    value={current}
                    onChange={(e) => setCurrent(e.target.value)}
                    required
                    autoComplete="current-password"
                    className={input}
                  />
                </div>
              )}
              <div>
                <label htmlFor="acct-new" className="mb-1 block text-sm font-medium">
                  New password
                </label>
                <input
                  id="acct-new"
                  type="password"
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  className={input}
                />
                <p className="mt-1 text-xs text-zinc-500">
                  At least 8 characters. Other devices will be signed out.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="submit"
                  disabled={updatePassword.isPending}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  Update password
                </button>
                {updatePassword.isSuccess && (
                  <span className="text-sm text-emerald-600">Password updated.</span>
                )}
                {updatePassword.isError && (
                  <span className="text-sm text-red-500">{errorMessage(updatePassword.error)}</span>
                )}
              </div>
            </form>
          )}

          <div className={section}>
            <h2 className="font-semibold">{t('account.voice')}</h2>
            <p className="text-sm text-zinc-500">{t('account.voiceHint')}</p>
            <VoiceSettings />
          </div>

          <div className={section}>
            <h2 className="font-semibold">{t('account.language')}</h2>
            <p className="text-sm text-zinc-500">{t('account.languageHint')}</p>
            <LanguageSelect />
          </div>

          <div className={section}>
            <h2 className="font-semibold">{t('account.data')}</h2>
            <p className="text-sm text-zinc-500">{t('account.dataHint')}</p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={exportAll}
                disabled={exporting}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                {exporting ? t('account.exporting') : t('account.export')}
              </button>
              {exportError && <span className="text-sm text-red-500">{exportError}</span>}
            </div>
          </div>

          <button
            type="button"
            onClick={() => logout.mutate(undefined)}
            className="w-full rounded-lg border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            {t('menu.signOut')}
          </button>
        </div>
      </div>
    </div>
  )
}
