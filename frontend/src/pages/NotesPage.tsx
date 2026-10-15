import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  chatAboutNote,
  createNote,
  deleteNote,
  getNote,
  listNotes,
  noteAi,
  updateNote,
} from '../api/notes'
import DictationButton from '../components/DictationButton'
import { DownloadIcon, PinIcon, PlusIcon, SearchIcon, TrashIcon } from '../components/icons'
import PageHeader from '../components/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useModels, useSelectedModel } from '../hooks/useModels'
import { useAppConfig } from '../hooks/useProviders'
import { downloadFile } from '../lib/exportChat'
import type { Note, NoteAiAction, NoteSummary } from '../types/api'

const Markdown = lazy(() => import('../components/Markdown'))

const SAVE_DELAY_MS = 800
const button =
  'flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100 disabled:opacity-40 dark:text-zinc-400 dark:hover:bg-zinc-800'

const AI_ACTIONS: { action: NoteAiAction; label: string }[] = [
  { action: 'improve', label: '✨ Improve writing' },
  { action: 'summarize', label: '📝 Summarize' },
  { action: 'continue', label: '➡️ Continue writing' },
  { action: 'custom', label: '💬 Custom instruction…' },
]

function relative(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function NoteList({ activeId, onPick }: { activeId?: string; onPick: () => void }) {
  const [q, setQ] = useState('')
  const notes = useQuery({ queryKey: ['notes', q], queryFn: () => listNotes(q) })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const create = useMutation({
    mutationFn: () => createNote({}),
    onSuccess: (note) => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      navigate(`/notes/${note.id}`)
      onPick()
    },
  })
  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 p-3">
        <button
          type="button"
          onClick={() => create.mutate()}
          disabled={create.isPending}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          <PlusIcon /> New note
        </button>
        {create.error && <p className="text-xs text-red-500">{errorMessage(create.error)}</p>}
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search notes"
            aria-label="Search notes"
            className="w-full rounded-lg border border-zinc-200 bg-white py-1.5 pl-8 pr-2 text-sm outline-none focus:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto px-2 pb-3" aria-label="Notes">
        {notes.data?.length === 0 && (
          <li className="px-2 py-6 text-center text-sm text-zinc-500">
            {q ? 'No matching notes.' : 'No notes yet.'}
          </li>
        )}
        {notes.data?.map((n: NoteSummary) => (
          <li key={n.id}>
            <Link
              to={`/notes/${n.id}`}
              onClick={onPick}
              className={`block rounded-lg px-3 py-2 ${
                n.id === activeId
                  ? 'bg-zinc-200 dark:bg-zinc-800'
                  : 'hover:bg-zinc-100 dark:hover:bg-zinc-800/60'
              }`}
            >
              <span className="flex items-center gap-1 text-sm font-medium">
                {n.pinned && (
                  <PinIcon width={12} height={12} className="shrink-0 text-indigo-500" />
                )}
                <span className="truncate">{n.title || 'Untitled'}</span>
              </span>
              <span className="mt-0.5 line-clamp-2 text-xs text-zinc-500">
                {relative(n.updated_at)} · {n.snippet || 'Empty note'}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Edits one note, saving shortly after each change. */
function Editor({ note }: { note: Note }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const models = useModels()
  const config = useAppConfig()
  const { selected } = useSelectedModel(models.data?.models, config.data?.default_model)
  const [title, setTitle] = useState(note.title)
  const [content, setContent] = useState(note.content)
  const [preview, setPreview] = useState(false)
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [aiOpen, setAiOpen] = useState(false)
  const [ai, setAi] = useState<{
    action: NoteAiAction
    text: string
    running: boolean
    error?: string
    // The selection it worked on (replaced by "Replace"), or the whole note.
    range: [number, number] | null
  } | null>(null)
  const [instruction, setInstruction] = useState('')
  const area = useRef<HTMLTextAreaElement>(null)
  const pending = useRef<Partial<Note>>({})
  const timer = useRef<number | undefined>(undefined)
  const abort = useRef<AbortController | null>(null)
  useDocumentTitle(title || 'Untitled note')

  const flush = async () => {
    window.clearTimeout(timer.current)
    const patch = pending.current
    pending.current = {}
    if (!Object.keys(patch).length) return
    setSaveState('saving')
    try {
      const saved = await updateNote(note.id, patch)
      queryClient.setQueryData(['note', note.id], saved)
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      setSaveState(Object.keys(pending.current).length ? 'saving' : 'saved')
    } catch {
      pending.current = { ...patch, ...pending.current }
      setSaveState('error')
    }
  }
  const schedule = (patch: Partial<Note>) => {
    pending.current = { ...pending.current, ...patch }
    setSaveState('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => void flush(), SAVE_DELAY_MS)
  }
  // Save anything unsaved when leaving the note.
  useEffect(
    () => () => {
      abort.current?.abort()
      void flush()
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  const setBody = (next: string) => {
    setContent(next)
    schedule({ content: next })
  }

  const insertAtCursor = (text: string) => {
    const el = area.current
    const at = el ? el.selectionEnd : content.length
    const before = content.slice(0, at)
    const sep = before && !/\s$/.test(before) ? ' ' : ''
    setBody(before + sep + text + content.slice(at))
  }

  const runAi = async (action: NoteAiAction) => {
    if (!selected) return
    setAiOpen(false)
    const el = area.current
    const hasSelection = !preview && el && el.selectionEnd > el.selectionStart
    const range: [number, number] | null = hasSelection
      ? [el.selectionStart, el.selectionEnd]
      : null
    abort.current?.abort()
    const controller = new AbortController()
    abort.current = controller
    setAi({ action, text: '', running: true, range })
    await flush() // the server reads the saved note when there's no selection
    try {
      await noteAi(
        note.id,
        {
          action,
          model_id: selected.id,
          text: range ? content.slice(range[0], range[1]) : undefined,
          instruction: action === 'custom' ? instruction : undefined,
        },
        {
          signal: controller.signal,
          onDelta: (d) => setAi((a) => (a ? { ...a, text: a.text + d } : a)),
        },
      )
      setAi((a) => (a ? { ...a, running: false } : a))
    } catch (err) {
      if (!controller.signal.aborted)
        setAi((a) => (a ? { ...a, running: false, error: errorMessage(err) } : a))
    }
  }

  const applyAi = (how: 'replace' | 'below') => {
    if (!ai) return
    const result = ai.text.trim()
    if (how === 'replace') {
      setBody(
        ai.range ? content.slice(0, ai.range[0]) + result + content.slice(ai.range[1]) : result,
      )
    } else {
      const at = ai.range ? ai.range[1] : content.length
      setBody(`${content.slice(0, at).replace(/\s+$/, '')}\n\n${result}\n${content.slice(at)}`)
    }
    setAi(null)
  }

  const remove = useMutation({
    mutationFn: () => deleteNote(note.id),
    onSuccess: () => {
      pending.current = {}
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      navigate('/notes')
    },
  })
  const pin = useMutation({
    mutationFn: () => updateNote(note.id, { pinned: !note.pinned }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['note', note.id], saved)
      queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
  const askInChat = useMutation({
    mutationFn: async () => {
      await flush()
      return chatAboutNote(note.id)
    },
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/c/${conv.id}`)
    },
  })

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <div className="mr-auto flex rounded-lg border border-zinc-200 p-0.5 text-sm dark:border-zinc-700">
          {(['Edit', 'Preview'] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={preview === (m === 'Preview')}
              onClick={() => setPreview(m === 'Preview')}
              className={`rounded-md px-2.5 py-1 ${
                preview === (m === 'Preview')
                  ? 'bg-zinc-200 dark:bg-zinc-800'
                  : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
        <span className="px-2 text-xs text-zinc-500" role="status">
          {saveState === 'saving'
            ? 'Saving…'
            : saveState === 'error'
              ? 'Not saved — retrying on next change'
              : 'Saved'}
        </span>
        <div className="relative">
          <button
            type="button"
            className={button}
            onClick={() => setAiOpen((o) => !o)}
            disabled={!selected || ai?.running}
            aria-haspopup="menu"
            aria-expanded={aiOpen}
            title={
              selected
                ? `Uses ${selected.name}. Works on the selection, or the whole note.`
                : 'No model available'
            }
          >
            ✨ AI
          </button>
          {aiOpen && (
            <div
              role="menu"
              className="absolute right-0 z-20 mt-1 w-64 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
            >
              {AI_ACTIONS.filter((a) => a.action !== 'custom').map((a) => (
                <button
                  key={a.action}
                  type="button"
                  role="menuitem"
                  onClick={() => void runAi(a.action)}
                  className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  {a.label}
                </button>
              ))}
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (instruction.trim()) void runAi('custom')
                }}
                className="border-t border-zinc-200 p-2 dark:border-zinc-800"
              >
                <input
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="Or say what to do, e.g. Translate to Spanish"
                  aria-label="Custom instruction"
                  className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950"
                />
              </form>
              <p className="px-3 pb-1.5 text-xs text-zinc-500">
                Select text first to work on just that part.
              </p>
            </div>
          )}
        </div>
        <DictationButton onText={insertAtCursor} serverStt={!!config.data?.speech_to_text} />
        <button
          type="button"
          className={button}
          onClick={() => pin.mutate()}
          aria-pressed={note.pinned}
          title={note.pinned ? 'Unpin' : 'Pin to the top'}
        >
          <PinIcon width={15} height={15} className={note.pinned ? 'text-indigo-500' : ''} />
        </button>
        <button
          type="button"
          className={button}
          onClick={() => askInChat.mutate()}
          disabled={askInChat.isPending || !content.trim()}
          title="Start a chat about this note"
        >
          💬 Ask in chat
        </button>
        <button
          type="button"
          className={button}
          onClick={() =>
            downloadFile(
              `${(title || 'note').replace(/[^\w\- ]+/g, '').trim() || 'note'}.md`,
              title ? `# ${title}\n\n${content}` : content,
              'text/markdown',
            )
          }
          title="Download as Markdown"
          aria-label="Download as Markdown"
        >
          <DownloadIcon width={15} height={15} />
        </button>
        <button
          type="button"
          className={button}
          onClick={() => window.confirm('Delete this note?') && remove.mutate()}
          title="Delete note"
          aria-label="Delete note"
        >
          <TrashIcon width={15} height={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col gap-3 px-4 py-5">
          <input
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              schedule({ title: e.target.value })
            }}
            placeholder="Untitled"
            aria-label="Title"
            maxLength={200}
            className="bg-transparent text-2xl font-semibold outline-none placeholder:text-zinc-400"
          />
          {ai && (
            <div className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3 dark:border-indigo-900 dark:bg-indigo-950/30">
              <p className="text-xs font-medium text-indigo-600 dark:text-indigo-300">
                {AI_ACTIONS.find((a) => a.action === ai.action)?.label}
                {ai.range ? ' · selection' : ' · whole note'}
                {ai.running && ' · writing…'}
              </p>
              {ai.error ? (
                <p className="text-sm text-red-500">{ai.error}</p>
              ) : (
                <div className="max-h-72 overflow-y-auto whitespace-pre-wrap text-sm">
                  {ai.text || '…'}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {!ai.running && !ai.error && ai.action !== 'continue' && (
                  <button
                    type="button"
                    onClick={() => applyAi('replace')}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
                  >
                    Replace {ai.range ? 'selection' : 'note'}
                  </button>
                )}
                {!ai.running && !ai.error && (
                  <button type="button" className={button} onClick={() => applyAi('below')}>
                    Insert below
                  </button>
                )}
                {!ai.running && !ai.error && (
                  <button
                    type="button"
                    className={button}
                    onClick={() => void navigator.clipboard?.writeText(ai.text)}
                  >
                    Copy
                  </button>
                )}
                <button
                  type="button"
                  className={button}
                  onClick={() => {
                    abort.current?.abort()
                    setAi(null)
                  }}
                >
                  {ai.running ? 'Stop' : 'Discard'}
                </button>
              </div>
            </div>
          )}
          {preview ? (
            <div className="min-h-[50vh]">
              {content.trim() ? (
                <Suspense fallback={<p className="text-sm text-zinc-500">Loading…</p>}>
                  <Markdown content={content} />
                </Suspense>
              ) : (
                <p className="text-sm text-zinc-500">Nothing to preview yet.</p>
              )}
            </div>
          ) : (
            <textarea
              ref={area}
              value={content}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Start writing… Markdown works: # headings, **bold**, - lists, `code`"
              aria-label="Note"
              className="min-h-[50vh] flex-1 resize-none bg-transparent font-mono text-sm leading-6 outline-none placeholder:text-zinc-400"
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default function NotesPage() {
  const { id } = useParams<{ id: string }>()
  const note = useQuery({ queryKey: ['note', id], queryFn: () => getNote(id!), enabled: !!id })
  const [listOpen, setListOpen] = useState(!id)
  useDocumentTitle(id ? undefined : 'Notes')
  useEffect(() => setListOpen(!id), [id])

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Notes" />
      <div className="flex min-h-0 flex-1">
        <aside
          className={`w-full shrink-0 border-zinc-200 dark:border-zinc-800 md:block md:w-72 md:border-r ${
            listOpen ? 'block' : 'hidden'
          }`}
        >
          <NoteList activeId={id} onPick={() => setListOpen(false)} />
        </aside>
        <section className={`min-w-0 flex-1 ${listOpen ? 'hidden md:block' : 'block'}`}>
          {!id ? (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-zinc-500">
              Pick a note, or create one. Notes are private to you, saved as you type, and the ✨ AI
              button can improve, summarize or continue them.
            </div>
          ) : note.isLoading ? (
            <p className="p-6 text-sm text-zinc-500">Loading…</p>
          ) : note.isError ? (
            <div className="p-6 text-sm">
              <p className="text-red-500">{errorMessage(note.error)}</p>
              <Link to="/notes" className="text-indigo-500 hover:underline">
                Back to notes
              </Link>
            </div>
          ) : (
            note.data && (
              <>
                <Link
                  to="/notes"
                  className="block px-4 pt-2 text-sm text-indigo-500 hover:underline md:hidden"
                >
                  ← All notes
                </Link>
                <Editor key={note.data.id} note={note.data} />
              </>
            )
          )}
        </section>
      </div>
    </div>
  )
}
