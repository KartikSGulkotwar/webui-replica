import { useCallback, useEffect, useRef, useState } from 'react'
import { transcribe } from '../api/audio'
import { errorMessage } from '../api/client'
import { listen } from '../lib/browserDictation'
import { startRecording, type Recording } from '../lib/recorder'
import { speak, stopSpeaking } from '../lib/speech'

export interface VoiceReply {
  /** Changes for every new exchange. */
  key: string
  text: string
  done: boolean
  error?: string
}

interface Props {
  serverStt: boolean
  serverTts: boolean
  onSend: (text: string) => void
  /** The latest reply (the first one, if several models answer). */
  reply: VoiceReply | null
  onClose: () => void
}

type Phase = 'listening' | 'transcribing' | 'thinking' | 'speaking' | 'paused'

const SILENCE_MS = 1300
const MAX_TURN_MS = 30_000

const STATUS: Record<Phase, string> = {
  listening: 'Listening…',
  transcribing: 'Got it…',
  thinking: 'Thinking…',
  speaking: 'Speaking — tap to interrupt',
  paused: 'Paused',
}

/** Talk with the assistant: it listens, answers out loud, and listens again. */
export default function VoiceMode({ serverStt, serverTts, onSend, reply, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>('listening')
  const [heard, setHeard] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [level, setLevel] = useState(0)
  const recording = useRef<Recording | null>(null)
  const stopBrowser = useRef<(() => void) | null>(null)
  const waitingFor = useRef<string | null>(null) // reply key before our message
  const open = useRef(true)

  const send = useCallback(
    (text: string) => {
      setHeard(text)
      waitingFor.current = reply?.key ?? ''
      setPhase('thinking')
      onSend(text)
    },
    [onSend, reply?.key],
  )

  const startListening = useCallback(async () => {
    if (!open.current) return
    setError(null)
    setHeard('') // a new turn
    setPhase('listening')
    if (serverStt) {
      try {
        const rec = await startRecording({
          untilSilence: SILENCE_MS,
          maxDuration: MAX_TURN_MS,
          onAutoStop: () => void finish(),
        })
        recording.current = rec
      } catch {
        setError('Microphone access was blocked')
        setPhase('paused')
      }
    } else {
      let said = ''
      stopBrowser.current = listen({
        continuous: false,
        onText: (t) => (said = `${said} ${t}`.trim()),
        onInterim: (t) => setHeard(t),
        onError: (message) => {
          setError(message)
          setPhase('paused')
        },
        onEnd: () => {
          stopBrowser.current = null
          if (!open.current) return
          if (said) send(said)
          else void startListening() // nothing heard yet: keep listening
        },
      })
    }

    async function finish() {
      const rec = recording.current
      recording.current = null
      if (!rec) return
      setPhase('transcribing')
      try {
        const audio = await rec.stop()
        const text = audio ? await transcribe(audio) : ''
        if (!open.current) return
        if (text) send(text)
        else void startListening()
      } catch (err) {
        setError(errorMessage(err))
        setPhase('paused')
      }
    }
  }, [serverStt, send])

  const stopAll = () => {
    recording.current?.cancel()
    recording.current = null
    stopBrowser.current?.()
    stopBrowser.current = null
    stopSpeaking()
  }

  // Start listening when opened; release the microphone when closed.
  useEffect(() => {
    open.current = true
    void startListening()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      open.current = false
      document.removeEventListener('keydown', onKey)
      stopAll()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The microphone level drives the orb while listening.
  useEffect(() => {
    if (phase !== 'listening' || !serverStt) return setLevel(0)
    let frame = 0
    const tick = () => {
      setLevel(recording.current?.level() ?? 0)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [phase, serverStt])

  // When the reply to our message is finished, read it out, then listen again.
  useEffect(() => {
    if (phase !== 'thinking' || !reply || reply.key === waitingFor.current || !reply.done) return
    if (reply.error) {
      setError(reply.error)
      setPhase('paused')
      return
    }
    setPhase('speaking')
    speak(reply.text, 'voice-mode', serverTts)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => {
        if (open.current) void startListening()
      })
  }, [phase, reply, serverTts, startListening])

  const onOrb = () => {
    if (phase === 'speaking')
      stopSpeaking() // the .finally above resumes listening
    else if (phase === 'paused') void startListening()
    else if (phase === 'listening') {
      stopAll()
      setPhase('paused')
    }
  }

  const scale = phase === 'listening' ? 1 + level * 0.6 : 1
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-white/95 p-6 text-center backdrop-blur dark:bg-zinc-950/95"
      role="dialog"
      aria-modal="true"
      aria-label="Voice mode"
    >
      <button
        type="button"
        onClick={onOrb}
        aria-label={
          phase === 'speaking'
            ? 'Interrupt'
            : phase === 'paused'
              ? 'Resume listening'
              : 'Pause listening'
        }
        className={`h-40 w-40 rounded-full transition-transform duration-100 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-400 ${
          phase === 'paused'
            ? 'bg-zinc-300 dark:bg-zinc-700'
            : phase === 'speaking'
              ? 'animate-pulse bg-indigo-500'
              : phase === 'thinking' || phase === 'transcribing'
                ? 'animate-pulse bg-indigo-300 dark:bg-indigo-800'
                : 'bg-indigo-600'
        }`}
        style={{ transform: `scale(${scale})` }}
      />
      <div className="max-w-md space-y-2" aria-live="polite">
        <p className="text-lg font-medium">{error ?? STATUS[phase]}</p>
        {heard && <p className="text-sm text-zinc-500">“{heard}”</p>}
        {phase === 'paused' && !error && (
          <p className="text-sm text-zinc-500">Tap the circle to keep talking.</p>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="rounded-full border border-zinc-300 px-6 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
      >
        End voice mode
      </button>
    </div>
  )
}
