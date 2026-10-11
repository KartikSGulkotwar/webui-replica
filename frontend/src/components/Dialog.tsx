import { useEffect, useRef, type ReactNode } from 'react'
import { XIcon } from './icons'

interface Props {
  title: string
  onClose: () => void
  children: ReactNode
}

/** Accessible modal built on <dialog>: focus trap, Escape and backdrop click close it. */
export default function Dialog({ title, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-label={title}
      className="w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-zinc-200 bg-white p-0 text-zinc-900 shadow-2xl backdrop:bg-black/50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100"
    >
      <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h2 className="font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          aria-label="Close"
        >
          <XIcon />
        </button>
      </div>
      <div className="p-4">{children}</div>
    </dialog>
  )
}
