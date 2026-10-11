import type { ReactNode } from 'react'
import { useLayout } from '../hooks/useLayout'
import { MenuIcon } from './icons'
import ThemeToggle from './ThemeToggle'

export default function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  const { sidebarOpen, openSidebar } = useLayout()
  return (
    <header className="flex items-center gap-1 border-b border-zinc-200 px-2 py-2 dark:border-zinc-800 sm:gap-2 sm:px-4">
      {!sidebarOpen && (
        <button
          type="button"
          onClick={openSidebar}
          className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          aria-label="Open sidebar"
          title="Open sidebar"
        >
          <MenuIcon />
        </button>
      )}
      <h1 className="flex-1 px-2 text-sm font-semibold">{title}</h1>
      {children}
      <ThemeToggle />
    </header>
  )
}
