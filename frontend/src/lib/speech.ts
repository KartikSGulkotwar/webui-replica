import { synthesize } from '../api/audio'
import { splitForSpeech, toSpeakable } from './speechText'
import { getVoicePrefs } from './voicePrefs'

/**
 * One read-aloud at a time for the whole app. Uses the server's voice when
 * there is one, otherwise the browser's (speechSynthesis).
 */
let speakingId: string | null = null
let audio: HTMLAudioElement | null = null
let finish: (() => void) | null = null
const listeners = new Set<() => void>()

const notify = (id: string | null) => {
  speakingId = id
  listeners.forEach((l) => l())
}

export const subscribeSpeech = (listener: () => void) => {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
export const getSpeakingId = () => speakingId

export const browserCanSpeak = () => typeof window !== 'undefined' && 'speechSynthesis' in window

export function stopSpeaking(): void {
  audio?.pause()
  audio = null
  if (browserCanSpeak()) window.speechSynthesis.cancel()
  const done = finish
  finish = null
  notify(null)
  done?.()
}

function pickVoice(): SpeechSynthesisVoice | undefined {
  const { voice } = getVoicePrefs()
  return voice ? window.speechSynthesis.getVoices().find((v) => v.voiceURI === voice) : undefined
}

/** Read `text` aloud; resolves when it ends or is stopped. */
export async function speak(text: string, id: string, useServer: boolean): Promise<void> {
  stopSpeaking()
  const spoken = toSpeakable(text)
  if (!spoken) return
  notify(id)
  try {
    if (useServer) {
      const blob = await synthesize(spoken)
      if (speakingId !== id) return // stopped while loading
      const url = URL.createObjectURL(blob)
      const player = new Audio(url)
      audio = player
      await new Promise<void>((resolve) => {
        finish = resolve
        player.onended = () => resolve()
        player.onerror = () => resolve()
        player.play().catch(() => resolve())
      })
      URL.revokeObjectURL(url)
    } else if (browserCanSpeak()) {
      const { rate } = getVoicePrefs()
      const voice = pickVoice()
      const chunks = splitForSpeech(spoken)
      await new Promise<void>((resolve) => {
        finish = resolve
        chunks.forEach((chunk, i) => {
          const u = new SpeechSynthesisUtterance(chunk)
          if (voice) u.voice = voice
          u.rate = rate
          if (i === chunks.length - 1) {
            u.onend = () => resolve()
            u.onerror = () => resolve()
          }
          window.speechSynthesis.speak(u)
        })
      })
    }
  } finally {
    if (speakingId === id) {
      finish = null
      audio = null
      notify(null)
    }
  }
}
