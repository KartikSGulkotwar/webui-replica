import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import type { Conversation } from '../types/api'
import { ArchiveIcon, CheckIcon, DotsIcon, PencilIcon, PinIcon, TrashIcon, XIcon } from './icons'

interface Props {
  conversation: Conversation
  active: boolean
  onRename: (title: string) => void
  onDelete: () => void
  onTogglePin: () => void
  onArchive: () => void
  onNavigate: () => void
}

type Mode = 'view' | 'rename' | 'confirm-delete'

const iconButton =
  'rounded p-2 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100 md:p-1'
const menuItem =
  'flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800'

/** Rendered in a portal with fixed position so the scrolling sidebar can't clip it. */
function ItemMenu({
  anchor,
  conversation,
  onClose,
  onPick,
}: {
  anchor: HTMLElement
  conversation: Conversation
  onClose: () => void
  onPick: (action: 'pin' | 'rename' | 'archive' | 'delete') => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    const r = anchor.getBoundingClientRect()
    const height = ref.current?.offsetHeight ?? 160
    const below = r.bottom + 4 + height < window.innerHeight
    setPos({ top: below ? r.bottom + 4 : r.top - height - 4, left: Math.max(8, r.right - 176) })
  }, [anchor])

  useEffect(() => {
    const close = (e: Event) => {
      if (
        e instanceof PointerEvent &&
        (ref.current?.contains(e.target as Node) || anchor.contains(e.target as Node))
      )
        return
      onClose()
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', esc)
    window.addEventListener('resize', close)
    document.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', esc)
      window.removeEventListener('resize', close)
      document.removeEventListener('scroll', close, true)
    }
  }, [anchor, onClose])

  return createPortal(
    <div
      ref={ref}
      role="menu"
      style={{ position: 'fixed', top: pos?.top ?? -9999, left: pos?.left ?? 0 }}
      className="z-50 w-44 rounded-lg border border-zinc-200 bg-white p-1 text-zinc-900 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
    >
      <button type="button" role="menuitem" className={menuItem} onClick={() => onPick('pin')}>
        <PinIcon width={14} height={14} /> {conversation.pinned ? 'Unpin' : 'Pin'}
      </button>
      <button type="button" role="menuitem" className={menuItem} onClick={() => onPick('rename')}>
        <PencilIcon width={14} height={14} /> Rename
      </button>
      <button type="button" role="menuitem" className={menuItem} onClick={() => onPick('archive')}>
        <ArchiveIcon width={14} height={14} /> Archive
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${menuItem} text-red-600 dark:text-red-400`}
        onClick={() => onPick('delete')}
      >
        <TrashIcon width={14} height={14} /> Delete
      </button>
    </div>,
    document.body,
  )
}

export default function ConversationItem({
  conversation,
  active,
  onRename,
  onDelete,
  onTogglePin,
  onArchive,
  onNavigate,
}: Props) {
  const [mode, setMode] = useState<Mode>('view')
  const [draft, setDraft] = useState(conversation.title)
  const [menuOpen, setMenuOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)

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
        className="min-w-0 flex-1 px-2 py-1.5"
        title={conversation.title}
        aria-current={active ? 'page' : undefined}
      >
        <span className="flex items-center gap-1">
          {conversation.pinned && (
            <PinIcon
              width={12}
              height={12}
              className="shrink-0 text-zinc-400"
              aria-label="Pinned"
            />
          )}
          <span className="truncate">{conversation.title}</span>
        </span>
        {conversation.snippet && (
          <span className="mt-0.5 line-clamp-2 block text-xs text-zinc-500">
            {conversation.snippet}
          </span>
        )}
      </Link>
      {/* Always visible on touch screens, the active row, and while open; on hover elsewhere. */}
      <div
        className={`flex shrink-0 items-center self-start pr-1 pt-1 ${
          active || menuOpen
            ? ''
            : 'md:invisible md:group-focus-within:visible md:group-hover:visible'
        }`}
      >
        <button
          ref={menuButtonRef}
          type="button"
          className={iconButton}
          onClick={() => setMenuOpen((o) => !o)}
          aria-label={`Options for ${conversation.title}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          title="Options"
        >
          <DotsIcon width={14} height={14} />
        </button>
      </div>
      {menuOpen && menuButtonRef.current && (
        <ItemMenu
          anchor={menuButtonRef.current}
          conversation={conversation}
          onClose={() => setMenuOpen(false)}
          onPick={(action) => {
            setMenuOpen(false)
            if (action === 'pin') onTogglePin()
            if (action === 'archive') onArchive()
            if (action === 'rename') {
              setDraft(conversation.title)
              setMode('rename')
            }
            if (action === 'delete') setMode('confirm-delete')
          }}
        />
      )}
    </div>
  )
}
