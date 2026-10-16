import { useId, useState, useSyncExternalStore } from 'react'
import { errorMessage } from '../api/client'
import { useAppConfig } from '../hooks/useProviders'
import { useT } from '../lib/i18n'
import { browserCanSpeak, getSpeakingId, speak, stopSpeaking, subscribeSpeech } from '../lib/speech'

const SpeakerIcon = () => (
  <svg
    width="15"
    height="15"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M11 5 6 9H2v6h4l5 4V5z" />
    <path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14" />
  </svg>
)
const StopSquare = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
)

/** Reads a reply aloud (the server's voice if set up, otherwise the browser's). */
export default function ReadAloudButton({ text }: { text: string }) {
  const id = useId()
  const t = useT()
  const config = useAppConfig()
  const speakingId = useSyncExternalStore(subscribeSpeech, getSpeakingId)
  const [error, setError] = useState<string | null>(null)
  const useServer = !!config.data?.text_to_speech
  if (!useServer && !browserCanSpeak()) return null
  const speaking = speakingId === id

  return (
    <button
      type="button"
      onClick={() => {
        setError(null)
        if (speaking) stopSpeaking()
        else speak(text, id, useServer).catch((err) => setError(errorMessage(err)))
      }}
      className={`rounded-md p-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 ${
        speaking
          ? 'text-indigo-500'
          : error
            ? 'text-red-500'
            : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100'
      }`}
      aria-label={speaking ? t('msg.stopReading') : t('msg.readAloud')}
      aria-pressed={speaking}
      title={error ?? (speaking ? t('msg.stopReading') : t('msg.readAloud'))}
    >
      {speaking ? <StopSquare /> : <SpeakerIcon />}
    </button>
  )
}
