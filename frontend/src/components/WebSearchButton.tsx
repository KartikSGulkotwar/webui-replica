const GlobeIcon = () => (
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
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
)

interface Props {
  on: boolean
  onToggle: () => void
  disabled?: boolean
}

/** Search the web before answering; the reply cites the pages it read. */
export default function WebSearchButton({ on, onToggle, disabled }: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={on}
      aria-label="Web search"
      title={on ? 'Web search on: replies search the internet first' : 'Search the web'}
      className={`flex items-center gap-1 self-end rounded-xl p-2 text-xs font-medium disabled:opacity-40 ${
        on
          ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300'
          : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'
      }`}
    >
      <GlobeIcon />
      {on && <span>Web search</span>}
    </button>
  )
}
