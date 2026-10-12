import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ACCEPTED_FILES } from '../api/knowledge'
import type { AttachmentControls } from '../hooks/useChatAttachments'
import { useCollections } from '../hooks/useKnowledge'
import { BookIcon, CheckIcon, FileIcon, PaperclipIcon, XIcon } from './icons'

type Controls = AttachmentControls

export function AttachmentChips({ controls }: { controls: Controls }) {
  const { attachments, uploads, error, remove, dismissUpload } = controls
  if (!attachments.length && !uploads.length && !error) return null
  return (
    <div className="mb-2 flex flex-wrap gap-1.5" aria-label="Attached documents">
      {attachments.map((a) => (
        <span
          key={`${a.kind}-${a.id}`}
          className="inline-flex max-w-[16rem] items-center gap-1 rounded-full border border-zinc-200 bg-white px-2 py-0.5 text-xs dark:border-zinc-700 dark:bg-zinc-900"
          title={a.kind === 'collection' ? `Knowledge base: ${a.name}` : a.name}
        >
          {a.kind === 'collection' ? (
            <BookIcon width={12} height={12} />
          ) : (
            <FileIcon width={12} height={12} />
          )}
          <span className="truncate">{a.name}</span>
          <button
            type="button"
            onClick={() => remove(a)}
            className="rounded p-0.5 text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
            aria-label={`Remove ${a.name}`}
          >
            <XIcon width={11} height={11} />
          </button>
        </span>
      ))}
      {uploads.map((u) => (
        <span
          key={u.key}
          className={`inline-flex max-w-[20rem] items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
            u.error
              ? 'border-red-300 text-red-600 dark:border-red-900 dark:text-red-400'
              : 'border-zinc-200 text-zinc-500 dark:border-zinc-700'
          }`}
          role={u.error ? 'alert' : 'status'}
        >
          {!u.error && <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />}
          <span className="truncate">
            {u.error ? `${u.name}: ${u.error}` : `Reading ${u.name}…`}
          </span>
          {u.error && (
            <button
              type="button"
              onClick={() => dismissUpload(u.key)}
              aria-label="Dismiss"
              className="p-0.5"
            >
              <XIcon width={11} height={11} />
            </button>
          )}
        </span>
      ))}
      {error && <span className="text-xs text-red-500">{error}</span>}
    </div>
  )
}

export function AttachButton({ controls, disabled }: { controls: Controls; disabled?: boolean }) {
  const { attachments, toggle, upload } = controls
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const collections = useCollections()

  useEffect(() => {
    if (!open) return
    const close = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const item =
    'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800'

  return (
    <div ref={ref} className="relative self-end">
      <input
        ref={fileRef}
        type="file"
        multiple
        accept={ACCEPTED_FILES}
        className="hidden"
        aria-label="Upload documents"
        onChange={(e) => {
          if (e.target.files?.length) upload(e.target.files)
          e.target.value = ''
          setOpen(false)
        }}
      />
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        className={`rounded-xl p-2 hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800 ${
          attachments.length ? 'text-indigo-500' : 'text-zinc-500'
        }`}
        aria-label="Attach documents"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Chat with your documents"
      >
        <PaperclipIcon />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-20 mb-2 w-72 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={() => fileRef.current?.click()}
          >
            <FileIcon /> Upload files…
            <span className="ml-auto text-xs text-zinc-500">PDF, Word, text</span>
          </button>
          <div className="my-1 border-t border-zinc-200 dark:border-zinc-800" />
          <p className="px-3 py-1 text-xs font-medium text-zinc-500">Knowledge bases</p>
          {collections.isLoading && <p className="px-3 py-1 text-xs text-zinc-500">Loading…</p>}
          {collections.data?.length === 0 && (
            <p className="px-3 py-1 text-xs text-zinc-500">None yet.</p>
          )}
          <div className="max-h-56 overflow-y-auto">
            {collections.data?.map((c) => {
              const on = attachments.some((a) => a.kind === 'collection' && a.id === c.id)
              return (
                <button
                  key={c.id}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={on}
                  className={item}
                  onClick={() => toggle({ kind: 'collection', id: c.id, name: c.name })}
                >
                  <BookIcon />
                  <span className="min-w-0 flex-1 truncate">{c.name}</span>
                  <span className="text-xs text-zinc-500">{c.document_count}</span>
                  {on && <CheckIcon className="text-indigo-500" />}
                </button>
              )
            })}
          </div>
          <Link
            to="/knowledge"
            className={`${item} text-indigo-500`}
            onClick={() => setOpen(false)}
          >
            Manage knowledge bases →
          </Link>
        </div>
      )}
    </div>
  )
}
