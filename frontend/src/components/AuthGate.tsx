import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useLogout, useMe } from '../hooks/useAuth'

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 bg-white p-6 text-center text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      {children}
    </div>
  )
}

/** Shows the app only to signed-in, approved users. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const me = useMe()
  const logout = useLogout()
  const location = useLocation()

  if (me.isLoading) {
    return (
      <Centered>
        <p className="text-sm text-zinc-500">Loading…</p>
      </Centered>
    )
  }
  if (me.isError) {
    return (
      <Centered>
        <p className="text-sm text-red-500">Can’t reach the server: {errorMessage(me.error)}</p>
        <button
          type="button"
          onClick={() => me.refetch()}
          className="text-sm text-indigo-500 hover:underline"
        >
          Try again
        </button>
      </Centered>
    )
  }
  if (!me.data) {
    const next = location.pathname + location.search
    return (
      <Navigate to={next === '/' ? '/auth' : `/auth?next=${encodeURIComponent(next)}`} replace />
    )
  }
  if (me.data.role === 'pending') {
    return (
      <Centered>
        <h1 className="text-xl font-semibold">Waiting for approval</h1>
        <p className="max-w-sm text-sm text-zinc-500">
          Thanks for signing up, {me.data.name}. An admin needs to approve your account before you
          can start chatting.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => me.refetch()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Check again
          </button>
          <button
            type="button"
            onClick={() => logout.mutate(undefined)}
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Sign out
          </button>
        </div>
      </Centered>
    )
  }
  return <>{children}</>
}

/** Admin-only pages; others see a not-found message rather than an error. */
export function AdminOnly({ children }: { children: ReactNode }) {
  const me = useMe()
  if (me.data?.role !== 'admin') {
    return (
      <Centered>
        <p className="text-sm text-zinc-500">This page is only available to admins.</p>
      </Centered>
    )
  }
  return <>{children}</>
}
