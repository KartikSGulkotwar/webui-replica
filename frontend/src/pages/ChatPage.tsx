import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { rateMessage, rateMessages } from '../api/conversations'
import { AttachButton, AttachmentChips } from '../components/ChatAttachments'
import ChatMenu from '../components/ChatMenu'
import ChatWindow from '../components/ChatWindow'
import Composer from '../components/Composer'
import { MenuIcon, PlusIcon, XIcon } from '../components/icons'
import MessageBubble, { type MessageActions } from '../components/MessageBubble'
import ReplyGroup, { type ReplyColumn, type Vote } from '../components/ReplyGroup'
import ToolsButton from '../components/ToolsButton'
import ComposerToggle, { GlobeIcon, ImageIcon } from '../components/ComposerToggle'
import DictationButton from '../components/DictationButton'
import VoiceMode, { type VoiceReply } from '../components/VoiceMode'
import ModelSelector from '../components/ModelSelector'
import ThemeToggle from '../components/ThemeToggle'
import { useChatAttachments } from '../hooks/useChatAttachments'
import { useSelectedTools, useToolList } from '../hooks/useTools'
import { expectedCount, useChatStream, type PendingReply } from '../hooks/useChatStream'
import { useMe } from '../hooks/useAuth'
import { conversationKey, useConversation } from '../hooks/useConversation'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useLayout } from '../hooks/useLayout'
import { useModels, useSelectedModel } from '../hooks/useModels'
import { useAppConfig } from '../hooks/useProviders'
import { browserCanListen } from '../lib/browserDictation'
import { canRecord, warmUpAudio } from '../lib/recorder'
import { browserCanSpeak } from '../lib/speech'
import { modelLabel } from '../lib/models'
import { ARENA_MODEL_ID, type ConversationDetail, type Message, type Rating } from '../types/api'
import { useT } from '../lib/i18n'

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const modelsQuery = useModels()
  const models = modelsQuery.data?.models
  const config = useAppConfig()
  const me = useMe()
  const t = useT()
  const { selected, select } = useSelectedModel(models, config.data?.default_model)
  // More models that answer side by side (not with the arena).
  const [extras, setExtras] = useState<string[]>([])
  const isArena = selected?.id === ARENA_MODEL_ID
  const extraModels = isArena
    ? []
    : extras
        .map((x) => models?.find((m) => m.id === x))
        .filter((m): m is NonNullable<typeof m> => !!m && m.id !== selected?.id)
  const chosen = selected ? [selected.id, ...extraModels.map((m) => m.id)] : []
  const addExtra = () => {
    const next = models?.find((m) => m.provider_kind !== 'arena' && !chosen.includes(m.id))
    if (next) setExtras((x) => [...x.filter((id) => chosen.includes(id)), next.id])
  }
  const conversation = useConversation(id)
  const { pending, run, stop, isStreaming } = useChatStream(id)
  const queryClient = useQueryClient()
  const toolList = useToolList()
  const toolChoice = useSelectedTools()
  // Only tools that are still enabled are sent.
  const activeTools = toolChoice.selected.filter((t) => toolList.data?.some((i) => i.id === t))
  // Web search is switched on per message, like Open WebUI (not remembered).
  const [webSearchOn, setWebSearchOn] = useState(false)
  const canSearch = !!config.data?.web_search
  // Image: this message becomes a picture (per message, like web search).
  const [imageOn, setImageOn] = useState(false)
  const canImage = !!config.data?.image_generation
  const runOptions = {
    tools: activeTools,
    webSearch: canSearch && webSearchOn,
    image: canImage && imageOn,
  }
  // Voice: dictation in the composer, and a hands-free voice mode.
  const serverStt = !!config.data?.speech_to_text
  const serverTts = !!config.data?.text_to_speech
  const canTalk = (serverStt ? canRecord() : browserCanListen()) && (serverTts || browserCanSpeak())
  const [voiceOpen, setVoiceOpen] = useState(false)
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
  const VOTES: Record<Vote, [1 | -1, 1 | -1]> = {
    a: [1, -1],
    b: [-1, 1],
    tie: [1, 1],
    bad: [-1, -1],
  }
  const vote = useMutation({
    mutationFn: (v: { replies: Message[]; vote: Vote }) => {
      const [a, b] = [...v.replies].sort((x, y) => (x.slot ?? 0) - (y.slot ?? 0))
      const [ra, rb] = VOTES[v.vote]
      return rateMessages(id!, { [a.id]: ra, [b.id]: rb })
    },
    // The answer reveals the models.
    onSuccess: (messages) =>
      queryClient.setQueryData<ConversationDetail>(conversationKey(id!), (d) =>
        d ? { ...d, messages } : d,
      ),
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
    !!p &&
    (p.status === 'streaming' ||
      (p.replies.some((r) => r.text !== '') && serverMessages.length < expectedCount(p)))
  // Messages, with consecutive replies to the same message grouped.
  const items: (Message | Message[])[] = []
  for (const m of serverMessages) {
    const last = items.at(-1)
    if (m.role === 'assistant' && Array.isArray(last)) last.push(m)
    else items.push(m.role === 'assistant' ? [m] : m)
  }
  const lastGroup = Array.isArray(items.at(-1)) ? (items.at(-1) as Message[]) : null
  const sideBySide = (g: Message[]) => g.length > 1 || g.some((m) => m.slot != null || m.blind)
  // Regenerating one of several replies: it rejoins its group while it streams.
  const pendingJoinsLast =
    !!p && p.kind === 'regenerate' && p.replies.length === 1 && p.replies[0].slot != null
  const wide =
    chosen.length > 1 ||
    items.some((x) => Array.isArray(x) && sideBySide(x)) ||
    (!!p && p.replies.length > 1)
  const lastMessage = serverMessages.at(-1)
  // A question whose reply failed or was never written can be answered again.
  const canRetry =
    !isStreaming && !!selected && lastMessage?.role === 'user' && !showPendingAssistant
  const pendingError = p?.status === 'error' ? p.error : null

  const selectedProviderOk =
    !selected ||
    (modelsQuery.data?.providers.find((x) => x.id === selected.provider_id)?.ok ?? true)

  let disabledReason: string | undefined
  if (modelsQuery.isLoading) disabledReason = t('chat.loadingModels')
  else if (modelsQuery.isError) disabledReason = t('chat.unreachable')
  else if (!selected) disabledReason = t('chat.noModels')
  else if (!selectedProviderOk)
    disabledReason = t('chat.providerOffline', { provider: selected.provider_name })

  const label = (modelId: string | null) => (modelId ? modelLabel(modelId, models) : null)
  const replyActions = (m: Message, inLastGroup: boolean, group: Message[]): MessageActions => ({
    rating: m.rating,
    onRate: (rating, comment) => rate.mutate({ messageId: m.id, rating, comment }),
    onRegenerate:
      inLastGroup && selected && !m.blind
        ? sideBySide(group)
          ? // One column: the same model writes it again.
            () =>
              run(
                { kind: 'regenerate', messageId: m.id },
                [m.model_id ?? selected.id],
                undefined,
                runOptions,
              )
          : () => run({ kind: 'regenerate' }, chosen, undefined, runOptions)
        : undefined,
    busy: isStreaming || !selected,
  })
  const serverColumn = (m: Message, group: Message[]): ReplyColumn => ({
    key: m.id,
    slot: m.slot ?? 0,
    model: label(m.model_id),
    content: m.content,
    sources: m.sources,
    toolCalls: m.tools,
    images: m.images,
    rating: m.rating,
    actions: replyActions(m, group === lastGroup, group),
  })
  const pendingColumn = (r: PendingReply, i: number): ReplyColumn => ({
    key: `pending-${i}`,
    slot: r.slot ?? i,
    model: label(r.modelId),
    content: r.text,
    streaming: r.status === 'streaming',
    error: r.status === 'error' ? r.error : undefined,
    sources: r.sources,
    toolCalls: r.tools,
    images: r.images,
  })
  const renderGroup = (group: Message[], extra: ReplyColumn[] = []) => (
    <ReplyGroup
      key={`g-${group[0]?.id ?? 'pending'}`}
      columns={[...group.map((m) => serverColumn(m, group)), ...extra]}
      toolInfo={toolList.data}
      blind={group.some((m) => m.blind) || (!!p?.blind && extra.length > 0)}
      onVote={group.length === 2 ? (v) => vote.mutate({ replies: group, vote: v }) : undefined}
      voting={vote.isPending}
    />
  )

  const send = (text: string) => {
    if (!selected) return
    run(
      { kind: 'send', content: text },
      chosen,
      id ? undefined : { systemPrompt: draftSystemPrompt, attachments: attach.draft },
      runOptions,
    )
    if (!id) setDraftSystemPrompt('')
  }
  // Voice mode reads out the first reply once it's finished.
  const voiceReply: VoiceReply | null =
    pending && pending.kind === 'send'
      ? {
          key: `${pending.conversationId}:${pending.baseCount}`,
          text: pending.replies[0]?.text ?? '',
          done: pending.status !== 'streaming',
          error: pending.status === 'error' ? pending.error : undefined,
        }
      : null

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
          label={extraModels.length ? 'Model 1' : undefined}
        />
        {extraModels.map((m, i) => (
          <div key={m.id} className="flex min-w-0 items-center">
            <ModelSelector
              data={modelsQuery.data}
              isLoading={modelsQuery.isLoading}
              isError={modelsQuery.isError}
              selected={m}
              onSelect={(next) => setExtras((x) => x.map((old) => (old === m.id ? next : old)))}
              isAdmin={me.data?.role === 'admin'}
              exclude={(o) => o.provider_kind === 'arena'}
              label={`Model ${i + 2}`}
            />
            <button
              type="button"
              onClick={() => setExtras((x) => x.filter((old) => old !== m.id))}
              className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
              aria-label={`Stop comparing with ${m.name}`}
              title="Remove"
            >
              <XIcon />
            </button>
          </div>
        ))}
        {selected && !isArena && chosen.length < 3 && (models?.length ?? 0) > chosen.length && (
          <button
            type="button"
            onClick={addExtra}
            className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            aria-label={t('chat.compare')}
            title={t('chat.compare')}
          >
            <PlusIcon />
          </button>
        )}
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
            {t('chat.startNew')}
          </Link>
        </div>
      ) : id && conversation.isLoading ? (
        <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
          {t('chat.loading')}
        </div>
      ) : isEmpty ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          {(selected?.provider_kind === 'custom' || isArena) && (
            <span className="text-4xl" aria-hidden="true">
              {selected!.emoji}
            </span>
          )}
          <h1 className="text-2xl font-semibold tracking-tight">
            {selected?.provider_kind === 'custom' || isArena
              ? selected!.name
              : t('chat.howCanIHelp')}
          </h1>
          <p className="max-w-md text-sm text-zinc-500">
            {selected?.provider_kind === 'custom' || isArena
              ? (selected!.description ?? `${selected!.name} is ready.`)
              : extraModels.length
                ? t('chat.sideBySide', {
                    models: [selected!, ...extraModels].map((m) => m.name).join(', '),
                  })
                : selected
                  ? t('chat.chattingWith', {
                      model: selected.name,
                      provider: selected.provider_name,
                    })
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
          contentKey={`${serverMessages.length}:${p?.replies.reduce((n, r) => n + r.text.length, 0) ?? 0}:${p?.status ?? ''}`}
          wide={wide}
        >
          {items.map((item) => {
            if (!Array.isArray(item)) {
              const m = item
              return (
                <MessageBubble
                  key={m.id}
                  role={m.role}
                  content={m.content}
                  actions={{
                    onEdit: selected
                      ? (content) =>
                          run(
                            { kind: 'edit', messageId: m.id, content },
                            chosen,
                            undefined,
                            runOptions,
                          )
                      : undefined,
                    busy: isStreaming,
                  }}
                />
              )
            }
            const group = item
            const joining = group === lastGroup && pendingJoinsLast && showPendingAssistant
            if (sideBySide(group) || joining) {
              return renderGroup(group, joining ? p!.replies.map(pendingColumn) : [])
            }
            const m = group[0]
            return (
              <MessageBubble
                key={m.id}
                role="assistant"
                content={m.content}
                model={label(m.model_id) ?? undefined}
                sources={m.sources}
                toolCalls={m.tools}
                images={m.images}
                toolInfo={toolList.data}
                actions={replyActions(m, group === lastGroup, group)}
              />
            )
          })}
          {showPendingUser && <MessageBubble role="user" content={p.userContent} />}
          {showPendingAssistant &&
            !pendingJoinsLast &&
            (p.replies.length === 1 && p.replies[0].slot == null ? (
              <MessageBubble
                role="assistant"
                content={p.replies[0].text}
                model={label(p.replies[0].modelId) ?? undefined}
                streaming={p.replies[0].status === 'streaming'}
                sources={p.replies[0].sources}
                toolCalls={p.replies[0].tools}
                images={p.replies[0].images}
                toolInfo={toolList.data}
              />
            ) : (
              renderGroup([], p.replies.map(pendingColumn))
            ))}
          {pendingError && (
            <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              {pendingError}
            </div>
          )}
          {canRetry && (
            <button
              type="button"
              onClick={() => run({ kind: 'regenerate' }, chosen, undefined, runOptions)}
              className="w-fit rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {t('chat.getReply')}
            </button>
          )}
        </ChatWindow>
      )}

      <Composer
        onSend={send}
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
            {canSearch && (
              <ComposerToggle
                on={webSearchOn}
                onToggle={() => setWebSearchOn((v) => !v)}
                label="Web search"
                icon={<GlobeIcon />}
                titleOn="Web search on: replies search the internet first"
                titleOff="Search the web"
                disabled={notFound}
              />
            )}
            {canImage && (
              <ComposerToggle
                on={imageOn}
                onToggle={() => setImageOn((v) => !v)}
                label="Image"
                icon={<ImageIcon />}
                titleOn="Image on: your message is turned into a picture"
                titleOff="Create an image"
                disabled={notFound}
              />
            )}
          </>
        }
        trailing={(addText) => (
          <>
            <DictationButton onText={addText} serverStt={serverStt} disabled={notFound} />
            {canTalk && (
              <button
                type="button"
                onClick={() => {
                  warmUpAudio() // while the click still counts as a user gesture
                  setVoiceOpen(true)
                }}
                disabled={!!disabledReason || notFound || isStreaming}
                className="self-end rounded-xl p-2 text-zinc-500 hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800"
                aria-label="Voice mode"
                title="Voice mode: talk and listen"
              >
                <WaveIcon />
              </button>
            )}
          </>
        )}
        disabled={!!disabledReason || notFound || attach.busy}
        disabledReason={disabledReason}
      />
      {voiceOpen && (
        <VoiceMode
          serverStt={serverStt}
          serverTts={serverTts}
          onSend={send}
          reply={voiceReply}
          onClose={() => setVoiceOpen(false)}
        />
      )}
    </div>
  )
}

const WaveIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    aria-hidden="true"
  >
    <path d="M3 10v4M7 6v12M11 3v18M15 7v10M19 10v4" />
  </svg>
)
