import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { getWebSearchSettings, saveWebSearchSettings, testWebSearch } from '../../api/webSearch'
import type { WebSearchEngine, WebSearchSettings } from '../../types/api'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'

const ENGINES: Record<Exclude<WebSearchEngine, ''>, { label: string; hint: string }> = {
  duckduckgo: {
    label: 'DuckDuckGo (no key)',
    hint: 'Free, no account needed. Rotates between several search backends; busy servers can be rate-limited.',
  },
  searxng: {
    label: 'SearXNG',
    hint: 'Your own SearXNG instance. Enable the JSON format in its settings.yml (search → formats).',
  },
  brave: {
    label: 'Brave Search',
    hint: 'API key from api-dashboard.search.brave.com (has a free tier).',
  },
  tavily: {
    label: 'Tavily',
    hint: 'API key from app.tavily.com (1,000 free searches a month).',
  },
}

export default function WebSearchPanel() {
  const settings = useQuery({ queryKey: ['admin', 'web-search'], queryFn: getWebSearchSettings })
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Web search</h2>
        <p className="text-sm text-zinc-500">
          Lets chats search the internet. People turn it on with the 🌐 button next to the message
          box; the reply cites the pages it read. Models can also search on their own through the
          “Web search” tool.
        </p>
      </div>
      {settings.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {settings.isError && <p className="text-sm text-red-500">{errorMessage(settings.error)}</p>}
      {settings.data && <WebSearchForm data={settings.data} />}
    </div>
  )
}

/** Starts from the saved settings, so the form never shows defaults first. */
function WebSearchForm({ data }: { data: WebSearchSettings }) {
  const queryClient = useQueryClient()
  const [engine, setEngine] = useState<WebSearchEngine>(data.engine)
  const [baseUrl, setBaseUrl] = useState(data.base_url)
  const [count, setCount] = useState(data.result_count)
  const [apiKey, setApiKey] = useState('')
  const [query, setQuery] = useState('latest Python release')

  const save = useMutation({
    mutationFn: () =>
      saveWebSearchSettings({
        engine,
        base_url: baseUrl,
        result_count: count,
        ...(apiKey ? { api_key: apiKey } : {}),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['admin', 'web-search'], data)
      // The composer's globe button and the tools menu depend on this.
      queryClient.invalidateQueries({ queryKey: ['config'] })
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      setApiKey('')
    },
  })
  const test = useMutation({ mutationFn: () => testWebSearch(query) })

  const needsKey = engine === 'brave' || engine === 'tavily'

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
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <div>
            <label htmlFor="ws-engine" className="mb-1 block text-sm font-medium">
              Search engine
            </label>
            <select
              id="ws-engine"
              value={engine}
              onChange={(e) => {
                setEngine(e.target.value as WebSearchEngine)
                test.reset()
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
            <label htmlFor="ws-count" className="mb-1 block text-sm font-medium">
              Pages to read
            </label>
            <input
              id="ws-count"
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) => setCount(Number(e.target.value) || 1)}
              className={input}
            />
          </div>
        </div>
        {engine && <p className="text-xs text-zinc-500">{ENGINES[engine].hint}</p>}
        {engine === 'searxng' && (
          <div>
            <label htmlFor="ws-url" className="mb-1 block text-sm font-medium">
              SearXNG URL
            </label>
            <input
              id="ws-url"
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://searxng:8080"
              required
              className={input}
            />
          </div>
        )}
        {needsKey && (
          <div>
            <label htmlFor="ws-key" className="mb-1 block text-sm font-medium">
              API key
            </label>
            <input
              id="ws-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={data.has_key ? 'Saved — leave blank to keep it' : 'Required'}
              className={input}
            />
            <p className="mt-1 text-xs text-zinc-500">
              Encrypted before it is stored and never sent back to the browser.
            </p>
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
          {save.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
        </div>
      </form>

      {data.engine && (
        <div className="space-y-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <h3 className="font-medium">Try a search</h3>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              test.mutate()
            }}
            className="flex gap-2"
          >
            <input
              aria-label="Test search query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              required
              className={input}
            />
            <button type="submit" className={button} disabled={test.isPending}>
              {test.isPending ? 'Searching…' : 'Search'}
            </button>
          </form>
          {test.error && <p className="text-sm text-red-500">{errorMessage(test.error)}</p>}
          {test.data && !test.data.ok && <p className="text-sm text-red-500">{test.data.error}</p>}
          {test.data?.ok && (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {test.data.results.length === 0 && <li className="list-none">No results.</li>}
              {test.data.results.map((r) => (
                <li key={r.url}>
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    {r.title}
                  </a>
                  <span className="block truncate text-xs text-zinc-500">{r.url}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </>
  )
}
