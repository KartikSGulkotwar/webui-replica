import { apiFetch, apiUrl, toApiError } from './client'
import type { AudioSettings } from '../types/api'

/** Speech to text with the server's engine. */
export async function transcribe(audio: Blob): Promise<string> {
  const form = new FormData()
  const ext = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm'
  form.append('file', audio, `speech.${ext}`)
  const resp = await fetch(apiUrl('/api/audio/transcriptions'), { method: 'POST', body: form })
  if (!resp.ok) throw await toApiError(resp)
  return ((await resp.json()) as { text: string }).text
}

/** Text to speech with the server's engine: playable audio. */
export async function synthesize(text: string): Promise<Blob> {
  const resp = await fetch(apiUrl('/api/audio/speech'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!resp.ok) throw await toApiError(resp)
  return resp.blob()
}

export const getAudioSettings = () => apiFetch<AudioSettings>('/api/admin/audio')

export const saveAudioSettings = (body: unknown) =>
  apiFetch<AudioSettings>('/api/admin/audio', { method: 'PUT', body: JSON.stringify(body) })
