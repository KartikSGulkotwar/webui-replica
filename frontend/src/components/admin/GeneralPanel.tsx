import { errorMessage } from '../../api/client'
import { useAdminSettings, useSaveAdminSettings } from '../../hooks/useAdmin'
import type { AdminSettings } from '../../types/api'

export default function GeneralPanel() {
  const settings = useAdminSettings()
  const save = useSaveAdminSettings()

  const update = (patch: Partial<AdminSettings>) => {
    if (settings.data) save.mutate({ ...settings.data, ...patch })
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Sign-up</h2>
        <p className="text-sm text-zinc-500">Who can create an account on this site.</p>
      </div>
      {settings.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {settings.isError && <p className="text-sm text-red-500">{errorMessage(settings.error)}</p>}
      {settings.data && (
        <div className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          <label className="flex cursor-pointer items-center justify-between gap-4 p-4">
            <span>
              <span className="block text-sm font-medium">Allow new sign-ups</span>
              <span className="block text-xs text-zinc-500">
                When off, only existing accounts can sign in.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              checked={settings.data.enable_signup}
              onChange={(e) => update({ enable_signup: e.target.checked })}
              disabled={save.isPending}
              className="h-4 w-4 accent-indigo-600"
            />
          </label>
          <label className="flex items-center justify-between gap-4 p-4">
            <span>
              <span className="block text-sm font-medium">Role for new accounts</span>
              <span className="block text-xs text-zinc-500">
                “Pending” accounts wait for you to approve them in Users.
              </span>
            </span>
            <select
              value={settings.data.default_user_role}
              onChange={(e) =>
                update({ default_user_role: e.target.value as AdminSettings['default_user_role'] })
              }
              disabled={save.isPending}
              className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="pending">Pending (needs approval)</option>
              <option value="user">User (can chat right away)</option>
            </select>
          </label>
        </div>
      )}
      {save.isError && <p className="text-sm text-red-500">{errorMessage(save.error)}</p>}
      {save.isSuccess && <p className="text-sm text-emerald-600 dark:text-emerald-400">Saved.</p>}
    </div>
  )
}
