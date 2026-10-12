import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { ACCEPTED_FILES, uploadDocument } from '../api/knowledge'
import { BookIcon, FileIcon, PlusIcon } from '../components/icons'
import PageHeader from '../components/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import {
  useCollection,
  useCollections,
  useCreateCollection,
  useDeleteCollection,
  useDeleteDocument,
  useUpdateCollection,
} from '../hooks/useKnowledge'
import { useAppConfig } from '../hooks/useProviders'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
const primary =
  'rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function CollectionList() {
  const collections = useCollections()
  const create = useCreateCollection()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [adding, setAdding] = useState(false)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate(
      { name: name.trim(), description: description.trim() },
      { onSuccess: (c) => navigate(`/knowledge/${c.id}`) },
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Knowledge bases</h2>
          <p className="text-sm text-zinc-500">
            Collections of documents a chat can answer from, with citations. Attach one with the 📎
            button in any chat.
          </p>
        </div>
        {!adding && (
          <button
            type="button"
            className={`${primary} flex shrink-0 items-center gap-1.5`}
            onClick={() => setAdding(true)}
          >
            <PlusIcon /> New
          </button>
        )}
      </div>

      {adding && (
        <form
          onSubmit={submit}
          className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
        >
          <div>
            <label htmlFor="kb-name" className="mb-1 block text-sm font-medium">
              Name
            </label>
            <input
              id="kb-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={100}
              autoFocus
              placeholder="e.g. Company handbook"
              className={input}
            />
          </div>
          <div>
            <label htmlFor="kb-desc" className="mb-1 block text-sm font-medium">
              Description (optional)
            </label>
            <input
              id="kb-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              className={input}
            />
          </div>
          {create.error && <p className="text-sm text-red-500">{errorMessage(create.error)}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" className={button} onClick={() => setAdding(false)}>
              Cancel
            </button>
            <button type="submit" className={primary} disabled={create.isPending || !name.trim()}>
              Create
            </button>
          </div>
        </form>
      )}

      {collections.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {collections.isError && (
        <p className="text-sm text-red-500">{errorMessage(collections.error)}</p>
      )}
      {collections.isSuccess && collections.data.length === 0 && !adding && (
        <div className="rounded-xl border border-dashed border-zinc-300 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
          No knowledge bases yet. Create one, add a few documents, then ask questions about them in
          a chat.
        </div>
      )}
      <ul className="grid gap-3 sm:grid-cols-2">
        {collections.data?.map((c) => (
          <li key={c.id}>
            <Link
              to={`/knowledge/${c.id}`}
              className="block h-full rounded-xl border border-zinc-200 p-4 hover:border-indigo-400 dark:border-zinc-800 dark:hover:border-indigo-500"
            >
              <p className="flex items-center gap-2 font-medium">
                <BookIcon className="shrink-0 text-indigo-500" />
                <span className="truncate">{c.name}</span>
              </p>
              {c.description && (
                <p className="mt-1 line-clamp-2 text-sm text-zinc-500">{c.description}</p>
              )}
              <p className="mt-2 text-xs text-zinc-500">
                {c.document_count} document{c.document_count === 1 ? '' : 's'}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

interface UploadStatus {
  name: string
  state: 'uploading' | 'done' | 'error'
  message?: string
}

function CollectionView({ id }: { id: string }) {
  const collection = useCollection(id)
  const config = useAppConfig()
  const update = useUpdateCollection()
  const removeCollection = useDeleteCollection()
  const removeDoc = useDeleteDocument()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [statuses, setStatuses] = useState<UploadStatus[]>([])
  const [dragging, setDragging] = useState(false)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  useDocumentTitle(collection.data?.name ?? 'Knowledge')
  const maxMb = config.data?.max_upload_mb ?? 10

  const uploadFiles = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      if (file.size > maxMb * 1024 * 1024) {
        setStatuses((s) => [
          ...s,
          { name: file.name, state: 'error', message: `Larger than ${maxMb} MB` },
        ])
        continue
      }
      setStatuses((s) => [...s, { name: file.name, state: 'uploading' }])
      try {
        const doc = await uploadDocument(file, id)
        setStatuses((s) =>
          s.map((x) =>
            x.name === file.name && x.state === 'uploading'
              ? {
                  ...x,
                  state: 'done',
                  message: `${doc.chunk_count} passage${doc.chunk_count === 1 ? '' : 's'} indexed`,
                }
              : x,
          ),
        )
      } catch (err) {
        setStatuses((s) =>
          s.map((x) =>
            x.name === file.name && x.state === 'uploading'
              ? { ...x, state: 'error', message: errorMessage(err) }
              : x,
          ),
        )
      }
      queryClient.invalidateQueries({ queryKey: ['knowledge'] })
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files)
  }

  if (collection.isLoading) return <p className="text-sm text-zinc-500">Loading…</p>
  if (collection.isError || !collection.data)
    return (
      <div className="space-y-2">
        <p className="text-sm text-red-500">{errorMessage(collection.error)}</p>
        <Link to="/knowledge" className="text-sm text-indigo-500 hover:underline">
          ← All knowledge bases
        </Link>
      </div>
    )
  const c = collection.data

  return (
    <div className="space-y-4">
      <Link to="/knowledge" className="text-sm text-indigo-500 hover:underline">
        ← All knowledge bases
      </Link>
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            update.mutate(
              { id, name: name.trim(), description: description.trim() },
              { onSuccess: () => setEditing(false) },
            )
          }}
          className="space-y-2"
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            aria-label="Name"
            className={input}
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={500}
            aria-label="Description"
            placeholder="Description"
            className={input}
          />
          <div className="flex gap-2">
            <button type="submit" className={primary}>
              Save
            </button>
            <button type="button" className={button} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <BookIcon className="text-indigo-500" /> {c.name}
            </h2>
            {c.description && <p className="text-sm text-zinc-500">{c.description}</p>}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className={button}
              onClick={() => {
                setName(c.name)
                setDescription(c.description)
                setEditing(true)
              }}
            >
              Edit
            </button>
            {confirmDelete ? (
              <button
                type="button"
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500"
                onClick={() =>
                  removeCollection.mutate(id, { onSuccess: () => navigate('/knowledge') })
                }
              >
                Delete it and its documents
              </button>
            ) : (
              <button
                type="button"
                className={`${button} text-red-600 dark:text-red-400`}
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </button>
            )}
          </div>
        </div>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-xl border-2 border-dashed px-4 py-8 text-center ${
          dragging
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40'
            : 'border-zinc-300 dark:border-zinc-700'
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          multiple
          accept={ACCEPTED_FILES}
          className="hidden"
          aria-label="Choose files"
          onChange={(e) => {
            if (e.target.files?.length) uploadFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <p className="text-sm">
          Drag files here, or{' '}
          <button
            type="button"
            className="font-medium text-indigo-500 hover:underline"
            onClick={() => fileRef.current?.click()}
          >
            choose files
          </button>
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          PDF, Word, Markdown, text, CSV, JSON, HTML · up to {maxMb} MB each
        </p>
      </div>

      {statuses.length > 0 && (
        <ul className="space-y-1 text-sm" aria-label="Upload progress">
          {statuses.map((s, i) => (
            <li
              key={i}
              className={
                s.state === 'error'
                  ? 'text-red-500'
                  : s.state === 'done'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-zinc-500'
              }
            >
              {s.state === 'uploading' ? '⏳' : s.state === 'done' ? '✓' : '✕'} {s.name}
              {s.message
                ? ` — ${s.message}`
                : s.state === 'uploading'
                  ? ' — reading and indexing…'
                  : ''}
            </li>
          ))}
        </ul>
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium text-zinc-500">
          {c.documents.length} document{c.documents.length === 1 ? '' : 's'}
        </h3>
        <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {c.documents.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-zinc-500">No documents yet.</li>
          )}
          {c.documents.map((d) => (
            <li key={d.id} className="flex items-start gap-3 px-4 py-3">
              <FileIcon className="mt-0.5 shrink-0 text-zinc-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{d.filename}</p>
                <p className="text-xs text-zinc-500">
                  {formatSize(d.size_bytes)}
                  {d.page_count
                    ? ` · ${d.page_count} page${d.page_count === 1 ? '' : 's'}`
                    : ''} · {d.chunk_count} passage{d.chunk_count === 1 ? '' : 's'}
                </p>
                {d.warning && (
                  <p className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">{d.warning}</p>
                )}
              </div>
              <button
                type="button"
                className="rounded-lg px-2 py-1 text-xs text-red-600 hover:bg-zinc-100 dark:text-red-400 dark:hover:bg-zinc-800"
                onClick={() => removeDoc.mutate(d.id)}
                aria-label={`Delete ${d.filename}`}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function KnowledgePage() {
  const { id } = useParams<{ id: string }>()
  useDocumentTitle('Knowledge')
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Knowledge" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          {id ? <CollectionView key={id} id={id} /> : <CollectionList />}
        </div>
      </div>
    </div>
  )
}
