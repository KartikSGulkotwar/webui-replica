import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  askModel,
  deleteChannel,
  deleteMessage,
  editMessage,
  getMessages,
  listChannels,
  postMessage,
  toggleReaction,
  updateChannel,
} from '../api/channels'
import { errorMessage } from '../api/client'
import Dialog from '../components/Dialog'
import { PencilIcon, SendIcon, TrashIcon, XIcon } from '../components/icons'
import PageHeader from '../components/PageHeader'
import { useMe } from '../hooks/useAuth'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useModels } from '../hooks/useModels'
import { useT } from '../lib/i18n'
import { REACTIONS, type Channel, type ChannelMessage, type ModelInfo } from '../types/api'

const Markdown = lazy(() => import('../components/Markdown'))

const POLL_MS = 3000
const MAX_MENTIONS = 2

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
const day = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })

/** A model writing its reply (only the person who asked sees it stream). */
interface Streaming {
  key: string
  author: string
  text: string
  replyTo: number
  error?: string
}

function Avatar({ name, model }: { name: string; model: boolean }) {
  return (
    <span
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold ${
        model
          ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
          : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
      }`}
      aria-hidden="true"
    >
      {model ? '✨' : name.slice(0, 1).toUpperCase()}
    </span>
  )
}

function Body({ text }: { text: string }) {
  return (
    <Suspense fallback={<p className="whitespace-pre-wrap text-sm">{text}</p>}>
      <div className="text-sm [&_.prose]:text-sm">
        <Markdown content={text} />
      </div>
    </Suspense>
  )
}

function MessageRow({
  m,
  quoted,
  mine,
  canDelete,
  onReply,
  onReact,
  onEdit,
  onDelete,
}: {
  m: ChannelMessage
  quoted?: ChannelMessage
  mine: boolean
  canDelete: boolean
  onReply: () => void
  onReact: (emoji: string) => void
  onEdit: (content: string) => void
  onDelete: () => void
}) {
  const [picking, setPicking] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(m.content)
  const action =
    'rounded-md p-1 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100'

  return (
    <div className="group relative flex gap-3 rounded-lg px-2 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-900/60">
      <Avatar name={m.author} model={!!m.model_id} />
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2 text-sm">
          <span className="font-semibold">{m.author}</span>
          {m.model_id && (
            <span className="rounded bg-indigo-100 px-1 text-[10px] font-medium uppercase text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              AI
            </span>
          )}
          <span className="text-xs text-zinc-500">{time(m.created_at)}</span>
          {m.edited && !m.deleted && <span className="text-xs text-zinc-500">(edited)</span>}
        </p>
        {m.reply_to != null && (
          <p className="mb-0.5 truncate border-l-2 border-zinc-300 pl-2 text-xs text-zinc-500 dark:border-zinc-700">
            ↪{' '}
            {quoted
              ? `${quoted.author}: ${quoted.deleted ? 'deleted message' : quoted.content}`
              : 'an earlier message'}
          </p>
        )}
        {m.deleted ? (
          <p className="text-sm italic text-zinc-500">This message was deleted.</p>
        ) : editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (draft.trim()) onEdit(draft.trim())
              setEditing(false)
            }}
            className="flex gap-2"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              autoFocus
              aria-label="Edit message"
              onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
              className="flex-1 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950"
            />
            <button type="submit" className="text-sm text-indigo-600 dark:text-indigo-400">
              Save
            </button>
          </form>
        ) : (
          <Body text={m.content} />
        )}
        {m.reactions.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {m.reactions.map((r) => (
              <button
                key={r.emoji}
                type="button"
                onClick={() => onReact(r.emoji)}
                aria-pressed={r.mine}
                aria-label={`${r.emoji} ${r.count}`}
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  r.mine
                    ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-700 dark:bg-indigo-950'
                    : 'border-zinc-200 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800'
                }`}
              >
                {r.emoji} {r.count}
              </button>
            ))}
          </div>
        )}
      </div>
      {!m.deleted && !editing && (
        <div className="absolute -top-3 right-2 hidden items-center gap-0.5 rounded-lg border border-zinc-200 bg-white p-0.5 shadow-sm focus-within:flex group-hover:flex dark:border-zinc-700 dark:bg-zinc-900">
          {picking ? (
            REACTIONS.map((e) => (
              <button
                key={e}
                type="button"
                className="rounded-md px-1 py-0.5 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                onClick={() => {
                  onReact(e)
                  setPicking(false)
                }}
                aria-label={`React ${e}`}
              >
                {e}
              </button>
            ))
          ) : (
            <>
              <button
                type="button"
                className={action}
                onClick={() => setPicking(true)}
                aria-label="Add reaction"
                title="React"
              >
                🙂
              </button>
              <button
                type="button"
                className={action}
                onClick={onReply}
                aria-label="Reply"
                title="Reply"
              >
                ↩
              </button>
              {mine && !m.model_id && (
                <button
                  type="button"
                  className={action}
                  onClick={() => {
                    setDraft(m.content)
                    setEditing(true)
                  }}
                  aria-label="Edit message"
                  title="Edit"
                >
                  <PencilIcon width={14} height={14} />
                </button>
              )}
              {canDelete && (
                <button
                  type="button"
                  className={action}
                  onClick={() => window.confirm('Delete this message?') && onDelete()}
                  aria-label="Delete message"
                  title="Delete"
                >
                  <TrashIcon width={14} height={14} />
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

/** The message box, with @ to bring in a model. */
function ChannelComposer({
  models,
  replyTo,
  onCancelReply,
  onSend,
  disabled,
}: {
  models: ModelInfo[]
  replyTo?: ChannelMessage
  onCancelReply: () => void
  onSend: (text: string, mentioned: ModelInfo[]) => Promise<void>
  disabled?: boolean
}) {
  const [text, setText] = useState('')
  const t = useT()
  const [query, setQuery] = useState<string | null>(null)
  const [active, setActive] = useState(0)
  const [sending, setSending] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)
  const matches = useMemo(
    () =>
      query === null
        ? []
        : models.filter((m) => m.name.toLowerCase().includes(query.toLowerCase())).slice(0, 6),
    [models, query],
  )

  useEffect(() => {
    if (replyTo) ref.current?.focus()
  }, [replyTo])

  // "@gp" right before the cursor opens the model list.
  const track = (value: string, cursor: number) => {
    const m = /(?:^|\s)@([^\s@]*)$/.exec(value.slice(0, cursor))
    setQuery(m ? m[1] : null)
    setActive(0)
  }

  // Where the cursor goes after a mention is inserted (set before the next keypress).
  const cursorAfter = useRef<number | null>(null)
  useLayoutEffect(() => {
    if (cursorAfter.current === null) return
    ref.current?.setSelectionRange(cursorAfter.current, cursorAfter.current)
    cursorAfter.current = null
  }, [text])

  const pick = (model: ModelInfo) => {
    const el = ref.current
    const cursor = el?.selectionStart ?? text.length
    const before = text.slice(0, cursor).replace(/@([^\s@]*)$/, `@${model.name} `)
    cursorAfter.current = before.length
    setText(before + text.slice(cursor))
    setQuery(null)
    el?.focus()
  }

  const send = async () => {
    const content = text.trim()
    if (!content || sending) return
    const mentioned = models.filter((m) => content.includes(`@${m.name}`)).slice(0, MAX_MENTIONS)
    setSending(true)
    try {
      await onSend(content, mentioned)
      setText('')
    } finally {
      setSending(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (matches.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        pick(matches[active])
        return
      }
      if (e.key === 'Escape') return setQuery(null)
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <div className="relative mx-auto w-full max-w-4xl px-3 pb-3 sm:px-4 sm:pb-4">
      {matches.length > 0 && (
        <ul
          role="listbox"
          aria-label="Mention a model"
          className="absolute bottom-full left-4 z-20 mb-1 w-72 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          <li className="px-2 py-1 text-xs text-zinc-500">Ask a model to reply</li>
          {matches.map((m, i) => (
            <li key={m.id}>
              <button
                type="button"
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault()
                  pick(m)
                }}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                  i === active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                }`}
              >
                <span aria-hidden="true">{m.emoji ?? '✨'}</span>
                <span className="truncate">{m.name}</span>
                <span className="ml-auto shrink-0 text-xs text-zinc-500">{m.provider_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {replyTo && (
        <div className="mb-1 flex items-center gap-2 rounded-t-lg bg-zinc-100 px-3 py-1.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          <span className="truncate">
            Replying to <strong>{replyTo.author}</strong>: {replyTo.content}
          </span>
          <button
            type="button"
            onClick={onCancelReply}
            className="ml-auto"
            aria-label="Cancel reply"
          >
            <XIcon width={14} height={14} />
          </button>
        </div>
      )}
      <div className="flex items-end gap-2 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm focus-within:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900 dark:focus-within:border-zinc-600">
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            track(e.target.value, e.target.selectionStart)
          }}
          onKeyDown={onKeyDown}
          onBlur={() => setQuery(null)}
          rows={1}
          disabled={disabled}
          placeholder={t('channel.placeholder')}
          aria-label="Message"
          className="max-h-[160px] flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-zinc-400"
        />
        <button
          type="button"
          onClick={() => void send()}
          disabled={disabled || sending || !text.trim()}
          className="rounded-xl bg-indigo-600 p-2 text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-zinc-300 dark:disabled:bg-zinc-700"
          aria-label="Send message"
        >
          <SendIcon />
        </button>
      </div>
    </div>
  )
}

function ChannelSettings({ channel, onClose }: { channel: Channel; onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState(channel.name)
  const [description, setDescription] = useState(channel.description)
  const save = useMutation({
    mutationFn: () => updateChannel(channel.id, { name, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      onClose()
    },
  })
  const remove = useMutation({
    mutationFn: () => deleteChannel(channel.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      navigate('/')
    },
  })
  const input =
    'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
  return (
    <Dialog title={`#${channel.name}`} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
        className="space-y-3 p-4"
      >
        <label className="block text-sm font-medium">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={80}
            className={`${input} mt-1`}
          />
        </label>
        <label className="block text-sm font-medium">
          Description
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={500}
            className={`${input} mt-1`}
          />
        </label>
        {(save.error || remove.error) && (
          <p className="text-sm text-red-500">{errorMessage(save.error ?? remove.error)}</p>
        )}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() =>
              window.confirm(`Delete #${channel.name} and all its messages?`) && remove.mutate()
            }
            className="mr-auto text-sm text-red-600 hover:underline dark:text-red-400"
          >
            Delete channel
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </form>
    </Dialog>
  )
}

export default function ChannelPage() {
  const { id } = useParams<{ id: string }>()
  const me = useMe()
  const t = useT()
  const channels = useQuery({ queryKey: ['channels'], queryFn: listChannels })
  const channel = channels.data?.find((c) => c.id === id)
  const models = useModels()
  const chatModels = (models.data?.models ?? []).filter((m) => m.provider_kind !== 'arena')
  useDocumentTitle(channel ? `#${channel.name}` : 'Channel')

  const [messages, setMessages] = useState<Map<number, ChannelMessage>>(new Map())
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [replyTo, setReplyTo] = useState<ChannelMessage | undefined>()
  const [streams, setStreams] = useState<Streaming[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const since = useRef<string | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const atBottom = useRef(true)

  const merge = useCallback((incoming: ChannelMessage[]) => {
    if (!incoming.length) return
    setMessages((current) => {
      const next = new Map(current)
      for (const m of incoming) next.set(m.id, m)
      return next
    })
  }, [])

  // First page, then poll for anything new or changed.
  useEffect(() => {
    if (!id) return
    let cancelled = false
    setMessages(new Map())
    setLoading(true)
    setError(null)
    since.current = null
    atBottom.current = true
    getMessages(id)
      .then((page) => {
        if (cancelled) return
        merge(page.messages)
        setHasMore(page.has_more)
        since.current = page.now
      })
      .catch((err) => !cancelled && setError(errorMessage(err)))
      .finally(() => !cancelled && setLoading(false))
    const timer = window.setInterval(async () => {
      if (document.hidden || !since.current) return
      try {
        const page = await getMessages(id, { since: since.current })
        if (cancelled) return
        since.current = page.now
        merge(page.messages)
      } catch {
        // try again on the next tick
      }
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [id, merge])

  const ordered = useMemo(() => [...messages.values()].sort((a, b) => a.id - b.id), [messages])

  useLayoutEffect(() => {
    const el = scroller.current
    if (el && atBottom.current) el.scrollTop = el.scrollHeight
  }, [ordered.length, streams])

  const loadOlder = async () => {
    if (!id || !ordered.length) return
    const el = scroller.current
    const fromBottom = el ? el.scrollHeight - el.scrollTop : 0
    const page = await getMessages(id, { before: ordered[0].id })
    merge(page.messages)
    setHasMore(page.has_more)
    requestAnimationFrame(() => el && (el.scrollTop = el.scrollHeight - fromBottom))
  }

  const send = async (text: string, mentioned: ModelInfo[]) => {
    if (!id) return
    setError(null)
    let posted: ChannelMessage
    try {
      posted = await postMessage(id, { content: text, reply_to: replyTo?.id ?? null })
    } catch (err) {
      setError(errorMessage(err))
      throw err
    }
    atBottom.current = true
    merge([posted])
    setReplyTo(undefined)
    // Each mentioned model answers; its reply streams here and is saved for everyone.
    for (const model of mentioned) {
      const key = `${posted.id}:${model.id}`
      setStreams((s) => [...s, { key, author: model.name, text: '', replyTo: posted.id }])
      askModel(
        id,
        { model_id: model.id, message_id: posted.id },
        {
          onDelta: (d) =>
            setStreams((s) => s.map((x) => (x.key === key ? { ...x, text: x.text + d } : x))),
        },
      )
        .then(async () => {
          const page = await getMessages(id, { since: since.current ?? posted.created_at })
          merge(page.messages)
          setStreams((s) => s.filter((x) => x.key !== key))
        })
        .catch((err) =>
          setStreams((s) => s.map((x) => (x.key === key ? { ...x, error: errorMessage(err) } : x))),
        )
    }
  }

  const act = async (run: () => Promise<ChannelMessage | void>) => {
    try {
      const updated = await run()
      if (updated) merge([updated])
      else if (id && since.current) {
        const page = await getMessages(id, { since: since.current })
        merge(page.messages)
      }
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (channels.isSuccess && !channel) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="Channel" />
        <div className="p-6 text-sm">
          <p className="text-zinc-500">This channel doesn’t exist (any more).</p>
          <Link to="/" className="text-indigo-500 hover:underline">
            Back to chat
          </Link>
        </div>
      </div>
    )
  }

  const isAdmin = me.data?.role === 'admin'
  let lastDay = ''
  return (
    <div className="flex h-full flex-col">
      <PageHeader title={channel ? `# ${channel.name}` : 'Channel'}>
        {isAdmin && channel && (
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="rounded-lg px-2.5 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            Edit channel
          </button>
        )}
      </PageHeader>
      {channel?.description && (
        <p className="border-b border-zinc-200 px-4 py-1.5 text-xs text-zinc-500 dark:border-zinc-800">
          {channel.description}
        </p>
      )}
      <div
        ref={scroller}
        onScroll={() => {
          const el = scroller.current
          if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
        }}
        className="flex-1 overflow-y-auto"
      >
        <div className="mx-auto w-full max-w-4xl px-2 py-4 sm:px-4">
          {hasMore && (
            <button
              type="button"
              onClick={() => void loadOlder()}
              className="mx-auto mb-3 block rounded-full border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              Load earlier messages
            </button>
          )}
          {loading && <p className="text-center text-sm text-zinc-500">Loading…</p>}
          {!loading && ordered.length === 0 && (
            <p className="py-10 text-center text-sm text-zinc-500">{t('channel.empty')}</p>
          )}
          <div className="space-y-1" aria-label="Messages" aria-live="polite">
            {ordered.map((m) => {
              const d = day(m.created_at)
              const divider = d !== lastDay
              lastDay = d
              const mine = m.user_id === me.data?.id
              const quoted = m.reply_to != null ? messages.get(m.reply_to) : undefined
              // A model's reply to your message is yours to delete too.
              const askedByMe = !!m.model_id && quoted?.user_id === me.data?.id
              return (
                <div key={m.id}>
                  {divider && (
                    <p className="my-3 text-center text-xs font-medium text-zinc-500">{d}</p>
                  )}
                  <MessageRow
                    m={m}
                    quoted={quoted}
                    mine={mine}
                    canDelete={mine || isAdmin || askedByMe}
                    onReply={() => setReplyTo(m)}
                    onReact={(emoji) => void act(() => toggleReaction(id!, m.id, emoji))}
                    onEdit={(content) => void act(() => editMessage(id!, m.id, content))}
                    onDelete={() => void act(() => deleteMessage(id!, m.id))}
                  />
                </div>
              )
            })}
            {streams.map((s) => (
              <div key={s.key} className="flex gap-3 rounded-lg px-2 py-1.5">
                <Avatar name={s.author} model />
                <div className="min-w-0 flex-1">
                  <p className="flex items-baseline gap-2 text-sm">
                    <span className="font-semibold">{s.author}</span>
                    <span className="text-xs text-zinc-500">
                      {s.error ? 'couldn’t reply' : 'is replying…'}
                    </span>
                  </p>
                  {s.error ? (
                    <p className="text-sm text-red-500">{s.error}</p>
                  ) : s.text ? (
                    <Body text={s.text} />
                  ) : (
                    <span className="inline-flex gap-1 py-2" aria-label="Thinking">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {error && <p className="px-4 pb-1 text-center text-sm text-red-500">{error}</p>}
      <ChannelComposer
        models={chatModels}
        replyTo={replyTo}
        onCancelReply={() => setReplyTo(undefined)}
        onSend={send}
        disabled={!channel}
      />
      {settingsOpen && channel && (
        <ChannelSettings channel={channel} onClose={() => setSettingsOpen(false)} />
      )}
    </div>
  )
}
