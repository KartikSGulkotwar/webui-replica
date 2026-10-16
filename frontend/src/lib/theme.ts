export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'webui.theme'

export function getStoredTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.style.colorScheme = theme
  // The browser / installed app's title bar follows the theme.
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'dark' ? '#09090b' : '#ffffff')
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // storage unavailable; theme still applies for this visit
  }
}
