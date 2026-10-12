import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { rateMessage } from '../api/conversations'
import { AttachButton, AttachmentChips } from '../components/ChatAttachments'
import ChatMenu from '../components/ChatMenu'
import ChatWindow from '../components/ChatWindow'
import Composer from '../components/Composer'
import { MenuIcon, PlusIcon } from '../components/icons'
import MessageBubble from '../components/MessageBubble'
import ToolsButton from '../components/ToolsButton'
import ModelSelector from '../components/ModelSelector'
import ThemeToggle from '../components/ThemeToggle'
import { useChatAttachments } from '../hooks/useChatAttachments'
import { useSelectedTools, useToolList } from '../hooks/useTools'
import { expectedCount, useChatStream } from '../hooks/useChatStream'
import { useMe } from '../hooks/useAuth'
import { conversationKey, useConversation } from '../hooks/useConversation'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useLayout } from '../hooks/useLayout'
import { useModels, useSelectedModel } from '../hooks/useModels'
import { useAppConfig } from '../hooks/useProviders'
import { modelLabel } from '../lib/models'
import type { ConversationDetail, Rating } from '../types/api'

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const modelsQuery = useModels()
  const models = modelsQuery.data?.models
  const config = useAppConfig()
  const me = useMe()
  const { selected, select } = useSelectedModel(models, config.data?.default_model)
  const conversation = useConversation(id)
  const { pending, run, stop, isStreaming } = useChatStream(id)
  const queryClient = useQueryClient()
  const toolList = useToolList()
  const toolChoice = useSelectedTools()
  // Only tools that are still enabled are sent.
  const activeTools = toolChoice.selected.filter((t) => toolList.data?.some((i) => i.id === t))
  // System prompt chosen before the first message, when the chat doesn't exist yet.
  const [draftSystemPrompt, setDraftSystemPrompt] = useState('')
  const attach = useChatAttachments(
    id ? conversation.data : undefined,
    config.data?.max_upload_mb ?? 10,
  )
  const labelFor = useCallback(
    (modelId: string) => {
      const l = modelLabel(modelId, models)
      return l.provider ? `${l.name} (${l.provider})` : l.name
    },
    [models],
  )

  const rate = useMutation({
    mutationFn: (v: { messageId: number; rating: Rating | null; comment?: string }) =>
      rateMessage(id!, v.messageId, v.rating, v.comment),
    onMutate: ({ messageId, rating }) => {
      queryClient.setQueryData<ConversationDetail>(conversationKey(id!), (d) =>
        d
          ? { ...d, messages: d.messages.map((m) => (m.id === messageId ? { ...m, rating } : m)) }
          : d,
      )
    },
    onError: () => queryClient.invalidateQueries({ queryKey: conversationKey(id!) }),
  })
  const { sidebarOpen, openSidebar } = useLayout()
  useDocumentTitle(id ? conversation.data?.title : undefined)

  const serverMessages = conversation.data?.messages ?? []
  // A failed send from "/" never got a conversation, so its id is ''.
  const p = pending && pending.conversationId === (id ?? '') ? pending : null
  // Show the local copy of an exchange until the refetched conversation contains it.
  const showPendingUser =
    !!p &&
    p.kind === 'send' &&
    !p.notSent &&
    p.conversationId !== '' &&
    serverMessages.length < p.baseCount + 1
  const showPendingAssistant =
    !!p && (p.status === 'streaming' || (p.text !== '' && serverMessages.length < expectedCount(p)))
  const lastAssistantId = [...serverMessages].reverse().find((m) => m.role === 'assistant')?.id
  const lastMessage = serverMessages.at(-1)
  // A question whose reply failed or was never written can be answered again.
  const canRetry =
    !isStreaming && !!selected && lastMessage?.role === 'user' && !showPendingAssistant
  const pendingError = p?.status === 'error' ? p.error : null

  const selectedProviderOk =
    !selected ||
    (modelsQuery.data?.providers.find((x) => x.id === selected.provider_id)?.ok ?? true)

  let disabledReason: string | undefined
  if (modelsQuery.isLoading) disabledReason = 'Loading models…'
  else if (modelsQuery.isError) disabledReason = 'Backend unreachable'
  else if (!selected) disabledReason = 'No models available'
  else if (!selectedProviderOk) disabledReason = `${selected.provider_name} is offline`

  const notFound = !!id && conversation.isError
  const isEmpty = !id || (conversation.isSuccess && serverMessages.length === 0 && !p)

  return (
    <div className="flex h-full flex-col">
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
        <ModelSelector
          data={modelsQuery.data}
          // Wait for the config too, so the default model shows without a flicker.
          isLoading={modelsQuery.isLoading || config.isLoading}
          isError={modelsQuery.isError}
          selected={selected}
          onSelect={select}
          isAdmin={me.data?.role === 'admin'}
        />
        <div className="min-w-0 flex-1 truncate text-center text-sm text-zinc-500">
          {conversation.data?.title}
        </div>
        {!notFound && (
          <ChatMenu
            conversation={id ? conversation.data : undefined}
            draftSystemPrompt={draftSystemPrompt}
            onDraftSystemPrompt={setDraftSystemPrompt}
            modelLabel={labelFor}
          />
        )}
        {!sidebarOpen && (
          <Link
            to="/"
            className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            aria-label="New chat"
            title="New chat"
          >
            <PlusIcon />
          </Link>
        )}
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
          {selected?.provider_kind === 'custom' && (
            <span className="text-4xl" aria-hidden="true">
              {selected.emoji}
            </span>
          )}
          <h1 className="text-2xl font-semibold tracking-tight">
            {selected?.provider_kind === 'custom' ? selected.name : 'How can I help?'}
          </h1>
          <p className="text-sm text-zinc-500">
            {selected?.provider_kind === 'custom'
              ? (selected.description ?? `${selected.name} is ready.`)
              : selected
                ? `Chatting with ${selected.name} via ${selected.provider_name}. Switch models anytime from the menu above.`
                : (disabledReason ?? '')}
          </p>
          {draftSystemPrompt && (
            <p className="max-w-md text-xs text-indigo-500">
              System prompt set: “{draftSystemPrompt.slice(0, 80)}
              {draftSystemPrompt.length > 80 ? '…' : ''}”
            </p>
          )}
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
              model={
                m.role === 'assistant' && m.model_id ? modelLabel(m.model_id, models) : undefined
              }
              sources={m.sources}
              toolCalls={m.tools}
              toolInfo={toolList.data}
              actions={
                m.role === 'assistant'
                  ? {
                      rating: m.rating,
                      onRate: (rating, comment) =>
                        rate.mutate({ messageId: m.id, rating, comment }),
                      onRegenerate:
                        m.id === lastAssistantId && selected
                          ? () =>
                              run({ kind: 'regenerate' }, selected.id, undefined, {
                                tools: activeTools,
                              })
                          : undefined,
                      busy: isStreaming || !selected,
                    }
                  : {
                      onEdit: selected
                        ? (content) =>
                            run(
                              { kind: 'edit', messageId: m.id, content },
                              selected.id,
                              undefined,
                              {
                                tools: activeTools,
                              },
                            )
                        : undefined,
                      busy: isStreaming,
                    }
              }
            />
          ))}
          {showPendingUser && <MessageBubble role="user" content={p.userContent} />}
          {showPendingAssistant && (
            <MessageBubble
              role="assistant"
              content={p.text}
              model={modelLabel(p.modelId, models)}
              streaming={p.status === 'streaming'}
              sources={p.sources}
              toolCalls={p.tools}
              toolInfo={toolList.data}
            />
          )}
          {pendingError && (
            <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              {pendingError}
            </div>
          )}
          {canRetry && (
            <button
              type="button"
              onClick={() =>
                run({ kind: 'regenerate' }, selected!.id, undefined, { tools: activeTools })
              }
              className="w-fit rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              Get a reply
            </button>
          )}
        </ChatWindow>
      )}

      <Composer
        onSend={(text) => {
          if (!selected) return
          run(
            { kind: 'send', content: text },
            selected.id,
            id ? undefined : { systemPrompt: draftSystemPrompt, attachments: attach.draft },
            { tools: activeTools },
          )
          if (!id) setDraftSystemPrompt('')
        }}
        onStop={stop}
        restoreText={p?.notSent ? p.userContent : undefined}
        isStreaming={isStreaming}
        above={<AttachmentChips controls={attach} />}
        leading={
          <>
            <AttachButton controls={attach} disabled={notFound} />
            <ToolsButton
              tools={toolList.data ?? []}
              selected={activeTools}
              onToggle={toolChoice.toggle}
              disabled={notFound}
            />
          </>
        }
        disabled={!!disabledReason || notFound || attach.busy}
        disabledReason={disabledReason}
      />
    </div>
  )
}
