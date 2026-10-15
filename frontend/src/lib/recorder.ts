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

export async function startRecording(options: Options = {}): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find((t) =>
    MediaRecorder.isTypeSupported(t),
  )
  const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
  const chunks: Blob[] = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  recorder.start(250)

  const context = new AudioContext()
  const analyser = context.createAnalyser()
  analyser.fftSize = 1024
  context.createMediaStreamSource(stream).connect(analyser)
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
    stream.getTracks().forEach((t) => t.stop())
    context.close().catch(() => {})
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
