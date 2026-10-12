import { useState } from 'react'
import type { Source } from '../types/api'

/** Numbered citations under a reply; click one to read the exact passage. */
export default function SourcesList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (!sources.length) return null
  const current = sources.find((s) => s.n === open)
  return (
    <div className="space-y-1.5" aria-label="Sources">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-medium text-zinc-500">Sources</span>
        {sources.map((s) => (
          <button
            key={s.n}
            type="button"
            onClick={() => setOpen(open === s.n ? null : s.n)}
            aria-expanded={open === s.n}
            className={`inline-flex max-w-[16rem] items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
              open === s.n
                ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                : 'border-zinc-200 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800'
            }`}
            title={s.filename}
          >
            <span className="font-semibold">[{s.n}]</span>
            <span className="truncate">{s.filename}</span>
            {s.page != null && <span className="shrink-0">· p.{s.page}</span>}
          </button>
        ))}
      </div>
      {current && (
        <blockquote className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-lg border-l-4 border-indigo-400 bg-zinc-50 px-3 py-2 text-sm text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          <p className="mb-1 text-xs font-medium text-zinc-500">
            [{current.n}] {current.filename}
            {current.page != null ? `, page ${current.page}` : ''}
          </p>
          {current.text}
        </blockquote>
      )}
    </div>
  )
}
