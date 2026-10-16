import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { getSharedChat } from '../api/conversations'
import MessageBubble from '../components/MessageBubble'
import ThemeToggle from '../components/ThemeToggle'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/** Public, read-only view of a shared chat. No sign-in needed. */
export default function SharedPage() {
  const { shareId } = useParams<{ shareId: string }>()
  const shared = useQuery({
    queryKey: ['shared', shareId],
    queryFn: () => getSharedChat(shareId!),
    retry: false,
  })
  useDocumentTitle(shared.data ? `${shared.data.title} (shared)` : 'Shared chat')

  return (
    <div className="flex h-full flex-col bg-paper text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="flex items-center gap-2 border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
        <Link to="/" className="text-sm font-semibold">
          WebUI Replica
        </Link>
        <span className="flex-1 truncate text-center text-sm text-zinc-500">
          {shared.data?.title}
        </span>
        <ThemeToggle />
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
          {shared.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
          {shared.isError && (
            <div className="space-y-2 py-10 text-center">
              <p className="text-zinc-500">{errorMessage(shared.error)}</p>
              <Link to="/" className="text-sm text-indigo-500 hover:underline">
                Go to WebUI Replica
              </Link>
            </div>
          )}
          {shared.data && (
            <>
              <p className="text-xs text-zinc-500">
                Shared chat · snapshot from{' '}
                {new Date(shared.data.updated_at).toLocaleString(undefined, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}
              </p>
              {shared.data.messages.map((m, i) => (
                <MessageBubble
                  key={i}
                  role={m.role}
                  content={m.content}
                  images={m.images}
                  model={
                    m.role === 'assistant' && m.model_id
                      ? {
                          name: m.model_id.slice(m.model_id.indexOf(':') + 1),
                          provider: m.model_id.split(':')[0],
                        }
                      : undefined
                  }
                />
              ))}
              <div className="border-t border-zinc-200 pt-4 text-center dark:border-zinc-800">
                <Link
                  to="/"
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
                >
                  Start your own chat
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
