import { useHealth } from '../hooks/useHealth'

export default function ChatPage() {
  const health = useHealth()

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">WebUI Replica</h1>
      <p className="max-w-md text-zinc-500 dark:text-zinc-400">
        Chat with Ollama and OpenAI-compatible models from one interface.
      </p>
      <div className="flex items-center gap-2 rounded-full border border-zinc-200 px-3 py-1 text-sm dark:border-zinc-800">
        <span
          className={`h-2 w-2 rounded-full ${
            health.isPending ? 'bg-zinc-400' : health.isSuccess ? 'bg-emerald-500' : 'bg-red-500'
          }`}
        />
        {health.isPending && 'Connecting to backend…'}
        {health.isSuccess && `Backend online · v${health.data.version}`}
        {health.isError && 'Backend unreachable'}
      </div>
    </div>
  )
}
