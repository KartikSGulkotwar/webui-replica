import { useCallback, useState } from 'react'
import { Outlet } from 'react-router-dom'
import type { LayoutContext } from '../hooks/useLayout'
import { useMediaQuery } from '../hooks/useMediaQuery'
import Sidebar from './Sidebar'

export default function Layout() {
  const isMobile = useMediaQuery('(max-width: 767px)')
  // Tracked separately so shrinking the window doesn't leave an overlay open.
  const [desktopOpen, setDesktopOpen] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const open = isMobile ? mobileOpen : desktopOpen

  const setOpen = useCallback(
    (value: boolean) => (isMobile ? setMobileOpen(value) : setDesktopOpen(value)),
    [isMobile],
  )

  return (
    <div className="flex h-full bg-paper text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Sidebar open={open} onClose={() => setOpen(false)} isMobile={isMobile} />
      <main className="min-w-0 flex-1">
        <Outlet
          context={{ sidebarOpen: open, openSidebar: () => setOpen(true) } satisfies LayoutContext}
        />
      </main>
    </div>
  )
}
