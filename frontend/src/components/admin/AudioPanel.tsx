import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { getAudioSettings, saveAudioSettings } from '../../api/audio'
import { errorMessage } from '../../api/client'
import { speak, stopSpeaking } from '../../lib/speech'
import type { AudioSettings, SpeechPart } from '../../types/api'
import DictationButton from '../DictationButton'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'

type Part = Omit<SpeechPart, 'has_key'> & { api_key: string }
interface Preset {
  label: string
  base_url: string
  model: string
  voice?: string
  note?: string
}

const STT_PRESETS: Preset[] = [
  {
    label: 'Groq Whisper',
    base_url: 'https://api.groq.com/openai/v1',
    model: 'whisper-large-v3-turbo',
  },
  { label: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini-transcribe' },
]
const TTS_PRESETS: Preset[] = [
  {
    label: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini-tts',
    voice: 'alloy',
  },
  {
    label: 'Groq Orpheus',
    base_url: 'https://api.groq.com/openai/v1',
    model: 'canopylabs/orpheus-v1-english',
    voice: 'tara',
    note: 'Accept the model’s terms in the Groq console first.',
  },
]

const fromSaved = (p: SpeechPart): Part => ({
  engine: p.engine,
  base_url: p.base_url,
  model: p.model,
  voice: p.voice,
  api_key: '',
})

function PartFields({
  id,
  title,
  description,
  part,
  hasKey,
  presets,
  withVoice,
  onChange,
}: {
  id: string
  title: string
  description: string
  part: Part
  hasKey: boolean
  presets: Preset[]
  withVoice?: boolean
  onChange: (p: Part) => void
}) {
  const set = (patch: Partial<Part>) => onChange({ ...part, ...patch })
  const note = presets.find((p) => p.base_url === part.base_url && p.model === part.model)?.note
  return (
    <fieldset className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <legend className="px-1 font-medium">{title}</legend>
      <p className="text-sm text-zinc-500">{description}</p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="radio"
            name={`${id}-engine`}
            checked={part.engine === ''}
            onChange={() => set({ engine: '' })}
          />
          Browser (free)
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="radio"
            name={`${id}-engine`}
            checked={part.engine === 'openai'}
            onChange={() => set({ engine: 'openai' })}
          />
          OpenAI-compatible API
        </label>
      </div>
      {part.engine === 'openai' && (
        <>
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() =>
                  set({ base_url: p.base_url, model: p.model, voice: p.voice ?? part.voice })
                }
                className="rounded-full border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor={`${id}-url`} className="mb-1 block text-sm font-medium">
                Base URL
              </label>
              <input
                id={`${id}-url`}
                type="url"
                value={part.base_url}
                onChange={(e) => set({ base_url: e.target.value })}
                required
                className={input}
              />
            </div>
            <div>
              <label htmlFor={`${id}-model`} className="mb-1 block text-sm font-medium">
                Model
              </label>
              <input
                id={`${id}-model`}
                value={part.model}
                onChange={(e) => set({ model: e.target.value })}
                required
                className={input}
              />
            </div>
            {withVoice && (
              <div>
                <label htmlFor={`${id}-voice`} className="mb-1 block text-sm font-medium">
                  Voice
                </label>
                <input
                  id={`${id}-voice`}
                  value={part.voice}
                  onChange={(e) => set({ voice: e.target.value })}
                  placeholder="alloy"
                  className={input}
                />
              </div>
            )}
            <div className="sm:col-span-2">
              <label htmlFor={`${id}-key`} className="mb-1 block text-sm font-medium">
                API key
              </label>
              <input
                id={`${id}-key`}
                type="password"
                autoComplete="off"
                value={part.api_key}
                onChange={(e) => set({ api_key: e.target.value })}
                placeholder={hasKey ? 'Saved — leave blank to keep it' : 'Required for hosted APIs'}
                className={input}
              />
            </div>
          </div>
          {note && <p className="text-xs text-amber-600 dark:text-amber-400">{note}</p>}
        </>
      )}
    </fieldset>
  )
}

function AudioForm({ data }: { data: AudioSettings }) {
  const queryClient = useQueryClient()
  const [stt, setStt] = useState<Part>(fromSaved(data.stt))
  const [tts, setTts] = useState<Part>(fromSaved(data.tts))
  const [heard, setHeard] = useState('')
  const [speechError, setSpeechError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () => {
      // An empty key field keeps the saved key.
      const body = (p: Part) => {
        const { api_key, ...rest } = p
        return api_key ? { ...rest, api_key } : rest
      }
      return saveAudioSettings({ stt: body(stt), tts: body(tts) })
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['admin', 'audio'], saved)
      queryClient.invalidateQueries({ queryKey: ['config'] })
      setStt(fromSaved(saved.stt))
      setTts(fromSaved(saved.tts))
    },
  })

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        save.mutate()
      }}
      className="space-y-4"
    >
      <PartFields
        id="stt"
        title="Speech-to-text"
        description="Turns speech into text for the 🎤 button and voice mode. The browser's own recognition works in Chrome, Edge and Safari; a server engine (Whisper) works everywhere and is usually more accurate."
        part={stt}
        hasKey={data.stt.has_key}
        presets={STT_PRESETS}
        onChange={setStt}
      />
      <PartFields
        id="tts"
        title="Text-to-speech"
        description="Reads replies aloud (🔊 and voice mode). Browser voices are free and work offline; a server voice sounds more natural."
        part={tts}
        hasKey={data.tts.has_key}
        presets={TTS_PRESETS}
        withVoice
        onChange={setTts}
      />
      {save.error && <p className="text-sm text-red-500">{errorMessage(save.error)}</p>}
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          Save
        </button>
        {save.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
      </div>

      <div className="space-y-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <h3 className="font-medium">Try the saved settings</h3>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-zinc-500">Speak:</span>
          <DictationButton
            onText={(t) => setHeard((h) => `${h} ${t}`.trim())}
            serverStt={data.stt.engine === 'openai'}
          />
          {heard && <span className="text-sm">“{heard}”</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={button}
            onClick={() => {
              setSpeechError(null)
              speak(
                'Hello! This is how replies will sound.',
                'admin-test',
                data.tts.engine === 'openai',
              ).catch((err) => setSpeechError(errorMessage(err)))
            }}
          >
            🔊 Play a sample
          </button>
          <button type="button" className={button} onClick={stopSpeaking}>
            Stop
          </button>
          {speechError && <span className="text-sm text-red-500">{speechError}</span>}
        </div>
      </div>
    </form>
  )
}

export default function AudioPanel() {
  const settings = useQuery({ queryKey: ['admin', 'audio'], queryFn: getAudioSettings })
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Audio</h2>
        <p className="text-sm text-zinc-500">
          Voice input and read-aloud. Both work without setup using the browser; server engines make
          them better and work in every browser.
        </p>
      </div>
      {settings.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {settings.isError && <p className="text-sm text-red-500">{errorMessage(settings.error)}</p>}
      {settings.data && <AudioForm data={settings.data} />}
    </div>
  )
}
