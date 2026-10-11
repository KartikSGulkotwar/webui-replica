import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import {
  useConversations,
  useDeleteConversation,
  useUpdateConversation,
} from '../hooks/useConversations'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

const button =
  'rounded-lg border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'

export default function ArchivedPage() {
  useDocumentTitle('Archived chats')
  const archived = useConversations({ archived: true })
  const update = useUpdateConversation()
  const remove = useDeleteConversation()
  const [confirming, setConfirming] = useState<string | null>(null)

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Archived chats" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-3 px-4 py-6">
          <p className="text-sm text-zinc-500">
            Archived chats are hidden from the sidebar. Restore one to bring it back.
          </p>
          {archived.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
          {archived.isError && (
            <p className="text-sm text-red-500">{errorMessage(archived.error)}</p>
          )}
          {archived.isSuccess && archived.data.length === 0 && (
            <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
              No archived chats.
            </p>
          )}
          <ul className="space-y-2">
            {archived.data?.map((c) => (
              <li
                key={c.id}
                className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800"
              >
                <Link to={`/c/${c.id}`} className="min-w-0 flex-1 truncate text-sm hover:underline">
                  {c.title}
                </Link>
                <span className="text-xs text-zinc-500">
                  {new Date(c.updated_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
                </span>
                <button
                  type="button"
                  className={button}
                  onClick={() => update.mutate({ id: c.id, patch: { archived: false } })}
                >
                  Restore
                </button>
                {confirming === c.id ? (
                  <button
                    type="button"
                    className="rounded-lg bg-red-600 px-2.5 py-1 text-xs text-white hover:bg-red-500"
                    onClick={() => remove.mutate(c.id)}
                  >
                    Confirm delete
                  </button>
                ) : (
                  <button
                    type="button"
                    className={`${button} text-red-600 dark:text-red-400`}
                    onClick={() => setConfirming(c.id)}
                  >
                    Delete
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
