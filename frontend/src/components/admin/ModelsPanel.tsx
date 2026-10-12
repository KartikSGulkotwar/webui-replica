import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { errorMessage } from '../../api/client'
import { listAdminModels, updateAdminModel } from '../../api/customModels'
import type { AdminModel } from '../../types/api'

const key = ['admin', 'models'] as const

function ModelRow({ model }: { model: AdminModel }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(model.display_name ?? '')
  // Flip the switch right away; roll back if saving fails.
  const [hidden, setHidden] = useState(model.hidden)
  const save = useMutation({
    mutationFn: (patch: { hidden?: boolean; display_name?: string }) =>
      updateAdminModel({
        model_id: model.id,
        hidden: patch.hidden ?? hidden,
        display_name: patch.display_name ?? (model.display_name || null),
      }),
    onMutate: (patch) => {
      if (patch.hidden !== undefined) setHidden(patch.hidden)
    },
    onError: () => setHidden(model.hidden),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key })
      queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })

  return (
    <li
      className={`flex flex-wrap items-center gap-3 px-4 py-2.5 ${model.hidden ? 'opacity-60' : ''}`}
    >
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm">{model.name}</p>
        {model.hidden && (
          <p className="text-xs text-amber-600 dark:text-amber-400">Hidden from everyone</p>
        )}
      </div>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={() =>
          name.trim() !== (model.display_name ?? '') && save.mutate({ display_name: name.trim() })
        }
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        placeholder="Display name (optional)"
        aria-label={`Display name for ${model.name}`}
        maxLength={100}
        className="w-48 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950"
      />
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          role="switch"
          checked={!hidden}
          onChange={(e) => save.mutate({ hidden: !e.target.checked })}
          aria-label={`Show ${model.name} in the model menu`}
          className="h-4 w-4 accent-indigo-600"
        />
        Visible
      </label>
      {save.error && <p className="w-full text-xs text-red-500">{errorMessage(save.error)}</p>}
    </li>
  )
}

export default function ModelsPanel() {
  const models = useQuery({ queryKey: key, queryFn: listAdminModels })
  const groups = new Map<string, AdminModel[]>()
  for (const m of models.data ?? [])
    groups.set(m.provider_name, [...(groups.get(m.provider_name) ?? []), m])

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Models</h2>
        <p className="text-sm text-zinc-500">
          Choose which provider models appear in everyone’s model menu, and give them friendlier
          names. Hidden models can still power public custom models you create.
        </p>
      </div>
      {models.isLoading && <p className="text-sm text-zinc-500">Loading models…</p>}
      {models.isError && <p className="text-sm text-red-500">{errorMessage(models.error)}</p>}
      {models.isSuccess && models.data.length === 0 && (
        <p className="text-sm text-zinc-500">No models: add a provider under Connections.</p>
      )}
      {[...groups.entries()].map(([provider, rows]) => (
        <section key={provider}>
          <h3 className="mb-1 text-sm font-medium text-zinc-500">
            {provider} · {rows.filter((r) => !r.hidden).length} of {rows.length} visible
          </h3>
          <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
            {rows.map((m) => (
              <ModelRow key={m.id} model={m} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
