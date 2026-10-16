import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ApiError } from './api/client'
import './index.css'
import { applyTheme, getStoredTheme } from './lib/theme'
import I18nProvider from './components/I18nProvider'

applyTheme(getStoredTheme())

// Any 401 means the session ended (signed out elsewhere, expired, or the account
// was removed): mark the user as signed out so the app shows the sign-in page.
const onError = (err: unknown) => {
  if (err instanceof ApiError && err.status === 401) queryClient.setQueryData(['me'], null)
}

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: {
    queries: {
      // Retrying a 401/403/404 can't help.
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Installable app: the service worker loads the app fast and shows an offline
// page without a connection (production builds only; it would cache dev files).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
)
