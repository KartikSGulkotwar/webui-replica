import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api/client'
import {
  addMemory,
  deleteAllMemories,
  deleteMemory,
  editMemory,
  listMemories,
  setMemoryEnabled,
} from '../api/memories'
import { PencilIcon, TrashIcon } from '../components/icons'
import PageHeader from '../components/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import type { MemoryItem, MemoryList } from '../types/api'

const key = ['memories'] as const
const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-900'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
const iconButton =
  'rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100'

function Row({ memory }: { memory: MemoryItem }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(memory.content)
  const refresh = () => queryClient.invalidateQueries({ queryKey: key })
  const save = useMutation({
    mutationFn: () => editMemory(memory.id, text),
    onSuccess: () => {
      setEditing(false)
      refresh()
    },
  })
  const remove = useMutation({ mutationFn: () => deleteMemory(memory.id), onSuccess: refresh })

  if (editing) {
    return (
      <li className="rounded-xl border border-indigo-300 p-3 dark:border-indigo-800">
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            save.mutate()
          }}
          className="space-y-2"
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            maxLength={1000}
            required
            aria-label="Edit memory"
            autoFocus
            className={input}
          />
          {save.error && <p className="text-sm text-red-500">{errorMessage(save.error)}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className={button}
              onClick={() => {
                setText(memory.content)
                setEditing(false)
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={save.isPending || !text.trim()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </form>
      </li>
    )
  }
  return (
    <li className="group flex items-start gap-3 rounded-xl border border-zinc-200 px-4 py-3 dark:border-zinc-800">
      <div className="min-w-0 flex-1">
        <p className="whitespace-pre-wrap break-words text-sm">{memory.content}</p>
        <p className="mt-0.5 text-xs text-zinc-500">
          {new Date(memory.updated_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
        </p>
      </div>
      <div className="flex shrink-0 gap-0.5">
        <button
          type="button"
          className={iconButton}
          onClick={() => setEditing(true)}
          aria-label={`Edit memory: ${memory.content}`}
        >
          <PencilIcon />
        </button>
        <button
          type="button"
          className={iconButton}
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
          aria-label={`Delete memory: ${memory.content}`}
        >
          <TrashIcon />
        </button>
      </div>
    </li>
  )
}

export default function MemoryPage() {
  useDocumentTitle('Memory')
  const queryClient = useQueryClient()
  const memories = useQuery({ queryKey: key, queryFn: listMemories })
  const [draft, setDraft] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const refresh = () => queryClient.invalidateQueries({ queryKey: key })

  const setEnabled = (enabled: boolean) =>
    queryClient.setQueryData<MemoryList>(key, (d) => (d ? { ...d, enabled } : d))
  const toggle = useMutation({
    mutationFn: setMemoryEnabled,
    // Flip the switch right away; put it back if saving fails.
    onMutate: (enabled) => setEnabled(enabled),
    onError: (_err, enabled) => setEnabled(!enabled),
  })
  const add = useMutation({
    mutationFn: addMemory,
    onSuccess: refresh,
    // Give the text back so it isn't lost (unless something new was typed).
    onError: (_err, content) => setDraft((d) => d || content),
  })
  // Clears the box right away, so the next memory can be typed while this one saves.
  const submit = () => {
    const content = draft.trim()
    if (!content) return
    setDraft('')
    add.mutate(content)
  }
  const clear = useMutation({
    mutationFn: deleteAllMemories,
    onSuccess: () => {
      setConfirmClear(false)
      refresh()
    },
  })
  const data = memories.data

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Memory" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
          <p className="text-sm text-zinc-500">
            Things the assistant remembers about you in every chat, like your name, your job, or how
            you like answers. Add them here, or turn on 🧠 Memory in the 🔧 tools menu and say
            “remember that…” in a chat. Only you can see your memories.
          </p>
          {memories.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
          {memories.isError && (
            <p className="text-sm text-red-500">{errorMessage(memories.error)}</p>
          )}
          {data && (
            <>
              <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
                <span>
                  <span className="block text-sm font-medium">Use memories in chats</span>
                  <span className="block text-xs text-zinc-500">
                    When off, your memories are kept but not shown to the model, and it can’t save
                    new ones.
                  </span>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  checked={data.enabled}
                  onChange={(e) => toggle.mutate(e.target.checked)}
                  disabled={toggle.isPending}
                  className="h-4 w-4 accent-indigo-600"
                />
              </label>
              {toggle.error && <p className="text-sm text-red-500">{errorMessage(toggle.error)}</p>}

              <form
                onSubmit={(e: FormEvent) => {
                  e.preventDefault()
                  submit()
                }}
                className="flex items-start gap-2"
              >
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && draft.trim()) {
                      e.preventDefault()
                      submit()
                    }
                  }}
                  rows={1}
                  maxLength={1000}
                  placeholder="e.g. I'm a backend developer who prefers Python and short answers"
                  aria-label="New memory"
                  className={`${input} resize-none`}
                />
                <button
                  type="submit"
                  disabled={!draft.trim()}
                  className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  Add
                </button>
              </form>
              {add.error && <p className="text-sm text-red-500">{errorMessage(add.error)}</p>}

              {data.memories.length === 0 ? (
                <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
                  Nothing remembered yet.
                </p>
              ) : (
                <>
                  <ul className="space-y-2" aria-label="Memories">
                    {data.memories.map((m) => (
                      <Row key={`${m.id}:${m.updated_at}`} memory={m} />
                    ))}
                  </ul>
                  <div className="flex items-center justify-between gap-2 pt-2 text-sm">
                    <span className="text-zinc-500">
                      {data.memories.length} {data.memories.length === 1 ? 'memory' : 'memories'}
                    </span>
                    {confirmClear ? (
                      <span className="flex items-center gap-2">
                        <span>Delete all memories?</span>
                        <button
                          type="button"
                          className={button}
                          onClick={() => setConfirmClear(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => clear.mutate()}
                          disabled={clear.isPending}
                          className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                        >
                          Delete all
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className={button}
                        onClick={() => setConfirmClear(true)}
                      >
                        Delete all
                      </button>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
