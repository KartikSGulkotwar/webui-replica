import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import ChatWindow from '../components/ChatWindow'
import Composer from '../components/Composer'
import { PlusIcon } from '../components/icons'
import MessageBubble from '../components/MessageBubble'
import ModelSelector from '../components/ModelSelector'
import ThemeToggle from '../components/ThemeToggle'
import { useChatStream } from '../hooks/useChatStream'
import { useConversation } from '../hooks/useConversation'
import { useModels, useSelectedModel } from '../hooks/useModels'
import { modelLabel } from '../lib/models'

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const modelsQuery = useModels()
  const models = modelsQuery.data?.models
  const { selected, select } = useSelectedModel(models)
  const conversation = useConversation(id)
  const { pending, send, stop, isStreaming } = useChatStream(id)

  const serverMessages = conversation.data?.messages ?? []
  // A failed send from "/" never got a conversation, so its id is ''.
  const p = pending && pending.conversationId === (id ?? '') ? pending : null
  // Show the local copy of an exchange until the refetched conversation contains it.
  const showPendingUser = !!p && p.conversationId !== '' && serverMessages.length < p.baseCount + 1
  const showPendingAssistant =
    !!p &&
    (p.status === 'streaming' || (p.text !== '' && serverMessages.length < p.baseCount + 2))
  const pendingError = p?.status === 'error' ? p.error : null

  const selectedProviderOk =
    !selected || (modelsQuery.data?.providers.find((x) => x.id === selected.provider_id)?.ok ?? true)

  let disabledReason: string | undefined
  if (modelsQuery.isLoading) disabledReason = 'Loading models…'
  else if (modelsQuery.isError) disabledReason = 'Backend unreachable'
  else if (!selected) disabledReason = 'No models available'
  else if (!selectedProviderOk) disabledReason = `${selected.provider_name} is offline`

  const notFound = !!id && conversation.isError
  const isEmpty = !id || (conversation.isSuccess && serverMessages.length === 0 && !p)

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-zinc-200 px-2 py-2 dark:border-zinc-800 sm:px-4">
        <ModelSelector
          data={modelsQuery.data}
          isLoading={modelsQuery.isLoading}
          isError={modelsQuery.isError}
          selected={selected}
          onSelect={select}
        />
        <div className="min-w-0 flex-1 truncate text-center text-sm text-zinc-500">
          {conversation.data?.title}
        </div>
        <Link
          to="/"
          className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          aria-label="New chat"
          title="New chat"
        >
          <PlusIcon />
        </Link>
        <ThemeToggle />
      </header>

      {notFound ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <p className="text-zinc-500">{errorMessage(conversation.error)}</p>
          <Link to="/" className="text-sm text-indigo-500 hover:underline">
            Start a new chat
          </Link>
        </div>
      ) : id && conversation.isLoading ? (
        <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
          Loading conversation…
        </div>
      ) : isEmpty ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">How can I help?</h1>
          <p className="text-sm text-zinc-500">
            {selected
              ? `Chatting with ${selected.name} via ${selected.provider_name}. Switch models anytime from the menu above.`
              : (disabledReason ?? '')}
          </p>
          {pendingError && <p className="text-sm text-red-500">{pendingError}</p>}
        </div>
      ) : (
        <ChatWindow
          key={id}
          contentKey={`${serverMessages.length}:${p?.text.length ?? 0}:${p?.status ?? ''}`}
        >
          {serverMessages.map((m) => (
            <MessageBubble
              key={m.id}
              role={m.role}
              content={m.content}
              model={m.role === 'assistant' && m.model_id ? modelLabel(m.model_id, models) : undefined}
            />
          ))}
          {showPendingUser && <MessageBubble role="user" content={p.userContent} />}
          {showPendingAssistant && (
            <MessageBubble
              role="assistant"
              content={p.text}
              model={modelLabel(p.modelId, models)}
              streaming={p.status === 'streaming'}
            />
          )}
          {pendingError && (
            <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              {pendingError}
            </div>
          )}
        </ChatWindow>
      )}

      <Composer
        onSend={(text) => selected && send(text, selected.id)}
        onStop={stop}
        isStreaming={isStreaming}
        disabled={!!disabledReason || notFound}
        disabledReason={disabledReason}
      />
    </div>
  )
}
