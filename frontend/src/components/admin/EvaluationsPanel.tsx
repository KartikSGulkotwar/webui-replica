import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getLeaderboard } from '../../api/admin'
import { errorMessage } from '../../api/client'
import { listAdminModels } from '../../api/customModels'
import { useAdminSettings, useSaveAdminSettings } from '../../hooks/useAdmin'
import { useModels } from '../../hooks/useModels'
import { modelLabel } from '../../lib/models'

const section = 'space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800'
const th = 'px-3 py-2 text-left text-xs font-medium text-zinc-500'
const td = 'px-3 py-2 tabular-nums'

function ArenaModels() {
  const settings = useAdminSettings()
  const save = useSaveAdminSettings()
  const queryClient = useQueryClient()
  const models = useQuery({ queryKey: ['admin', 'models'], queryFn: listAdminModels })
  const [draft, setDraft] = useState<string[] | null>(null)
  const saved = settings.data?.arena_models ?? []
  const chosen = draft ?? saved
  const dirty = draft !== null && [...draft].sort().join() !== [...saved].sort().join()

  const toggle = (id: string) =>
    setDraft(chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id])

  return (
    <div className={section}>
      <div>
        <h3 className="font-medium">Arena</h3>
        <p className="text-sm text-zinc-500">
          Pick the models that compete. Each message in the ⚔️ Arena goes to two of them at random,
          with their names hidden until the person votes. Choose at least two to show the Arena in
          the model menu.
        </p>
      </div>
      {models.isLoading && <p className="text-sm text-zinc-500">Loading models…</p>}
      {models.isError && <p className="text-sm text-red-500">{errorMessage(models.error)}</p>}
      {models.data && (
        <div className="flex flex-wrap gap-2">
          {models.data.map((m) => {
            const on = chosen.includes(m.id)
            return (
              <label
                key={m.id}
                className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${
                  on
                    ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950'
                    : 'border-zinc-300 dark:border-zinc-700'
                }`}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggle(m.id)}
                  className="accent-indigo-600"
                />
                {m.display_name ?? m.name}
                <span className="text-xs text-zinc-500">· {m.provider_name}</span>
                {m.hidden && <span className="text-xs text-zinc-500">(hidden)</span>}
              </label>
            )
          })}
        </div>
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!dirty || save.isPending || !settings.data}
          onClick={() =>
            settings.data &&
            save.mutate(
              { ...settings.data, arena_models: chosen },
              {
                onSuccess: () => {
                  setDraft(null)
                  queryClient.invalidateQueries({ queryKey: ['models'] })
                },
              },
            )
          }
          className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          Save
        </button>
        <span className="text-sm text-zinc-500">
          {chosen.length} chosen{chosen.length === 1 ? ' — choose one more' : ''}
        </span>
        {save.isError && <span className="text-sm text-red-500">{errorMessage(save.error)}</span>}
      </div>
    </div>
  )
}

function Leaderboard() {
  const board = useQuery({ queryKey: ['admin', 'leaderboard'], queryFn: getLeaderboard })
  const models = useModels()
  return (
    <div className={section}>
      <div>
        <h3 className="font-medium">Leaderboard</h3>
        <p className="text-sm text-zinc-500">
          Built from people’s ratings. When replies are shown side by side (compared models or the
          Arena), the better-rated one wins the match, and Elo ratings (start: 1000) move with each
          result. 👍 and 👎 count every rated reply.
        </p>
      </div>
      {board.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {board.isError && <p className="text-sm text-red-500">{errorMessage(board.error)}</p>}
      {board.data?.length === 0 && (
        <p className="rounded-lg border border-dashed border-zinc-300 px-4 py-6 text-center text-sm text-zinc-500 dark:border-zinc-700">
          No ratings yet. Vote in the Arena or rate replies with 👍/👎.
        </p>
      )}
      {!!board.data?.length && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-zinc-200 dark:border-zinc-800">
              <tr>
                <th className={th}>#</th>
                <th className={th}>Model</th>
                <th className={`${th} text-right`}>Elo</th>
                <th className={`${th} text-right`}>Matches</th>
                <th className={`${th} text-right`}>Won · Lost · Tied</th>
                <th className={`${th} text-right`}>👍 · 👎</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {board.data.map((r, i) => {
                const l = modelLabel(r.model_id, models.data?.models)
                return (
                  <tr key={r.model_id}>
                    <td className={`${td} text-zinc-500`}>{i + 1}</td>
                    <td className="px-3 py-2">
                      <span className="font-medium">{l.name}</span>
                      {l.provider && <span className="text-zinc-500"> · {l.provider}</span>}
                    </td>
                    <td className={`${td} text-right font-semibold`}>{r.elo}</td>
                    <td className={`${td} text-right`}>{r.matches}</td>
                    <td className={`${td} text-right text-zinc-600 dark:text-zinc-400`}>
                      {r.wins} · {r.losses} · {r.ties}
                    </td>
                    <td className={`${td} text-right text-zinc-600 dark:text-zinc-400`}>
                      {r.likes} · {r.dislikes}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function EvaluationsPanel() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Evaluations</h2>
        <p className="text-sm text-zinc-500">
          Find out which models people prefer: blind Arena battles and side-by-side comparisons feed
          a leaderboard.
        </p>
      </div>
      <ArenaModels />
      <Leaderboard />
    </div>
  )
}
