import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import {
  getEmbeddingSettings,
  reindexEmbeddings,
  saveEmbeddingSettings,
  testEmbeddings,
} from '../../api/knowledge'
import type { EmbeddingEngine } from '../../types/api'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'

const PRESETS: Record<
  Exclude<EmbeddingEngine, ''>,
  { base_url: string; model: string; hint: string }
> = {
  ollama: {
    base_url: 'http://ollama:11434',
    model: 'nomic-embed-text',
    hint: 'Free and local. Download the model first: ollama pull nomic-embed-text',
  },
  openai: {
    base_url: 'https://api.openai.com/v1',
    model: 'text-embedding-3-small',
    hint: 'Any /embeddings API: OpenAI, Voyage AI (https://api.voyageai.com/v1, voyage-3.5), and others.',
  },
}

export default function DocumentsPanel() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['admin', 'embeddings'], queryFn: getEmbeddingSettings })
  const [engine, setEngine] = useState<EmbeddingEngine>('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')

  useEffect(() => {
    if (!settings.data) return
    setEngine(settings.data.engine)
    setBaseUrl(settings.data.base_url)
    setModel(settings.data.model)
  }, [settings.data])

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin', 'embeddings'] })
  const save = useMutation({
    mutationFn: () =>
      saveEmbeddingSettings({
        engine,
        base_url: baseUrl,
        model,
        ...(apiKey ? { api_key: apiKey } : {}),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['admin', 'embeddings'], data)
      setApiKey('')
    },
  })
  const test = useMutation({ mutationFn: testEmbeddings })
  const reindex = useMutation({ mutationFn: reindexEmbeddings, onSuccess: refresh })

  const data = settings.data
  const stale = data && data.engine && data.embedded_chunks < data.total_chunks

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Document search</h2>
        <p className="text-sm text-zinc-500">
          Chats with documents always use keyword search (BM25). Add an embedding model to also
          search by meaning: results from both are merged.
        </p>
      </div>
      {settings.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {settings.isError && <p className="text-sm text-red-500">{errorMessage(settings.error)}</p>}
      {data && (
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            test.reset()
            save.mutate()
          }}
          className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
        >
          <div>
            <label htmlFor="emb-engine" className="mb-1 block text-sm font-medium">
              Embedding model
            </label>
            <select
              id="emb-engine"
              value={engine}
              onChange={(e) => {
                const next = e.target.value as EmbeddingEngine
                setEngine(next)
                if (next && !baseUrl && !model) {
                  setBaseUrl(PRESETS[next].base_url)
                  setModel(PRESETS[next].model)
                }
              }}
              className={input}
            >
              <option value="">None: keyword search only</option>
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI-compatible API</option>
            </select>
            {engine && <p className="mt-1 text-xs text-zinc-500">{PRESETS[engine].hint}</p>}
          </div>
          {engine && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="emb-url" className="mb-1 block text-sm font-medium">
                  Base URL
                </label>
                <input
                  id="emb-url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  required
                  className={input}
                />
              </div>
              <div>
                <label htmlFor="emb-model" className="mb-1 block text-sm font-medium">
                  Model
                </label>
                <input
                  id="emb-model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  required
                  className={input}
                />
              </div>
              {engine === 'openai' && (
                <div className="sm:col-span-2">
                  <label htmlFor="emb-key" className="mb-1 block text-sm font-medium">
                    API key
                  </label>
                  <input
                    id="emb-key"
                    type="password"
                    autoComplete="off"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={
                      data.has_key ? 'Saved — leave blank to keep it' : 'Required for hosted APIs'
                    }
                    className={input}
                  />
                </div>
              )}
            </div>
          )}
          {save.error && <p className="text-sm text-red-500">{errorMessage(save.error)}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={save.isPending}
              className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              Save
            </button>
            {data.engine && (
              <button
                type="button"
                className={button}
                disabled={test.isPending}
                onClick={() => test.mutate()}
              >
                Test
              </button>
            )}
            {save.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
            {test.data && (
              <span className={`text-sm ${test.data.ok ? 'text-emerald-600' : 'text-red-500'}`}>
                {test.data.ok
                  ? `Working · ${test.data.dimensions}-dimensional vectors`
                  : test.data.error}
              </span>
            )}
            {test.error && <span className="text-sm text-red-500">{errorMessage(test.error)}</span>}
          </div>
        </form>
      )}

      {data && (
        <div className="space-y-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <h3 className="font-medium">Index</h3>
          <p className="text-sm text-zinc-500">
            {data.total_chunks} passages stored
            {data.engine ? `, ${data.embedded_chunks} embedded with ${data.model}` : ''}.
          </p>
          {stale && (
            <p className="text-sm text-amber-600 dark:text-amber-400">
              Some passages aren’t embedded with the current model (it was changed, or embedding
              failed). Re-index so semantic search covers every document.
            </p>
          )}
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={button}
              disabled={reindex.isPending || !data.total_chunks}
              onClick={() => reindex.mutate()}
            >
              {reindex.isPending ? 'Re-indexing…' : 'Re-index all documents'}
            </button>
            {reindex.data && (
              <span className="text-sm text-emerald-600">
                Re-indexed {reindex.data.reindexed_chunks} passages.
              </span>
            )}
            {reindex.error && (
              <span className="text-sm text-red-500">{errorMessage(reindex.error)}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
