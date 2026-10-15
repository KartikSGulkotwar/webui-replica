import { useEffect, useRef, useState } from 'react'
import { transcribe } from '../api/audio'
import { errorMessage } from '../api/client'
import { browserCanListen, listen } from '../lib/browserDictation'
import { canRecord, startRecording, type Recording } from '../lib/recorder'

export const MicIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10a7 7 0 0 0 14 0M12 17v5" />
  </svg>
)

const MAX_RECORDING_MS = 120_000

interface Props {
  /** Add dictated text to the message box. */
  onText: (text: string) => void
  /** The server transcribes recordings; otherwise the browser listens itself. */
  serverStt: boolean
  disabled?: boolean
}

type State = 'idle' | 'listening' | 'transcribing'

/** Dictate a message: click to start, click again to stop. */
export default function DictationButton({ onText, serverStt, disabled }: Props) {
  const [state, setState] = useState<State>('idle')
  const [error, setError] = useState<string | null>(null)
  const [seconds, setSeconds] = useState(0)
  const recording = useRef<Recording | null>(null)
  const stopListening = useRef<(() => void) | null>(null)
  const available = serverStt ? canRecord() : browserCanListen()

  // Stop the microphone if the composer goes away mid-dictation.
  useEffect(
    () => () => {
      recording.current?.cancel()
      stopListening.current?.()
    },
    [],
  )
  useEffect(() => {
    if (state !== 'listening') return
    setSeconds(0)
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(t)
  }, [state])

  if (!available) return null

  const finishRecording = async () => {
    const rec = recording.current
    recording.current = null
    if (!rec) return
    setState('transcribing')
    try {
      const audio = await rec.stop()
      if (audio) {
        const text = await transcribe(audio)
        if (text) onText(text)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setState('idle')
    }
  }

  const start = async () => {
    setError(null)
    if (serverStt) {
      try {
        recording.current = await startRecording({
          maxDuration: MAX_RECORDING_MS,
          onAutoStop: () => void finishRecording(),
        })
        setState('listening')
      } catch {
        setError('Microphone access was blocked')
      }
    } else {
      setState('listening')
      stopListening.current = listen({
        onText: (text) => text && onText(text),
        onError: (message) => setError(message),
        onEnd: () => {
          stopListening.current = null
          setState('idle')
        },
      })
    }
  }

  const stop = () => {
    if (serverStt) void finishRecording()
    else stopListening.current?.()
  }

  const label =
    state === 'listening'
      ? 'Stop dictation'
      : state === 'transcribing'
        ? 'Transcribing…'
        : 'Dictate'
  return (
    <button
      type="button"
      onClick={state === 'listening' ? stop : start}
      disabled={disabled || state === 'transcribing'}
      aria-label={label}
      aria-pressed={state === 'listening'}
      title={error ?? label}
      className={`flex items-center gap-1 self-end rounded-xl p-2 text-xs font-medium disabled:opacity-40 ${
        state === 'listening'
          ? 'bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-300'
          : error
            ? 'text-red-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'
            : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'
      }`}
    >
      {state === 'transcribing' ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <MicIcon />
      )}
      {state === 'listening' && (
        <span className="tabular-nums">
          <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
        </span>
      )}
    </button>
  )
}
