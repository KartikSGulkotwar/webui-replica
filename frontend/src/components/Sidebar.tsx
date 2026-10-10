import { useMemo } from 'react'
import { Link, NavLink, useMatch, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  useConversations,
  useDeleteConversation,
  useRenameConversation,
} from '../hooks/useConversations'
import { groupByDate } from '../lib/dates'
import ConversationItem from './ConversationItem'
import { MenuIcon, PlusIcon, SettingsIcon } from './icons'

interface Props {
  open: boolean
  onClose: () => void
  /** On small screens the sidebar is an overlay that closes after navigating. */
  isMobile: boolean
}

export default function Sidebar({ open, onClose, isMobile }: Props) {
  const activeId = useMatch('/c/:id')?.params.id
  const navigate = useNavigate()
  const conversations = useConversations()
  const rename = useRenameConversation()
  const remove = useDeleteConversation()

  const groups = useMemo(
    () => groupByDate(conversations.data ?? [], (c) => c.updated_at),
    [conversations.data],
  )

  const afterNavigate = () => {
    if (isMobile) onClose()
  }

  const handleDelete = (id: string) => {
    remove.mutate(id)
    if (id === activeId) navigate('/')
  }

  const mutationError = rename.error ?? remove.error

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
          {conversations.isSuccess && conversations.data.length === 0 && (
            <p className="px-2 pt-2 text-sm text-zinc-500">No conversations yet.</p>
          )}
          {groups.map(({ group, items }) => (
            <div key={group} className="mt-3 first:mt-1">
              <h2 className="px-2 pb-1 text-xs font-medium text-zinc-500">{group}</h2>
              <ul className="space-y-0.5">
                {items.map((c) => (
                  <li key={c.id}>
                    <ConversationItem
                      conversation={c}
                      active={c.id === activeId}
                      onNavigate={afterNavigate}
                      onRename={(title) => rename.mutate({ id: c.id, title })}
                      onDelete={() => handleDelete(c.id)}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-zinc-200 p-2 dark:border-zinc-800">
          <NavLink
            to="/settings"
            onClick={afterNavigate}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                isActive
                  ? 'bg-zinc-200 dark:bg-zinc-800'
                  : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800/60'
              }`
            }
          >
            <SettingsIcon />
            Settings
          </NavLink>
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
