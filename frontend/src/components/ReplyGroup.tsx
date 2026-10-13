import type { ReactNode } from 'react'
import type { Rating, Source, ToolInfo, ToolTrace } from '../types/api'
import MessageBubble, { type MessageActions } from './MessageBubble'

export interface ReplyColumn {
  key: string | number
  slot: number
  /** The model's label; null while an arena model is hidden. */
  model: { name: string; provider: string } | null
  content: string
  streaming?: boolean
  error?: string
  sources?: Source[] | null
  toolCalls?: ToolTrace[] | null
  rating?: Rating | null
  actions?: MessageActions
}

export type Vote = 'a' | 'b' | 'tie' | 'bad'

interface Props {
  columns: ReplyColumn[]
  toolInfo?: ToolInfo[]
  /** Arena: columns are "Model A", "Model B"… and the user votes for one. */
  blind?: boolean
  onVote?: (vote: Vote) => void
  voting?: boolean
}

const letter = (slot: number) => String.fromCharCode(65 + slot)

function VoteBar({ onVote, voting }: { onVote: (v: Vote) => void; voting?: boolean }) {
  const button =
    'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
  return (
    <div
      className="flex flex-wrap items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-300 p-3 dark:border-zinc-700"
      role="group"
      aria-label="Vote"
    >
      <span className="w-full text-center text-sm text-zinc-500 sm:w-auto">
        Which answer is better?
      </span>
      <button type="button" className={button} disabled={voting} onClick={() => onVote('a')}>
        👈 A is better
      </button>
      <button type="button" className={button} disabled={voting} onClick={() => onVote('tie')}>
        🤝 Tie
      </button>
      <button type="button" className={button} disabled={voting} onClick={() => onVote('bad')}>
        👎 Both are bad
      </button>
      <button type="button" className={button} disabled={voting} onClick={() => onVote('b')}>
        B is better 👉
      </button>
    </div>
  )
}

function verdict(columns: ReplyColumn[]): ReactNode {
  const [a, b] = columns
  if (!a || !b || a.rating == null || b.rating == null) return null
  const text =
    a.rating > b.rating
      ? 'You preferred A'
      : a.rating < b.rating
        ? 'You preferred B'
        : a.rating > 0
          ? 'You called it a tie'
          : 'You thought both were bad'
  return <p className="text-center text-sm text-zinc-500">{text}. The models are revealed above.</p>
}

/** Replies from several models to the same message, side by side. */
export default function ReplyGroup({ columns, toolInfo, blind, onVote, voting }: Props) {
  const sorted = [...columns].sort((x, y) => x.slot - y.slot)
  const revealed = sorted.some((c) => c.rating != null)
  const finished = sorted.every((c) => !c.streaming)
  const cols = sorted.length >= 3 ? 'lg:grid-cols-3' : 'md:grid-cols-2'
  return (
    <div className="space-y-3">
      <div className={`grid gap-4 ${cols}`}>
        {sorted.map((c) => {
          const model = blind
            ? {
                name: `Model ${letter(c.slot)}`,
                provider: c.model ? `${c.model.name}` : 'hidden',
              }
            : (c.model ?? undefined)
          return (
            <div
              key={c.key}
              className="min-w-0 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800"
            >
              <MessageBubble
                role="assistant"
                content={c.content}
                model={model}
                streaming={c.streaming}
                sources={c.sources}
                toolCalls={c.toolCalls}
                toolInfo={toolInfo}
                // In the arena the vote stands in for 👍/👎 until it's cast.
                actions={blind && !revealed ? undefined : c.actions}
              />
              {c.error && <p className="mt-2 text-sm text-red-500">{c.error}</p>}
            </div>
          )
        })}
      </div>
      {blind && !revealed && finished && onVote && <VoteBar onVote={onVote} voting={voting} />}
      {blind && revealed && verdict(sorted)}
    </div>
  )
}
