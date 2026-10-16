import typography from '@tailwindcss/typography'
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Light mode backgrounds: a warm off-white instead of pure white.
        // Raised surfaces (message box, menus, cards, fields) stay white.
        paper: { DEFAULT: '#faf9f6', dim: '#f3f2ee' },
      },
    },
  },
  plugins: [typography],
} satisfies Config
