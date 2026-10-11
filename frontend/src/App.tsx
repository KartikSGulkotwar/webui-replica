import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AuthGate, { AdminOnly } from './components/AuthGate'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import AuthPage from './pages/AuthPage'
import ChatPage from './pages/ChatPage'
import NotFoundPage from './pages/NotFoundPage'

const AdminPage = lazy(() => import('./pages/AdminPage'))
const AccountPage = lazy(() => import('./pages/AccountPage'))

function Lazy({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-zinc-500">Loading…</div>}>
      {children}
    </Suspense>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route
          element={
            <AuthGate>
              <Layout />
            </AuthGate>
          }
        >
          {/* Both routes render the same ChatPage instance, so a stream started on "/"
              keeps running when the URL changes to the new conversation. */}
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:id" element={<ChatPage />} />
          <Route
            path="/account"
            element={
              <Lazy>
                <AccountPage />
              </Lazy>
            }
          />
          <Route
            path="/admin/:tab?"
            element={
              <AdminOnly>
                <Lazy>
                  <AdminPage />
                </Lazy>
              </AdminOnly>
            }
          />
          <Route path="/settings" element={<Navigate to="/admin/connections" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}
