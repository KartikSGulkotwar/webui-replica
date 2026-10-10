import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import NotFoundPage from './pages/NotFoundPage'

const SettingsPage = lazy(() => import('./pages/SettingsPage'))

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<Layout />}>
          {/* Both routes render the same ChatPage instance, so a stream started on "/"
              keeps running when the URL changes to the new conversation. */}
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:id" element={<ChatPage />} />
          <Route
            path="/settings"
            element={
              <Suspense
                fallback={<div className="p-6 text-sm text-zinc-500">Loading settings…</div>}
              >
                <SettingsPage />
              </Suspense>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}
