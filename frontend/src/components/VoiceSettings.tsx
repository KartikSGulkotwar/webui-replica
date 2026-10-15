import { useEffect, useState } from 'react'
import { useAppConfig } from '../hooks/useProviders'
import { browserCanSpeak, speak, stopSpeaking } from '../lib/speech'
import { getVoicePrefs, setVoicePrefs, type VoicePrefs } from '../lib/voicePrefs'

const select =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-900'

/** The browser voice used to read replies aloud (kept in this browser). */
export default function VoiceSettings() {
  const config = useAppConfig()
  const [prefs, setPrefs] = useState<VoicePrefs>(getVoicePrefs)
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])

  useEffect(() => {
    if (!browserCanSpeak()) return
    // Voices load asynchronously in some browsers.
    const load = () => setVoices(window.speechSynthesis.getVoices())
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', load)
  }, [])

  const update = (patch: Partial<VoicePrefs>) => {
    const next = { ...prefs, ...patch }
    setPrefs(next)
    setVoicePrefs(next)
  }

  if (config.data?.text_to_speech) {
    return (
      <p className="text-sm text-zinc-500">
        Replies are read aloud with this site’s voice (set by an admin).
      </p>
    )
  }
  if (!browserCanSpeak()) {
    return <p className="text-sm text-zinc-500">This browser can’t read text aloud.</p>
  }
  const lang = navigator.language.split('-')[0]
  // The reader's own language first.
  const sorted = [...voices].sort(
    (a, b) =>
      Number(b.lang.startsWith(lang)) - Number(a.lang.startsWith(lang)) ||
      a.name.localeCompare(b.name),
  )
  return (
    <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
      <div>
        <label htmlFor="voice" className="mb-1 block text-sm font-medium">
          Voice
        </label>
        <select
          id="voice"
          value={prefs.voice}
          onChange={(e) => update({ voice: e.target.value })}
          className={select}
        >
          <option value="">Browser default</option>
          {sorted.map((v) => (
            <option key={v.voiceURI} value={v.voiceURI}>
              {v.name} ({v.lang})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="voice-rate" className="mb-1 block text-sm font-medium">
          Speed · {prefs.rate.toFixed(1)}×
        </label>
        <input
          id="voice-rate"
          type="range"
          min={0.6}
          max={1.8}
          step={0.1}
          value={prefs.rate}
          onChange={(e) => update({ rate: Number(e.target.value) })}
          className="w-full accent-indigo-600"
        />
      </div>
      <div className="flex gap-2 sm:col-span-2">
        <button
          type="button"
          onClick={() =>
            void speak('Hello! This is how I’ll read replies to you.', 'voice-preview', false)
          }
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          ▶ Try it
        </button>
        <button
          type="button"
          onClick={stopSpeaking}
          className="rounded-lg px-3 py-1.5 text-sm text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          Stop
        </button>
      </div>
    </div>
  )
}
