import { useState } from 'react'
import { describeArgs } from '../lib/tools'
import type { ToolInfo, ToolTrace } from '../types/api'

/** The tools a reply used, in order; click one to see its input and output. */
export default function ToolCallsView({
  calls,
  tools,
}: {
  calls: ToolTrace[]
  tools?: ToolInfo[]
}) {
  const [open, setOpen] = useState<string | null>(null)
  if (!calls.length) return null
  return (
    <div className="space-y-1" aria-label="Tools used">
      {calls.map((c) => {
        const info = tools?.find((t) => t.id === c.name)
        const running = c.output === undefined
        const input = describeArgs(c.arguments)
        const short = !running && !c.error && c.output!.length <= 60 && !c.output!.includes('\n')
        return (
          <div key={c.id} className="text-sm">
            <button
              type="button"
              onClick={() => setOpen(open === c.id ? null : c.id)}
              aria-expanded={open === c.id}
              className={`inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-left text-xs ${
                c.error
                  ? 'border-red-300 text-red-700 dark:border-red-900 dark:text-red-300'
                  : 'border-zinc-200 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800'
              }`}
            >
              <span aria-hidden="true">{info?.emoji ?? '🔧'}</span>
              <span className="font-medium">{info?.label ?? c.name}</span>
              {input && <span className="truncate font-mono">· {input}</span>}
              {running ? (
                <span className="flex items-center gap-1 text-zinc-500">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" /> running…
                </span>
              ) : c.error ? (
                <span>· failed</span>
              ) : short ? (
                <span className="font-mono text-zinc-900 dark:text-zinc-100">→ {c.output}</span>
              ) : (
                <span>· done</span>
              )}
            </button>
            {open === c.id && (
              <div className="mt-1 space-y-1 rounded-lg bg-zinc-50 p-2 text-xs dark:bg-zinc-900">
                <p className="font-medium text-zinc-500">Input</p>
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono">
                  {JSON.stringify(c.arguments, null, 2)}
                </pre>
                <p className="font-medium text-zinc-500">{c.error ? 'Error' : 'Output'}</p>
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap font-mono">
                  {running ? '…' : c.output}
                </pre>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
