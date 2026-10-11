import { useMemo, useState } from 'react'
import { Link, useMatch, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  useConversations,
  useDeleteConversation,
  useUpdateConversation,
} from '../hooks/useConversations'
import { useDebounced } from '../hooks/useDebounced'
import { groupByDate } from '../lib/dates'
import type { Conversation } from '../types/api'
import ConversationItem from './ConversationItem'
import { MenuIcon, PlusIcon, SearchIcon, XIcon } from './icons'
import UserMenu from './UserMenu'

interface Props {
  open: boolean
  onClose: () => void
  /** On small screens the sidebar is an overlay that closes after navigating. */
  isMobile: boolean
}

export default function Sidebar({ open, onClose, isMobile }: Props) {
  const activeId = useMatch('/c/:id')?.params.id
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const query = useDebounced(search.trim(), 250)
  const searching = query.length > 0
  const conversations = useConversations({ q: query || undefined })
  const update = useUpdateConversation()
  const remove = useDeleteConversation()

  const list = conversations.data ?? []
  const pinned = searching ? [] : list.filter((c) => c.pinned)
  const groups = useMemo(
    () =>
      searching
        ? []
        : groupByDate(
            (conversations.data ?? []).filter((c) => !c.pinned),
            (c) => c.updated_at,
          ),
    [conversations.data, searching],
  )

  const afterNavigate = () => {
    if (isMobile) onClose()
  }

  const handleDelete = (id: string) => {
    remove.mutate(id)
    if (id === activeId) navigate('/')
  }

  const mutationError = update.error ?? remove.error

  const item = (c: Conversation) => (
    <li key={c.id}>
      <ConversationItem
        conversation={c}
        active={c.id === activeId}
        onNavigate={afterNavigate}
        onRename={(title) => update.mutate({ id: c.id, patch: { title } })}
        onTogglePin={() => update.mutate({ id: c.id, patch: { pinned: !c.pinned } })}
        onArchive={() => {
          update.mutate({ id: c.id, patch: { archived: true } })
          if (c.id === activeId) navigate('/')
        }}
        onDelete={() => handleDelete(c.id)}
      />
    </li>
  )

  return (
    <>
      {isMobile && open && (
        <div className="fixed inset-0 z-30 bg-black/40" onClick={onClose} aria-hidden="true" />
      )}
      <aside
        className={`flex h-full w-64 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 ${
          isMobile
            ? // visibility (not just transform) keeps the closed drawer out of the tab order;
              // transitioning it lets the slide-out animation finish first.
              `fixed inset-y-0 left-0 z-40 transition-[transform,visibility] duration-200 ${open ? 'translate-x-0' : 'invisible -translate-x-full'}`
            : open
              ? ''
              : 'hidden'
        }`}
        aria-label="Conversations"
      >
        <div className="flex items-center gap-1 p-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            aria-label="Close sidebar"
            title="Close sidebar"
          >
            <MenuIcon />
          </button>
          <span className="flex-1 truncate px-1 text-sm font-semibold">WebUI Replica</span>
        </div>

        <div className="px-2 pb-2">
          <Link
            to="/"
            onClick={afterNavigate}
            className="flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            <PlusIcon />
            New chat
          </Link>
          <div className="relative mt-2">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && setSearch('')}
              placeholder="Search chats"
              aria-label="Search chats"
              className="w-full rounded-lg border border-zinc-200 bg-white py-1.5 pl-8 pr-7 text-sm outline-none placeholder:text-zinc-400 focus:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-950 [&::-webkit-search-cancel-button]:hidden"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
                aria-label="Clear search"
              >
                <XIcon width={14} height={14} />
              </button>
            )}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {conversations.isLoading && (
            <div className="space-y-2 px-2 pt-2" aria-label="Loading conversations">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-6 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
              ))}
            </div>
          )}
          {conversations.isError && (
            <div className="px-2 pt-2 text-sm text-red-500">
              <p>Couldn’t load conversations.</p>
              <p className="text-xs text-zinc-500">{errorMessage(conversations.error)}</p>
              <button
                type="button"
                onClick={() => conversations.refetch()}
                className="mt-1 text-xs text-indigo-500 hover:underline"
              >
                Retry
              </button>
            </div>
          )}
          {conversations.isSuccess && list.length === 0 && (
            <p className="px-2 pt-2 text-sm text-zinc-500">
              {searching ? `No chats match “${query}”.` : 'No conversations yet.'}
            </p>
          )}
          {searching && list.length > 0 && (
            <div className="mt-1">
              <h2 className="px-2 pb-1 text-xs font-medium text-zinc-500">
                {list.length} result{list.length === 1 ? '' : 's'}
              </h2>
              <ul className="space-y-0.5">{list.map(item)}</ul>
            </div>
          )}
          {pinned.length > 0 && (
            <div className="mt-1">
              <h2 className="px-2 pb-1 text-xs font-medium text-zinc-500">Pinned</h2>
              <ul className="space-y-0.5">{pinned.map(item)}</ul>
            </div>
          )}
          {groups.map(({ group, items }) => (
            <div key={group} className="mt-3 first:mt-1">
              <h2 className="px-2 pb-1 text-xs font-medium text-zinc-500">{group}</h2>
              <ul className="space-y-0.5">{items.map(item)}</ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-zinc-200 p-2 dark:border-zinc-800">
          <UserMenu onNavigate={afterNavigate} />
        </div>

        {mutationError && (
          <p
            className="border-t border-zinc-200 px-3 py-2 text-xs text-red-500 dark:border-zinc-800"
            role="alert"
          >
            {errorMessage(mutationError)}
          </p>
        )}
      </aside>
    </>
  )
}
