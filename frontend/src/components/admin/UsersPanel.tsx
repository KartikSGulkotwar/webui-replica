import { useState } from 'react'
import { errorMessage } from '../../api/client'
import { useDeleteUser, useSetUserRole, useUsers } from '../../hooks/useAdmin'
import { useMe } from '../../hooks/useAuth'
import type { User, UserRole } from '../../types/api'

const ROLE_STYLES: Record<UserRole, string> = {
  admin: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300',
  user: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })
}

function UserRow({ user, isMe }: { user: User; isMe: boolean }) {
  const setRole = useSetUserRole()
  const remove = useDeleteUser()
  const [confirming, setConfirming] = useState(false)
  const error = setRole.error ?? remove.error

  return (
    <li className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-200 text-sm font-semibold dark:bg-zinc-800">
          {user.name.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {user.name} {isMe && <span className="text-zinc-500">(you)</span>}
          </p>
          <p className="truncate text-xs text-zinc-500">
            {user.is_guest ? 'Guest account' : user.email} · joined {formatDate(user.created_at)} ·
            active {formatDate(user.last_active_at)}
          </p>
        </div>
        {isMe ? (
          <span className={`rounded-full px-2 py-0.5 text-xs ${ROLE_STYLES[user.role]}`}>
            {user.role}
          </span>
        ) : (
          <select
            value={user.role}
            onChange={(e) => setRole.mutate({ id: user.id, role: e.target.value as UserRole })}
            disabled={setRole.isPending}
            aria-label={`Role for ${user.name}`}
            className={`rounded-full border-0 px-2 py-0.5 text-xs ${ROLE_STYLES[user.role]}`}
          >
            <option value="pending">pending</option>
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        )}
        {!isMe &&
          (confirming ? (
            <span className="flex items-center gap-1 text-xs">
              <span className="text-red-600 dark:text-red-400">Delete user and their chats?</span>
              <button
                type="button"
                onClick={() => remove.mutate(user.id)}
                disabled={remove.isPending}
                className="rounded-lg bg-red-600 px-2 py-1 text-white hover:bg-red-500 disabled:opacity-50"
              >
                Delete
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded-lg border border-zinc-300 px-2 py-1 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-lg border border-zinc-300 px-2 py-1 text-xs text-red-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-red-400 dark:hover:bg-zinc-800"
            >
              Delete
            </button>
          ))}
      </div>
      {error && <p className="mt-2 text-xs text-red-500">{errorMessage(error)}</p>}
    </li>
  )
}

export default function UsersPanel() {
  const users = useUsers()
  const me = useMe()
  const [filter, setFilter] = useState<'all' | UserRole>('all')

  const list = users.data?.filter((u) => filter === 'all' || u.role === filter) ?? []
  const pendingCount = users.data?.filter((u) => u.role === 'pending').length ?? 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Users</h2>
          <p className="text-sm text-zinc-500">
            Approve new sign-ups, change roles, or remove accounts.
          </p>
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as typeof filter)}
          aria-label="Filter by role"
          className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="all">All roles</option>
          <option value="pending">Pending ({pendingCount})</option>
          <option value="user">Users</option>
          <option value="admin">Admins</option>
        </select>
      </div>

      {users.isLoading && <p className="text-sm text-zinc-500">Loading users…</p>}
      {users.isError && (
        <p className="text-sm text-red-500">Couldn’t load users: {errorMessage(users.error)}</p>
      )}
      {users.isSuccess && list.length === 0 && (
        <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
          No users match this filter.
        </p>
      )}
      <ul className="space-y-2">
        {list.map((u) => (
          <UserRow key={u.id} user={u} isMe={u.id === me.data?.id} />
        ))}
      </ul>
    </div>
  )
}
