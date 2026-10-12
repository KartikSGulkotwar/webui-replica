import { lazy, memo, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Rating, Role, Source } from '../types/api'
import SourcesList from './SourcesList'
import { CheckIcon, CopyIcon, PencilIcon, RefreshIcon, ThumbDownIcon, ThumbUpIcon } from './icons'

// Markdown + syntax highlighting is most of the bundle; load it after first paint.
const Markdown = lazy(() => import('./Markdown'))

function PlainText({ content }: { content: string }) {
  return <div className="whitespace-pre-wrap break-words leading-7">{content}</div>
}

export interface MessageActions {
  rating?: Rating | null
  onRate?: (rating: Rating | null, comment?: string) => void
  /** Only passed for the last reply. */
  onRegenerate?: () => void
  /** User messages: resend with new text. */
  onEdit?: (content: string) => void
  /** True while a reply is streaming: actions that start a new one are off. */
  busy?: boolean
}

interface Props {
  role: Role
  content: string
  /** For assistant messages: which model wrote it. */
  model?: { name: string; provider: string }
  streaming?: boolean
  /** Document passages the reply cites as [1], [2]… */
  sources?: Source[] | null
  /** Omit for read-only views (shared chats, in-flight messages). */
  actions?: MessageActions
}

function ActionButton({
  label,
  onClick,
  active,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  active?: boolean
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={`rounded-md p-1.5 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-zinc-800 ${
        active
          ? 'text-indigo-600 dark:text-indigo-400'
          : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100'
      }`}
    >
      {children}
    </button>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <ActionButton
      label={copied ? 'Copied' : 'Copy'}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          // clipboard blocked (insecure context); nothing useful to do
        }
      }}
    >
      {copied ? <CheckIcon width={15} height={15} /> : <CopyIcon width={15} height={15} />}
    </ActionButton>
  )
}

function EditBox({
  initial,
  onSave,
  onCancel,
}: {
  initial: string
  onSave: (text: string) => void
  onCancel: () => void
}) {
  const [text, setText] = useState(initial)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`
  }, [text])
  const trimmed = text.trim()
  return (
    <div className="w-full max-w-[85%] space-y-2 rounded-2xl border border-zinc-300 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <textarea
        ref={ref}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && trimmed) {
            e.preventDefault()
            onSave(trimmed)
          }
        }}
        aria-label="Edit message"
        className="max-h-80 w-full resize-none bg-transparent outline-none"
      />
      <div className="flex justify-end gap-2 text-sm">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => onSave(trimmed)}
          disabled={!trimmed}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          Save &amp; send
        </button>
      </div>
      <p className="text-xs text-zinc-500">Later messages in this chat will be replaced.</p>
    </div>
  )
}

function FeedbackComment({ onSubmit }: { onSubmit: (comment: string) => void }) {
  const [comment, setComment] = useState('')
  const [sent, setSent] = useState(false)
  if (sent) return <p className="text-xs text-zinc-500">Thanks for the feedback.</p>
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(comment.trim())
        setSent(true)
      }}
      className="flex max-w-md items-center gap-2"
    >
      <input
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        maxLength={1000}
        placeholder="What went wrong? (optional)"
        aria-label="Feedback comment"
        className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-900"
      />
      <button
        type="submit"
        className="rounded-lg border border-zinc-300 px-2 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
      >
        Send
      </button>
    </form>
  )
}

function MessageBubble({ role, content, model, streaming, sources, actions }: Props) {
  const [editing, setEditing] = useState(false)
  const [askComment, setAskComment] = useState(false)

  if (role === 'user') {
    if (editing && actions?.onEdit) {
      return (
        <div className="flex justify-end">
          <EditBox
            initial={content}
            onCancel={() => setEditing(false)}
            onSave={(text) => {
              setEditing(false)
              actions.onEdit?.(text)
            }}
          />
        </div>
      )
    }
    return (
      <div className="group flex flex-col items-end gap-1">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-zinc-100 px-4 py-2.5 dark:bg-zinc-800">
          {content}
        </div>
        {actions && (
          <div className="flex gap-0.5 opacity-100 transition-opacity md:opacity-0 md:focus-within:opacity-100 md:group-hover:opacity-100">
            <CopyButton text={content} />
            {actions.onEdit && (
              <ActionButton label="Edit" onClick={() => setEditing(true)} disabled={actions.busy}>
                <PencilIcon width={15} height={15} />
              </ActionButton>
            )}
          </div>
        )}
      </div>
    )
  }

  const rate = (value: 1 | -1) => {
    const next = actions?.rating === value ? null : value
    actions?.onRate?.(next)
    setAskComment(next === -1)
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
      {sources && sources.length > 0 && <SourcesList sources={sources} />}
      {actions && content && (
        <div className="flex flex-col gap-1">
          <div className="-ml-1.5 flex gap-0.5">
            <CopyButton text={content} />
            {actions.onRegenerate && (
              <ActionButton
                label="Regenerate"
                onClick={actions.onRegenerate}
                disabled={actions.busy}
              >
                <RefreshIcon width={15} height={15} />
              </ActionButton>
            )}
            {actions.onRate && (
              <>
                <ActionButton
                  label="Good response"
                  onClick={() => rate(1)}
                  active={actions.rating === 1}
                >
                  <ThumbUpIcon width={15} height={15} />
                </ActionButton>
                <ActionButton
                  label="Bad response"
                  onClick={() => rate(-1)}
                  active={actions.rating === -1}
                >
                  <ThumbDownIcon width={15} height={15} />
                </ActionButton>
              </>
            )}
          </div>
          {askComment && actions.rating === -1 && (
            <FeedbackComment onSubmit={(comment) => actions.onRate?.(-1, comment)} />
          )}
        </div>
      )}
    </div>
  )
}

export default memo(MessageBubble)
