import { useState, useSyncExternalStore } from 'react'
import { canPromptInstall, detectPlatform, promptInstall, subscribeInstall } from '../lib/install'
import Dialog from './Dialog'

const STEPS: Record<string, { title: string; steps: string[] }> = {
  ios: {
    title: 'On iPhone or iPad (Safari)',
    steps: [
      'Tap the Share button (the square with an arrow) at the bottom of Safari.',
      'Scroll down and tap “Add to Home Screen”.',
      'Tap “Add”. WebUI opens from your home screen like an app.',
    ],
  },
  'mac-safari': {
    title: 'On a Mac (Safari)',
    steps: [
      'In the menu bar choose File → Add to Dock.',
      'Click “Add”. WebUI opens in its own window from the Dock and Launchpad.',
    ],
  },
  chromium: {
    title: 'In Chrome or Edge',
    steps: [
      'Click the install icon at the right end of the address bar,',
      'or open the browser menu and choose “Install WebUI Replica”.',
    ],
  },
  other: {
    title: 'In other browsers',
    steps: [
      'Open this site in Safari (iPhone, Mac), or Chrome or Edge (Mac, Windows, Android), then install it from there.',
    ],
  },
}

/** How to install the app here, with a one-click install where the browser allows it. */
export default function InstallDialog({ onClose }: { onClose: () => void }) {
  const canPrompt = useSyncExternalStore(subscribeInstall, canPromptInstall)
  const [installed, setInstalled] = useState(false)
  const platform = detectPlatform()
  const help = STEPS[platform]
  return (
    <Dialog title="Install WebUI Replica" onClose={onClose}>
      <div className="space-y-4 p-4 text-sm">
        <p className="text-zinc-600 dark:text-zinc-400">
          Get an app icon and a full-screen window, without the browser’s address bar. It updates by
          itself and stays signed in.
        </p>
        {canPrompt && !installed && (
          <button
            type="button"
            onClick={async () => setInstalled(await promptInstall())}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-500"
          >
            Install now
          </button>
        )}
        {installed && <p className="text-emerald-600">Installed — look for WebUI in your apps.</p>}
        <div>
          <p className="mb-1 font-medium">{help.title}</p>
          <ol className="list-decimal space-y-1 pl-5 text-zinc-600 dark:text-zinc-400">
            {help.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      </div>
    </Dialog>
  )
}
