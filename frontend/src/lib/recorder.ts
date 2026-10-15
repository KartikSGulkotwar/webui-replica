/** Microphone recording for dictation and voice mode. */

export const canRecord = () =>
  typeof navigator !== 'undefined' &&
  !!navigator.mediaDevices?.getUserMedia &&
  typeof MediaRecorder !== 'undefined'

export interface Recording {
  /** Stop and get the audio (null if nothing was said, with `untilSilence`). */
  stop: () => Promise<Blob | null>
  /** Throw the recording away. */
  cancel: () => void
  /** 0–1 loudness, for a level meter. */
  level: () => number
}

interface Options {
  /** Voice mode: stop by itself after this much silence following speech (ms). */
  untilSilence?: number
  /** Called when silence (or the time limit) ended the recording. */
  onAutoStop?: () => void
  /** Hard limit (ms). */
  maxDuration?: number
}

const SPEECH_LEVEL = 0.045 // RMS above this counts as speaking

// Browsers start an AudioContext paused unless a click is still "fresh". Voice
// mode listens again long after the last click, so one context is created and
// resumed on the first (clicked) recording and kept running for later turns.
let shared: AudioContext | null = null
async function audioContext(): Promise<AudioContext> {
  if (!shared || shared.state === 'closed') shared = new AudioContext()
  if (shared.state === 'suspended') await shared.resume().catch(() => {})
  return shared
}

/** Call from a click handler so later recordings can measure loudness. */
export function warmUpAudio(): void {
  void audioContext()
}

export async function startRecording(options: Options = {}): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find((t) =>
    MediaRecorder.isTypeSupported(t),
  )
  const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
  const chunks: Blob[] = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  recorder.start(250)

  const context = await audioContext()
  const analyser = context.createAnalyser()
  analyser.fftSize = 1024
  const source = context.createMediaStreamSource(stream)
  source.connect(analyser)
  const samples = new Float32Array(analyser.fftSize)
  let heard = false
  let quietSince = 0
  let current = 0
  const started = Date.now()

  const timer = window.setInterval(() => {
    analyser.getFloatTimeDomainData(samples)
    current = Math.sqrt(samples.reduce((sum, x) => sum + x * x, 0) / samples.length)
    const now = Date.now()
    if (current > SPEECH_LEVEL) {
      heard = true
      quietSince = 0
    } else if (heard && !quietSince) {
      quietSince = now
    }
    const silent =
      options.untilSilence && heard && quietSince && now - quietSince > options.untilSilence
    const tooLong = options.maxDuration && now - started > options.maxDuration
    if (silent || tooLong) options.onAutoStop?.()
  }, 100)

  const release = () => {
    window.clearInterval(timer)
    source.disconnect()
    stream.getTracks().forEach((t) => t.stop())
  }

  return {
    level: () => Math.min(1, current * 8),
    cancel: () => {
      recorder.onstop = null
      if (recorder.state !== 'inactive') recorder.stop()
      release()
    },
    stop: () =>
      new Promise((resolve) => {
        recorder.onstop = () => {
          release()
          const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
          resolve(options.untilSilence && !heard ? null : blob.size ? blob : null)
        }
        if (recorder.state !== 'inactive') recorder.stop()
        else recorder.onstop?.(new Event('stop'))
      }),
  }
}
