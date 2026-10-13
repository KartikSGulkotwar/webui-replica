import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLogout, useMe } from '../hooks/useAuth'
import { SettingsIcon } from './icons'

const item =
  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800'

export default function UserMenu({ onNavigate }: { onNavigate: () => void }) {
  const me = useMe()
  const logout = useLogout()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const user = me.data
  if (!user) return null
  const go = () => {
    setOpen(false)
    onNavigate()
  }

  return (
    <div ref={ref} className="relative">
      {open && (
        <div
          className="absolute bottom-full left-0 right-0 mb-1 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
          role="menu"
        >
          <Link to="/account" onClick={go} className={item} role="menuitem">
            Account
          </Link>
          <Link to="/memory" onClick={go} className={item} role="menuitem">
            Memory
          </Link>
          <Link to="/archived" onClick={go} className={item} role="menuitem">
            Archived chats
          </Link>
          {user.role === 'admin' && (
            <Link to="/admin/users" onClick={go} className={item} role="menuitem">
              <SettingsIcon />
              Admin panel
            </Link>
          )}
          <button
            type="button"
            onClick={() => logout.mutate(undefined)}
            className={`${item} text-red-600 dark:text-red-400`}
            role="menuitem"
          >
            Sign out
          </button>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800/60"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
          {user.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{user.name}</span>
          <span className="block truncate text-xs text-zinc-500">
            {user.is_guest ? 'Guest' : user.role === 'admin' ? 'Admin' : user.email}
          </span>
        </span>
      </button>
    </div>
  )
}
