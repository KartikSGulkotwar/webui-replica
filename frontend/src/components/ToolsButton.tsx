import { useEffect, useRef, useState } from 'react'
import type { ToolInfo } from '../types/api'
import { CheckIcon } from './icons'

const WrenchIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
)

interface Props {
  tools: ToolInfo[]
  selected: string[]
  onToggle: (id: string) => void
  disabled?: boolean
}

/** Lets the model call tools (calculator, time, web page) for this message. */
export default function ToolsButton({ tools, selected, onToggle, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const active = tools.filter((t) => selected.includes(t.id))

  useEffect(() => {
    if (!open) return
    const close = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  if (!tools.length) return null
  return (
    <div ref={ref} className="relative self-end">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        className={`flex items-center gap-1 rounded-xl p-2 hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800 ${
          active.length ? 'text-indigo-500' : 'text-zinc-500'
        }`}
        aria-label={active.length ? `Tools (${active.length} on)` : 'Tools'}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Let the model use tools"
      >
        <WrenchIcon />
        {active.length > 0 && <span className="text-xs font-semibold">{active.length}</span>}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-20 mb-2 w-72 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          <p className="px-3 py-1.5 text-xs font-medium text-zinc-500">Tools the model may use</p>
          {tools.map((t) => {
            const on = selected.includes(t.id)
            return (
              <button
                key={t.id}
                type="button"
                role="menuitemcheckbox"
                aria-checked={on}
                onClick={() => onToggle(t.id)}
                className="flex w-full items-start gap-2 rounded-md px-3 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <span aria-hidden="true">{t.emoji}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm">{t.label}</span>
                  <span className="block text-xs text-zinc-500">{t.summary}</span>
                </span>
                {on && <CheckIcon className="mt-0.5 shrink-0 text-indigo-500" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
