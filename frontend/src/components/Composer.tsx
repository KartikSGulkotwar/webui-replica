import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { SendIcon, StopIcon } from './icons'

interface Props {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled: boolean
  disabledReason?: string
}

export default function Composer({ onSend, onStop, isStreaming, disabled, disabledReason }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  // Grow with content up to a cap, then scroll.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])

  const canSend = !disabled && !isStreaming && text.trim().length > 0

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    if (!canSend) return
    onSend(text.trim())
    setText('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl px-3 pb-3 sm:px-4 sm:pb-4">
      <div className="flex items-end gap-2 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm focus-within:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900 dark:focus-within:border-zinc-600">
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          autoFocus
          placeholder={disabled && disabledReason ? disabledReason : 'Send a message'}
          className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-zinc-400"
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="rounded-xl bg-zinc-900 p-2 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            aria-label="Stop generating"
            title="Stop"
          >
            <StopIcon />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            className="rounded-xl bg-indigo-600 p-2 text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-zinc-300 dark:disabled:bg-zinc-700"
            aria-label="Send message"
            title="Send (Enter)"
          >
            <SendIcon />
          </button>
        )}
      </div>
      <p className="mt-1.5 text-center text-xs text-zinc-500">
        Enter to send · Shift+Enter for a new line
      </p>
    </form>
  )
}
