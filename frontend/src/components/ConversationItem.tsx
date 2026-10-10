import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Conversation } from '../types/api'
import { CheckIcon, PencilIcon, TrashIcon, XIcon } from './icons'

interface Props {
  conversation: Conversation
  active: boolean
  onRename: (title: string) => void
  onDelete: () => void
  onNavigate: () => void
}

type Mode = 'view' | 'rename' | 'confirm-delete'

const iconButton =
  'rounded p-1 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100'

export default function ConversationItem({
  conversation,
  active,
  onRename,
  onDelete,
  onNavigate,
}: Props) {
  const [mode, setMode] = useState<Mode>('view')
  const [draft, setDraft] = useState(conversation.title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (mode === 'rename') inputRef.current?.select()
  }, [mode])

  const commitRename = () => {
    const title = draft.trim()
    if (title && title !== conversation.title) onRename(title)
    setMode('view')
  }

  const rowClass = `group relative flex items-center rounded-lg text-sm ${
    active
      ? 'bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
      : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800/60'
  }`

  if (mode === 'rename') {
    return (
      <div className={rowClass}>
        <input
          ref={inputRef}
          value={draft}
          maxLength={200}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitRename()
            if (e.key === 'Escape') {
              setDraft(conversation.title)
              setMode('view')
            }
          }}
          aria-label="Conversation title"
          className="w-full rounded-lg border border-indigo-500 bg-white px-2 py-1.5 outline-none dark:bg-zinc-900"
        />
      </div>
    )
  }

  if (mode === 'confirm-delete') {
    return (
      <div className={`${rowClass} gap-1 px-2 py-1.5`}>
        <span className="flex-1 truncate text-red-600 dark:text-red-400">
          Delete “{conversation.title}”?
        </span>
        <button
          type="button"
          className={iconButton}
          onClick={onDelete}
          aria-label="Confirm delete"
          autoFocus
        >
          <CheckIcon />
        </button>
        <button
          type="button"
          className={iconButton}
          onClick={() => setMode('view')}
          aria-label="Cancel delete"
        >
          <XIcon />
        </button>
      </div>
    )
  }

  return (
    <div className={rowClass}>
      <Link
        to={`/c/${conversation.id}`}
        onClick={onNavigate}
        className="min-w-0 flex-1 truncate px-2 py-1.5"
        title={conversation.title}
        aria-current={active ? 'page' : undefined}
      >
        {conversation.title}
      </Link>
      {/* Always visible on touch screens and the active row; on hover elsewhere. */}
      <div
        className={`flex shrink-0 items-center pr-1 ${
          active ? '' : 'md:invisible md:group-focus-within:visible md:group-hover:visible'
        }`}
      >
        <button
          type="button"
          className={iconButton}
          onClick={() => {
            setDraft(conversation.title)
            setMode('rename')
          }}
          aria-label={`Rename ${conversation.title}`}
          title="Rename"
        >
          <PencilIcon width={14} height={14} />
        </button>
        <button
          type="button"
          className={iconButton}
          onClick={() => setMode('confirm-delete')}
          aria-label={`Delete ${conversation.title}`}
          title="Delete"
        >
          <TrashIcon width={14} height={14} />
        </button>
      </div>
    </div>
  )
}
