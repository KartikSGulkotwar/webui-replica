/** The browser's own speech recognition (Chrome, Edge, Safari), when there's no server engine. */

interface RecognitionResult {
  isFinal: boolean
  0: { transcript: string }
}
interface RecognitionEvent {
  resultIndex: number
  results: ArrayLike<RecognitionResult>
}
interface Recognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((e: RecognitionEvent) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}
type RecognitionClass = new () => Recognition

const Recognition = (): RecognitionClass | undefined =>
  typeof window === 'undefined'
    ? undefined
    : ((window as unknown as Record<string, RecognitionClass | undefined>).SpeechRecognition ??
      (window as unknown as Record<string, RecognitionClass | undefined>).webkitSpeechRecognition)

export const browserCanListen = () => !!Recognition()

interface Handlers {
  /** Finished phrases. */
  onText: (text: string) => void
  /** What's being heard right now (replaced as it changes). */
  onInterim?: (text: string) => void
  onEnd?: () => void
  onError?: (message: string) => void
  /** Keep listening across pauses (dictation) or stop after one phrase (voice mode). */
  continuous?: boolean
}

/** Start listening; returns a function that stops. */
export function listen({ onText, onInterim, onEnd, onError, continuous = true }: Handlers) {
  const Ctor = Recognition()
  if (!Ctor) {
    onError?.("This browser can't recognize speech")
    return () => {}
  }
  const rec = new Ctor()
  rec.lang = navigator.language || 'en-US'
  rec.continuous = continuous
  rec.interimResults = true
  rec.onresult = (e) => {
    let interim = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i]
      if (r.isFinal) onText(r[0].transcript.trim())
      else interim += r[0].transcript
    }
    onInterim?.(interim)
  }
  rec.onerror = (e) => {
    if (e.error === 'no-speech' || e.error === 'aborted') return
    onError?.(
      e.error === 'not-allowed'
        ? 'Microphone access was blocked'
        : `Speech recognition failed (${e.error})`,
    )
  }
  rec.onend = () => onEnd?.()
  rec.start()
  return () => rec.stop()
}
