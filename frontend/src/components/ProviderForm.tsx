import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api/client'
import { testConnection } from '../api/providers'
import { useCreateProvider, useUpdateProvider } from '../hooks/useProviders'
import { KIND_LABELS, PRESETS } from '../lib/providerPresets'
import type { Provider, ProviderHealth, ProviderKind } from '../types/api'
import HealthBadge from './HealthBadge'
import { EyeIcon, EyeOffIcon } from './icons'

interface Props {
  /** Omit to create a new provider. */
  provider?: Provider
  encryptionConfigured: boolean
  onDone: () => void
  onCancel: () => void
}

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const label = 'mb-1 block text-sm font-medium'
const secondaryButton =
  'rounded-lg border border-zinc-300 px-3 py-2 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'

export default function ProviderForm({ provider, encryptionConfigured, onDone, onCancel }: Props) {
  const editing = !!provider
  const [kind, setKind] = useState<ProviderKind>(provider?.kind ?? 'openai_compat')
  const [name, setName] = useState(provider?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [removeKey, setRemoveKey] = useState(false)
  const [testResult, setTestResult] = useState<ProviderHealth>()
  const [testing, setTesting] = useState(false)

  const create = useCreateProvider()
  const update = useUpdateProvider()
  const saving = create.isPending || update.isPending
  const saveError = create.error ?? update.error

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    setKind(preset.kind)
    setName(preset.label)
    setBaseUrl(preset.base_url)
    setTestResult(undefined)
  }

  const runTest = async () => {
    setTesting(true)
    setTestResult(undefined)
    try {
      setTestResult(
        await testConnection({
          kind,
          base_url: baseUrl,
          api_key: apiKey.trim() || undefined,
          // Editing without typing a new key: test with the saved one.
          provider_id: editing && !apiKey.trim() && !removeKey ? provider.id : undefined,
        }),
      )
    } catch (err) {
      setTestResult({ ok: false, error: errorMessage(err), latency_ms: null, model_count: null })
    } finally {
      setTesting(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const key = apiKey.trim()
    if (editing) {
      update.mutate(
        {
          id: provider.id,
          patch: {
            name: name.trim(),
            base_url: baseUrl.trim(),
            // undefined keeps the stored key; "" removes it.
            ...(key ? { api_key: key } : removeKey ? { api_key: '' } : {}),
          },
        },
        { onSuccess: onDone },
      )
    } else {
      create.mutate(
        { name: name.trim(), kind, base_url: baseUrl.trim(), api_key: key || null },
        { onSuccess: onDone },
      )
    }
  }

  const showKeyField = kind === 'openai_compat'
  const keyBlocked = showKeyField && !!apiKey.trim() && !encryptionConfigured

  return (
    <form
      onSubmit={submit}
      className="space-y-4 rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <h3 className="font-semibold">{editing ? `Edit ${provider.name}` : 'Add provider'}</h3>

      {!editing && (
        <div>
          <span className={label}>Quick start</span>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  name === p.label && baseUrl === p.base_url
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                    : 'border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="provider-kind">
            Type
          </label>
          <select
            id="provider-kind"
            value={kind}
            disabled={editing}
            onChange={(e) => {
              setKind(e.target.value as ProviderKind)
              setTestResult(undefined)
            }}
            className={`${input} disabled:opacity-60`}
          >
            {(Object.keys(KIND_LABELS) as ProviderKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="provider-name">
            Name
          </label>
          <input
            id="provider-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            placeholder="e.g. Groq"
            className={input}
          />
        </div>
      </div>

      <div>
        <label className={label} htmlFor="provider-url">
          Base URL
        </label>
        <input
          id="provider-url"
          value={baseUrl}
          onChange={(e) => {
            setBaseUrl(e.target.value)
            setTestResult(undefined)
          }}
          required
          type="url"
          placeholder={kind === 'ollama' ? 'http://localhost:11434' : 'https://api.example.com/v1'}
          className={input}
        />
        <p className="mt-1 text-xs text-zinc-500">
          {kind === 'ollama'
            ? 'The URL is reached from the backend. In Docker Compose use http://ollama:11434; for Ollama on your own machine use http://host.docker.internal:11434.'
            : 'Usually ends in /v1. The backend calls {base URL}/models and {base URL}/chat/completions.'}
        </p>
      </div>

      {showKeyField && (
        <div>
          <label className={label} htmlFor="provider-key">
            API key
          </label>
          <div className="relative">
            <input
              id="provider-key"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value)
                setTestResult(undefined)
              }}
              type={showKey ? 'text' : 'password'}
              autoComplete="off"
              disabled={removeKey}
              placeholder={
                provider?.has_key
                  ? 'Saved — leave blank to keep the current key'
                  : 'Optional for local servers'
              }
              className={`${input} pr-10 disabled:opacity-60`}
            />
            <button
              type="button"
              onClick={() => setShowKey((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
              aria-label={showKey ? 'Hide API key' : 'Show API key'}
            >
              {showKey ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>
          {provider?.has_key && (
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={removeKey}
                onChange={(e) => {
                  setRemoveKey(e.target.checked)
                  if (e.target.checked) setApiKey('')
                }}
              />
              Remove saved key
            </label>
          )}
          <p className="mt-1 text-xs text-zinc-500">
            Encrypted before it is stored and never sent back to the browser.
          </p>
          {keyBlocked && (
            <p className="mt-1 text-xs text-red-500">
              The backend has no ENCRYPTION_KEY set, so it can’t store API keys.
            </p>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={runTest}
          disabled={testing || !baseUrl}
          className={secondaryButton}
        >
          Test connection
        </button>
        <HealthBadge health={testResult} checking={testing} />
      </div>

      {saveError && (
        <p className="text-sm text-red-500" role="alert">
          {errorMessage(saveError)}
        </p>
      )}

      <div className="flex justify-end gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <button type="button" onClick={onCancel} className={secondaryButton}>
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving || keyBlocked}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving ? 'Saving…' : editing ? 'Save changes' : 'Add provider'}
        </button>
      </div>
    </form>
  )
}
