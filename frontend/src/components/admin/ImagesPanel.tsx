import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { getImageSettings, saveImageSettings, testImage } from '../../api/images'
import type { ImageEngine, ImageSettings } from '../../types/api'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
const SIZES = ['512x512', '768x768', '1024x1024', '1024x1536', '1536x1024']

const ENGINES: Record<
  Exclude<ImageEngine, ''>,
  { label: string; hint: string; base_url?: string; model?: string }
> = {
  pollinations: {
    label: 'Pollinations (free, no key)',
    hint: 'Free public service, no account needed (about one image every 15–20 seconds per server). Adds a small watermark. A free token from auth.pollinations.ai raises the limit.',
  },
  openai: {
    label: 'OpenAI-compatible',
    hint: 'OpenAI (gpt-image-1, dall-e-3) or any service with an /images/generations API.',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-image-1',
  },
  automatic1111: {
    label: 'Automatic1111 / Stable Diffusion WebUI',
    hint: 'Your own Stable Diffusion WebUI started with --api.',
    base_url: 'http://localhost:7860',
  },
}

export default function ImagesPanel() {
  const settings = useQuery({ queryKey: ['admin', 'images'], queryFn: getImageSettings })
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Images</h2>
        <p className="text-sm text-zinc-500">
          Lets chats create pictures. People turn it on with the 🎨 Image button next to the message
          box, and models can also make images with the “Image” tool.
        </p>
      </div>
      {settings.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {settings.isError && <p className="text-sm text-red-500">{errorMessage(settings.error)}</p>}
      {settings.data && <ImagesForm data={settings.data} />}
    </div>
  )
}

/** Starts from the saved settings, so the form never shows defaults first. */
function ImagesForm({ data }: { data: ImageSettings }) {
  const queryClient = useQueryClient()
  const [engine, setEngine] = useState<ImageEngine>(data.engine)
  const [baseUrl, setBaseUrl] = useState(data.base_url)
  const [model, setModel] = useState(data.model)
  const [size, setSize] = useState(data.size)
  const [apiKey, setApiKey] = useState('')
  const [prompt, setPrompt] = useState('A lighthouse on a cliff at sunset, watercolor')

  const save = useMutation({
    mutationFn: () =>
      saveImageSettings({
        engine,
        base_url: baseUrl,
        model,
        size,
        ...(apiKey ? { api_key: apiKey } : {}),
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['admin', 'images'], saved)
      // The composer's Image button and the tools menu depend on this.
      queryClient.invalidateQueries({ queryKey: ['config'] })
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      setApiKey('')
    },
  })
  const test = useMutation({ mutationFn: () => testImage(prompt) })
  const needsUrl = engine === 'openai' || engine === 'automatic1111'
  const keyLabel =
    engine === 'openai'
      ? 'API key'
      : engine === 'pollinations'
        ? 'Token (optional, for higher limits)'
        : 'Login (user:password, optional)'

  return (
    <>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          test.reset()
          save.mutate()
        }}
        className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
      >
        <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
          <div>
            <label htmlFor="img-engine" className="mb-1 block text-sm font-medium">
              Image engine
            </label>
            <select
              id="img-engine"
              value={engine}
              onChange={(e) => {
                const next = e.target.value as ImageEngine
                setEngine(next)
                test.reset()
                // Fill in the usual address and model the first time.
                if (next && next !== engine) {
                  setBaseUrl(ENGINES[next].base_url ?? '')
                  setModel(ENGINES[next].model ?? '')
                }
              }}
              className={input}
            >
              <option value="">Off</option>
              {(Object.keys(ENGINES) as (keyof typeof ENGINES)[]).map((k) => (
                <option key={k} value={k}>
                  {ENGINES[k].label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="img-size" className="mb-1 block text-sm font-medium">
              Size
            </label>
            <select
              id="img-size"
              value={size}
              onChange={(e) => setSize(e.target.value)}
              className={input}
            >
              {SIZES.map((s) => (
                <option key={s} value={s}>
                  {s.replace('x', ' × ')}
                </option>
              ))}
            </select>
          </div>
        </div>
        {engine && <p className="text-xs text-zinc-500">{ENGINES[engine].hint}</p>}
        {needsUrl && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="img-url" className="mb-1 block text-sm font-medium">
                Base URL
              </label>
              <input
                id="img-url"
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                required
                className={input}
              />
            </div>
            {engine === 'openai' && (
              <div>
                <label htmlFor="img-model" className="mb-1 block text-sm font-medium">
                  Model
                </label>
                <input
                  id="img-model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  required
                  placeholder="gpt-image-1"
                  className={input}
                />
              </div>
            )}
          </div>
        )}
        {engine && (
          <div>
            <label htmlFor="img-key" className="mb-1 block text-sm font-medium">
              {keyLabel}
            </label>
            <input
              id="img-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                data.has_key
                  ? 'Saved — leave blank to keep it'
                  : engine === 'openai'
                    ? 'sk-…'
                    : engine === 'pollinations'
                      ? 'Leave blank to use the free anonymous tier'
                      : 'Only if started with --api-auth'
              }
              className={input}
            />
            <p className="mt-1 text-xs text-zinc-500">
              Encrypted before it is stored and never sent back to the browser.
            </p>
          </div>
        )}
        {save.error && <p className="text-sm text-red-500">{errorMessage(save.error)}</p>}
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Save
          </button>
          {save.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
        </div>
      </form>

      {data.engine && (
        <div className="space-y-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <h3 className="font-medium">Try it</h3>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              test.mutate()
            }}
            className="flex gap-2"
          >
            <input
              aria-label="Test prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              required
              className={input}
            />
            <button type="submit" className={button} disabled={test.isPending}>
              {test.isPending ? 'Creating…' : 'Create'}
            </button>
          </form>
          {test.error && <p className="text-sm text-red-500">{errorMessage(test.error)}</p>}
          {test.data && !test.data.ok && <p className="text-sm text-red-500">{test.data.error}</p>}
          {test.data?.data_url && (
            <img
              src={test.data.data_url}
              alt={prompt}
              className="w-full max-w-xs rounded-xl border border-zinc-200 dark:border-zinc-800"
            />
          )}
        </div>
      )}
    </>
  )
}
