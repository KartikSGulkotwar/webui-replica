import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Last-resort screen for render crashes, so users never get a blank page. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-white p-6 text-center text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="max-w-md text-sm text-zinc-500">
          The page hit an unexpected error. Your conversations are saved on the server.
        </p>
        <pre className="max-w-full overflow-x-auto rounded bg-zinc-100 px-3 py-2 text-xs text-red-600 dark:bg-zinc-900 dark:text-red-400">
          {this.state.error.message}
        </pre>
        <button
          type="button"
          onClick={() => window.location.assign('/')}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Reload
        </button>
      </div>
    )
  }
}
