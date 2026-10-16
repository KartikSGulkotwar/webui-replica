/** Installing the app (PWA). Chrome and Edge offer a prompt we can trigger;
 * Safari installs from its Share / File menu, so we explain where. */

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

let deferred: InstallPromptEvent | null = null
const listeners = new Set<() => void>()
const notify = () => listeners.forEach((l) => l())

if (typeof window !== 'undefined') {
  // Fired early, possibly before React mounts: keep it for later.
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferred = e as InstallPromptEvent
    notify()
  })
  window.addEventListener('appinstalled', () => {
    deferred = null
    notify()
  })
}

export const subscribeInstall = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}
export const canPromptInstall = () => deferred !== null

export async function promptInstall(): Promise<boolean> {
  if (!deferred) return false
  await deferred.prompt()
  const { outcome } = await deferred.userChoice
  deferred = null
  notify()
  return outcome === 'accepted'
}

/** Already running as an installed app. */
export const isInstalled = () =>
  window.matchMedia?.('(display-mode: standalone)').matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true

export type Platform = 'ios' | 'mac-safari' | 'chromium' | 'other'

export function detectPlatform(): Platform {
  const ua = navigator.userAgent
  const iOS =
    /iPhone|iPad|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1)
  if (iOS) return 'ios'
  if (/Chrome|Chromium|Edg\//.test(ua)) return 'chromium'
  if (ua.includes('Macintosh') && ua.includes('Safari')) return 'mac-safari'
  return 'other'
}
