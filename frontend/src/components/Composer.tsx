import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { SendIcon, StopIcon } from './icons'
import { useT } from '../lib/i18n'

interface Props {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled: boolean
  disabledReason?: string
  /** Text to put back after a message was rejected before it was saved. */
  restoreText?: string
  /** Shown above the input (e.g. attached documents). */
  above?: ReactNode
  /** Buttons left of the input (e.g. attach). */
  leading?: ReactNode
  /** Buttons right of the input, given a way to add text (e.g. dictation). */
  trailing?: (addText: (text: string) => void) => ReactNode
}

export default function Composer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  disabledReason,
  restoreText,
  above,
  leading,
  trailing,
}: Props) {
  const [text, setText] = useState('')
  const t = useT()
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (restoreText) setText((current) => current || restoreText)
  }, [restoreText])

  // Grow with content up to a cap, then scroll.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])

  const canSend = !disabled && !isStreaming && text.trim().length > 0

  // Dictated text joins what's already typed.
  const addText = (more: string) => {
    setText((current) => (current.trim() ? `${current.replace(/\s+$/, '')} ${more}` : more))
    ref.current?.focus()
  }

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
      {above}
      {/* Phones: the text box gets the whole first row and the buttons go underneath;
          wider screens keep everything on one row. */}
      <div className="flex flex-wrap items-end gap-1 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm focus-within:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900 dark:focus-within:border-zinc-600 sm:flex-nowrap sm:gap-2">
        {leading}
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          autoFocus
          placeholder={disabled && disabledReason ? disabledReason : t('composer.placeholder')}
          className="order-first max-h-[200px] min-w-0 basis-full resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-zinc-400 sm:order-none sm:basis-auto sm:flex-1"
        />
        <span className="flex-1 sm:hidden" aria-hidden="true" />
        {trailing?.(addText)}
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="rounded-xl bg-zinc-900 p-2 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            aria-label={t('composer.stop')}
            title="Stop"
          >
            <StopIcon />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            className="rounded-xl bg-indigo-600 p-2 text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-zinc-300 dark:disabled:bg-zinc-700"
            aria-label={t('composer.send')}
            title="Send (Enter)"
          >
            <SendIcon />
          </button>
        )}
      </div>
      <p className="mt-1.5 text-center text-xs text-zinc-500">{t('composer.hint')}</p>
    </form>
  )
}
