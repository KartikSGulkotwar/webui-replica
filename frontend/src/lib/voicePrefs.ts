/** Read-aloud preferences for the browser's own voices, kept in this browser. */
export interface VoicePrefs {
  /** SpeechSynthesisVoice.voiceURI; empty = the browser's default. */
  voice: string
  rate: number
}

const KEY = 'webui.voice'
const DEFAULTS: VoicePrefs = { voice: '', rate: 1 }

export function getVoicePrefs(): VoicePrefs {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return DEFAULTS
  }
}

export function setVoicePrefs(prefs: VoicePrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs))
  } catch {
    // storage unavailable; the choice lasts for this visit only
  }
}
