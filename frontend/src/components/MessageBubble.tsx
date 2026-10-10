import { lazy, memo, Suspense } from 'react'
import type { Role } from '../types/api'

// Markdown + syntax highlighting is most of the bundle; load it after first paint.
const Markdown = lazy(() => import('./Markdown'))

function PlainText({ content }: { content: string }) {
  return <div className="whitespace-pre-wrap break-words leading-7">{content}</div>
}

interface Props {
  role: Role
  content: string
  /** For assistant messages: which model wrote it. */
  model?: { name: string; provider: string }
  streaming?: boolean
}

function MessageBubble({ role, content, model, streaming }: Props) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-zinc-100 px-4 py-2.5 dark:bg-zinc-800">
          {content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5">
      {model && (
        <span
          className="inline-flex w-fit max-w-full items-center gap-1 truncate rounded-full border border-zinc-200 px-2 py-0.5 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400"
          title={`${model.provider} · ${model.name}`}
        >
          <span className="font-medium text-zinc-700 dark:text-zinc-300">{model.name}</span>
          {model.provider && <span>· {model.provider}</span>}
        </span>
      )}
      {content ? (
        <div className={streaming ? 'streaming-cursor' : undefined}>
          <Suspense fallback={<PlainText content={content} />}>
            <Markdown content={content} />
          </Suspense>
        </div>
      ) : (
        streaming && (
          <div className="flex gap-1 py-2" aria-label="Waiting for response">
            <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-400" />
          </div>
        )
      )}
    </div>
  )
}

export default memo(MessageBubble)
