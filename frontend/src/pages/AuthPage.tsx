import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { oauthLoginUrl } from '../api/auth'
import { errorMessage } from '../api/client'
import ThemeToggle from '../components/ThemeToggle'
import { useGuest, useLogin, useMe, useSignup } from '../hooks/useAuth'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useAppConfig } from '../hooks/useProviders'
import LanguageSelect from '../components/LanguageSelect'
import { useT } from '../lib/i18n'

const PROVIDER_LABELS: Record<string, string> = { github: 'GitHub', google: 'Google' }

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-900'

/** Only allow redirects back into this app, never to another site. */
function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

export default function AuthPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const me = useMe()
  const config = useAppConfig()
  const t = useT()
  const login = useLogin()
  const signup = useSignup()
  const guest = useGuest()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const firstRun = config.data ? !config.data.has_users : false
  const signupAllowed = config.data?.signup_enabled ?? true
  const showSignup = firstRun || (mode === 'signup' && signupAllowed)
  useDocumentTitle(firstRun ? 'Create admin account' : showSignup ? 'Sign up' : 'Sign in')

  const next = safeNext(params.get('next'))
  if (me.data) return <Navigate to={next} replace />
  // Wait for the site settings: they decide between "create the admin account"
  // and normal sign-in, and rendering early flashes the wrong one.
  if (config.isLoading) return <div className="h-full bg-paper dark:bg-zinc-950" />

  const busy = login.isPending || signup.isPending || guest.isPending
  const error = signup.error ?? login.error ?? guest.error
  const oauthError = params.get('error')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const done = { onSuccess: () => navigate(next, { replace: true }) }
    if (showSignup) signup.mutate({ name: name.trim(), email: email.trim(), password }, done)
    else login.mutate({ email: email.trim(), password }, done)
  }

  return (
    <div className="flex h-full flex-col bg-paper text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <div className="flex justify-end p-2">
        <ThemeToggle />
      </div>
      <main className="flex flex-1 items-start justify-center overflow-y-auto px-4 pb-10 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              {firstRun
                ? t('auth.createAdmin')
                : showSignup
                  ? t('auth.createAccount')
                  : t('auth.welcomeBack')}
            </h1>
            <p className="text-sm text-zinc-500">
              {firstRun ? t('auth.firstRun') : t('auth.tagline')}
            </p>
          </div>

          {(oauthError || error) && (
            <p
              className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
              role="alert"
            >
              {error ? errorMessage(error) : oauthError}
            </p>
          )}

          <form onSubmit={submit} className="space-y-3">
            {showSignup && (
              <div>
                <label htmlFor="auth-name" className="mb-1 block text-sm font-medium">
                  {t('auth.name')}
                </label>
                <input
                  id="auth-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={100}
                  autoComplete="name"
                  className={input}
                />
              </div>
            )}
            <div>
              <label htmlFor="auth-email" className="mb-1 block text-sm font-medium">
                {t('auth.email')}
              </label>
              <input
                id="auth-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className={input}
              />
            </div>
            <div>
              <label htmlFor="auth-password" className="mb-1 block text-sm font-medium">
                {t('auth.password')}
              </label>
              <input
                id="auth-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={showSignup ? 8 : undefined}
                autoComplete={showSignup ? 'new-password' : 'current-password'}
                className={input}
              />
              {showSignup && <p className="mt-1 text-xs text-zinc-500">{t('auth.minLength')}</p>}
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
            >
              {busy ? t('auth.wait') : showSignup ? t('auth.submitSignup') : t('auth.signIn')}
            </button>
          </form>

          {!firstRun && (config.data?.oauth_providers.length ?? 0) > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-3 text-xs text-zinc-500">
                <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
                {t('auth.or')}
                <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
              </div>
              {config.data!.oauth_providers.map((p) => (
                <a
                  key={p}
                  href={oauthLoginUrl(p)}
                  className="flex w-full items-center justify-center rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                >
                  {t('auth.continueWith', { provider: PROVIDER_LABELS[p] ?? p })}
                </a>
              ))}
            </div>
          )}

          {config.data?.guest_access && !firstRun && (
            <button
              type="button"
              onClick={() =>
                guest.mutate(undefined, { onSuccess: () => navigate(next, { replace: true }) })
              }
              disabled={busy}
              className="w-full rounded-lg border border-dashed border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 disabled:opacity-60 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {t('auth.guest')}
            </button>
          )}

          {!firstRun && signupAllowed && (
            <p className="text-center text-sm text-zinc-500">
              {showSignup ? t('auth.haveAccount') : t('auth.newHere')}
              <button
                type="button"
                onClick={() => {
                  setMode(showSignup ? 'signin' : 'signup')
                  login.reset()
                  signup.reset()
                }}
                className="font-medium text-indigo-500 hover:underline"
              >
                {showSignup ? t('auth.signIn') : t('auth.createAccount')}
              </button>
            </p>
          )}
          <div className="flex justify-center">
            <LanguageSelect compact />
          </div>
        </div>
      </main>
    </div>
  )
}
