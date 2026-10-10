import { useOutletContext } from 'react-router-dom'

export interface LayoutContext {
  sidebarOpen: boolean
  openSidebar: () => void
}

export function useLayout() {
  return useOutletContext<LayoutContext>()
}
