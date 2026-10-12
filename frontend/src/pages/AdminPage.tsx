import { NavLink, Navigate, useParams } from 'react-router-dom'
import ConnectionsPanel from '../components/admin/ConnectionsPanel'
import DocumentsPanel from '../components/admin/DocumentsPanel'
import GeneralPanel from '../components/admin/GeneralPanel'
import ModelsPanel from '../components/admin/ModelsPanel'
import UsersPanel from '../components/admin/UsersPanel'
import WebSearchPanel from '../components/admin/WebSearchPanel'
import PageHeader from '../components/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

const TABS = [
  { id: 'users', label: 'Users', Panel: UsersPanel },
  { id: 'connections', label: 'Connections', Panel: ConnectionsPanel },
  { id: 'models', label: 'Models', Panel: ModelsPanel },
  { id: 'documents', label: 'Documents', Panel: DocumentsPanel },
  { id: 'web-search', label: 'Web search', Panel: WebSearchPanel },
  { id: 'general', label: 'General', Panel: GeneralPanel },
] as const

export default function AdminPage() {
  const { tab } = useParams<{ tab: string }>()
  const current = TABS.find((t) => t.id === tab)
  useDocumentTitle(current ? `Admin · ${current.label}` : 'Admin')
  if (!current) return <Navigate to="/admin/users" replace />

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Admin panel" />
      <nav className="flex gap-1 overflow-x-auto border-b border-zinc-200 px-2 dark:border-zinc-800 sm:px-4">
        {TABS.map((t) => (
          <NavLink
            key={t.id}
            to={`/admin/${t.id}`}
            className={({ isActive }) =>
              `whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
                isActive
                  ? 'border-indigo-500 font-medium text-zinc-900 dark:text-zinc-100'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100'
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          <current.Panel />
        </div>
      </div>
    </div>
  )
}
