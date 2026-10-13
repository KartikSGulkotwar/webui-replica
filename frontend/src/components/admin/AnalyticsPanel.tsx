import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getAnalytics } from '../../api/admin'
import { errorMessage } from '../../api/client'
import { useModels } from '../../hooks/useModels'
import { modelLabel } from '../../lib/models'
import type { UsageReport } from '../../types/api'

const PERIODS = [7, 30, 90] as const
const number = new Intl.NumberFormat()
const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })
const th = 'px-3 py-2 text-left text-xs font-medium text-zinc-500'
const td = 'px-3 py-2 tabular-nums'

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })

/** Round the axis top up to 1, 2 or 5 × 10ⁿ so gridline labels are tidy. */
function niceMax(value: number): number {
  if (value <= 4) return 4
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 5, 10].find((s) => s * power >= value) ?? 10
  return step * power
}

function Tile({ value, label, note }: { value: string; label: string; note?: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-sm text-zinc-500">{label}</p>
      {note && <p className="mt-0.5 text-xs text-zinc-500">{note}</p>}
    </div>
  )
}

function DailyChart({ days }: { days: UsageReport['daily'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const top = niceMax(Math.max(...days.map((d) => d.messages)))
  const current = hover === null ? null : days[hover]
  const at = hover === null ? 0 : (hover + 0.5) / days.length
  // Near an edge the tooltip opens inwards so it stays inside the card.
  const shift = at > 0.75 ? '-translate-x-full' : at < 0.25 ? '' : '-translate-x-1/2'
  const middle = days[Math.floor((days.length - 1) / 2)]

  return (
    <figure className="space-y-2">
      <figcaption className="text-sm font-medium">Messages per day</figcaption>
      <div className="relative h-48 pl-9">
        {/* Recessive gridlines with their values. */}
        {[1, 0.5, 0].map((f) => (
          <div
            key={f}
            className="absolute left-9 right-0 border-t border-zinc-200/70 dark:border-zinc-800"
            style={{ bottom: `${f * 100}%` }}
            aria-hidden="true"
          >
            <span className="absolute -left-9 w-7 -translate-y-1/2 text-right text-[11px] tabular-nums text-zinc-500">
              {compact.format(top * f)}
            </span>
          </div>
        ))}
        <div className="absolute inset-0 left-9 flex items-end gap-[2px]">
          {days.map((d, i) => (
            // The whole column is the hover target, bigger than the bar.
            <div
              key={d.date}
              tabIndex={0}
              aria-label={`${shortDate(d.date)}: ${d.messages} messages, ${d.replies} replies, ${d.active_users} people`}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              className={`flex h-full min-w-0 flex-1 items-end rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                hover === i ? 'bg-zinc-100 dark:bg-zinc-900' : ''
              }`}
            >
              <div
                className={`w-full rounded-t-[4px] ${hover === i ? 'bg-indigo-600 dark:bg-indigo-400' : 'bg-indigo-500'}`}
                style={{ height: `${(d.messages / top) * 100}%`, minHeight: d.messages ? 2 : 0 }}
              />
            </div>
          ))}
        </div>
        {current && hover !== null && (
          <div
            className={`pointer-events-none absolute top-0 z-10 w-max ${shift} rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900`}
            style={{ left: `calc(2.25rem + (100% - 2.25rem) * ${at})` }}
            role="status"
          >
            <p className="text-zinc-500">{shortDate(current.date)}</p>
            <p>
              <strong className="text-sm tabular-nums">{number.format(current.messages)}</strong>{' '}
              messages
            </p>
            <p className="text-zinc-600 tabular-nums dark:text-zinc-400">
              {number.format(current.replies)} replies · {compact.format(current.tokens)} tokens ·{' '}
              {current.active_users} {current.active_users === 1 ? 'person' : 'people'}
            </p>
          </div>
        )}
      </div>
      <div
        className="flex justify-between whitespace-nowrap pl-9 text-[11px] text-zinc-500"
        aria-hidden="true"
      >
        <span>{shortDate(days[0].date)}</span>
        {days.length > 2 && <span>{shortDate(middle.date)}</span>}
        <span>{shortDate(days[days.length - 1].date)}</span>
      </div>
    </figure>
  )
}

export default function AnalyticsPanel() {
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30)
  const [asTable, setAsTable] = useState(false)
  const report = useQuery({
    queryKey: ['admin', 'analytics', days],
    queryFn: () => getAnalytics(days),
  })
  const models = useModels()
  const data = report.data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Analytics</h2>
          <p className="text-sm text-zinc-500">How the site is used. Days are in UTC.</p>
        </div>
        <div
          className="flex rounded-lg border border-zinc-300 p-0.5 text-sm dark:border-zinc-700"
          role="group"
          aria-label="Period"
        >
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={days === p}
              onClick={() => setDays(p)}
              className={`rounded-md px-3 py-1 ${
                days === p
                  ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                  : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800'
              }`}
            >
              {p} days
            </button>
          ))}
        </div>
      </div>
      {report.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {report.isError && <p className="text-sm text-red-500">{errorMessage(report.error)}</p>}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile value={number.format(data.totals.period_messages)} label="Messages" />
            <Tile value={number.format(data.totals.active_users)} label="Active people" />
            <Tile
              value={compact.format(data.totals.period_tokens)}
              label="Tokens"
              note="Prompt + reply, as reported by providers"
            />
            <Tile
              value={number.format(data.totals.users)}
              label="Accounts"
              note={`+ ${number.format(data.totals.guests)} guests · ${number.format(data.totals.conversations)} chats in total`}
            />
          </div>

          <div className="space-y-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            {asTable ? (
              <div className="max-h-72 overflow-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Activity per day</caption>
                  <thead className="sticky top-0 border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
                    <tr>
                      <th className={th}>Day</th>
                      <th className={`${th} text-right`}>Messages</th>
                      <th className={`${th} text-right`}>Replies</th>
                      <th className={`${th} text-right`}>Tokens</th>
                      <th className={`${th} text-right`}>People</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
                    {[...data.daily].reverse().map((d) => (
                      <tr key={d.date}>
                        <td className="px-3 py-1.5">{shortDate(d.date)}</td>
                        <td className={`${td} text-right`}>{number.format(d.messages)}</td>
                        <td className={`${td} text-right`}>{number.format(d.replies)}</td>
                        <td className={`${td} text-right`}>{number.format(d.tokens)}</td>
                        <td className={`${td} text-right`}>{d.active_users}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DailyChart days={data.daily} />
            )}
            <button
              type="button"
              onClick={() => setAsTable((t) => !t)}
              className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
            >
              {asTable ? 'Show chart' : 'Show as table'}
            </button>
          </div>

          <div className="space-y-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            <h3 className="text-sm font-medium">By model</h3>
            {data.models.length === 0 ? (
              <p className="text-sm text-zinc-500">No replies in this period.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-zinc-200 dark:border-zinc-800">
                    <tr>
                      <th className={th}>Model</th>
                      <th className={`${th} text-right`}>Replies</th>
                      <th className={`${th} text-right`}>Tokens in</th>
                      <th className={`${th} text-right`}>Tokens out</th>
                      <th className={`${th} text-right`}>👍 · 👎</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
                    {data.models.map((m) => {
                      const l = modelLabel(m.model_id, models.data?.models)
                      return (
                        <tr key={m.model_id}>
                          <td className="px-3 py-2">
                            <span className="font-medium">{l.name}</span>
                            {l.provider && <span className="text-zinc-500"> · {l.provider}</span>}
                          </td>
                          <td className={`${td} text-right`}>{number.format(m.replies)}</td>
                          <td className={`${td} text-right`}>{compact.format(m.prompt_tokens)}</td>
                          <td className={`${td} text-right`}>
                            {compact.format(m.completion_tokens)}
                          </td>
                          <td className={`${td} text-right text-zinc-600 dark:text-zinc-400`}>
                            {m.likes} · {m.dislikes}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
