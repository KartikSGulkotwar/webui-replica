import type { ReactNode } from 'react'

const svg = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
}

export const GlobeIcon = () => (
  <svg {...svg}>
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
)

export const ImageIcon = () => (
  <svg {...svg}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <circle cx="9" cy="9" r="2" />
    <path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21" />
  </svg>
)

interface Props {
  on: boolean
  onToggle: () => void
  label: string
  icon: ReactNode
  /** Tooltips for each state. */
  titleOn: string
  titleOff: string
  disabled?: boolean
}

/** A per-message option next to the message box (Web search, Image). */
export default function ComposerToggle({
  on,
  onToggle,
  label,
  icon,
  titleOn,
  titleOff,
  disabled,
}: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={on}
      aria-label={label}
      title={on ? titleOn : titleOff}
      className={`flex items-center gap-1 self-end rounded-xl p-2 text-xs font-medium disabled:opacity-40 ${
        on
          ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300'
          : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'
      }`}
    >
      {icon}
      {on && <span>{label}</span>}
    </button>
  )
}
