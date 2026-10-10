import { useState } from 'react'
import { errorMessage } from '../api/client'
import { MenuIcon, PlusIcon } from '../components/icons'
import ProviderCard from '../components/ProviderCard'
import ProviderForm from '../components/ProviderForm'
import ThemeToggle from '../components/ThemeToggle'
import { useLayout } from '../hooks/useLayout'
import { useAppConfig, useProviders } from '../hooks/useProviders'

/** "new" while adding, a provider id while editing, null otherwise. */
type Editing = 'new' | string | null

export default function SettingsPage() {
  const { sidebarOpen, openSidebar } = useLayout()
  const config = useAppConfig()
  const providers = useProviders()
  const [editing, setEditing] = useState<Editing>(null)

  const readOnly = config.data?.providers_read_only ?? false
  const encryptionConfigured = config.data?.encryption_configured ?? true

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-1 border-b border-zinc-200 px-2 py-2 dark:border-zinc-800 sm:gap-2 sm:px-4">
        {!sidebarOpen && (
          <button
            type="button"
            onClick={openSidebar}
            className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            aria-label="Open sidebar"
            title="Open sidebar"
          >
            <MenuIcon />
          </button>
        )}
        <h1 className="flex-1 px-2 text-sm font-semibold">Settings</h1>
        <ThemeToggle />
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Providers</h2>
              <p className="text-sm text-zinc-500">
                Where models come from. Each enabled provider’s models appear in the model menu.
              </p>
            </div>
            {!readOnly && editing !== 'new' && (
              <button
                type="button"
                onClick={() => setEditing('new')}
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                <PlusIcon />
                Add provider
              </button>
            )}
          </div>

          {readOnly && (
            <p className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              This is a public demo, so provider settings are read-only. Run it yourself with{' '}
              <code>docker compose up</code> to add your own providers.
            </p>
          )}
          {!readOnly && !encryptionConfigured && (
            <p className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              <strong>ENCRYPTION_KEY</strong> is not set on the backend, so providers that need an
              API key can’t be saved. Providers without a key (like Ollama) still work.
            </p>
          )}

          {editing === 'new' && (
            <ProviderForm
              encryptionConfigured={encryptionConfigured}
              onDone={() => setEditing(null)}
              onCancel={() => setEditing(null)}
            />
          )}

          {providers.isLoading && (
            <div className="space-y-3">
              {[0, 1].map((i) => (
                <div
                  key={i}
                  className="h-28 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900"
                />
              ))}
            </div>
          )}
          {providers.isError && (
            <div className="rounded-lg border border-red-300 px-4 py-3 text-sm text-red-600 dark:border-red-900 dark:text-red-400">
              Couldn’t load providers: {errorMessage(providers.error)}{' '}
              <button type="button" onClick={() => providers.refetch()} className="underline">
                Retry
              </button>
            </div>
          )}
          {providers.isSuccess && providers.data.length === 0 && editing !== 'new' && (
            <div className="rounded-xl border border-dashed border-zinc-300 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
              No providers yet. Add Ollama or an OpenAI-compatible API to start chatting.
            </div>
          )}

          <ul className="space-y-3">
            {providers.data?.map((p) =>
              editing === p.id ? (
                <li key={p.id}>
                  <ProviderForm
                    provider={p}
                    encryptionConfigured={encryptionConfigured}
                    onDone={() => setEditing(null)}
                    onCancel={() => setEditing(null)}
                  />
                </li>
              ) : (
                <ProviderCard
                  key={p.id}
                  provider={p}
                  readOnly={readOnly}
                  onEdit={() => setEditing(p.id)}
                />
              ),
            )}
          </ul>
        </div>
      </div>
    </div>
  )
}
