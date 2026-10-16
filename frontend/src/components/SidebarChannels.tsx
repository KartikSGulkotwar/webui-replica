import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { createChannel, listChannels } from '../api/channels'
import { errorMessage } from '../api/client'
import Dialog from './Dialog'
import { PlusIcon } from './icons'
import { useT } from '../lib/i18n'

/** "Channels" in the sidebar; admins can add one. */
export default function SidebarChannels({
  isAdmin,
  onNavigate,
}: {
  isAdmin: boolean
  onNavigate: () => void
}) {
  const channels = useQuery({ queryKey: ['channels'], queryFn: listChannels })
  const t = useT()
  const [creating, setCreating] = useState(false)
  if (!channels.data?.length && !isAdmin) return null
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between px-3 py-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          {t('nav.channels')}
        </span>
        {isAdmin && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            aria-label={t('nav.newChannel')}
            title={t('nav.newChannel')}
          >
            <PlusIcon width={14} height={14} />
          </button>
        )}
      </div>
      {channels.data?.map((c) => (
        <NavLink
          key={c.id}
          to={`/channels/${c.id}`}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-1.5 truncate rounded-lg px-3 py-1 text-sm ${
              isActive
                ? 'bg-zinc-200 dark:bg-zinc-800'
                : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800/60'
            }`
          }
        >
          <span className="text-zinc-400">#</span>
          <span className="truncate">{c.name}</span>
        </NavLink>
      ))}
      {isAdmin && channels.data?.length === 0 && (
        <p className="px-3 text-xs text-zinc-500">No channels yet.</p>
      )}
      {creating && (
        <NewChannel
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false)
            onNavigate()
          }}
        />
      )}
    </div>
  )
}

function NewChannel({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => createChannel({ name, description }),
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      navigate(`/channels/${channel.id}`)
      onCreated()
    },
  })
  const input =
    'mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
  return (
    <Dialog title="New channel" onClose={onClose}>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          create.mutate()
        }}
        className="space-y-3 p-4"
      >
        <label className="block text-sm font-medium">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="general"
            required
            maxLength={80}
            autoFocus
            className={input}
          />
        </label>
        <label className="block text-sm font-medium">
          Description <span className="font-normal text-zinc-500">(optional)</span>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What it's for"
            maxLength={500}
            className={input}
          />
        </label>
        <p className="text-xs text-zinc-500">
          Every signed-in person can read and post. Type @ in a message to bring a model in.
        </p>
        {create.error && <p className="text-sm text-red-500">{errorMessage(create.error)}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Create
          </button>
        </div>
      </form>
    </Dialog>
  )
}
