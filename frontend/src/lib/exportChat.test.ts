import { describe, expect, it } from 'vitest'
import { conversationToMarkdown, safeFilename } from './exportChat'
import type { ConversationDetail } from '../types/api'

const conv: ConversationDetail = {
  id: 'c',
  title: 'Prime numbers',
  pinned: false,
  archived: false,
  shared: false,
  created_at: '',
  updated_at: '',
  system_prompt: 'Be brief',
  share_id: null,
  attachments: [],
  messages: [
    { id: 1, role: 'user', content: 'Is 7 prime?', model_id: null, created_at: '' },
    { id: 2, role: 'assistant', content: 'Yes.', model_id: 'groq:llama', created_at: '' },
  ],
}

describe('export', () => {
  it('renders a readable Markdown transcript', () => {
    expect(conversationToMarkdown(conv, (id) => `model ${id}`)).toBe(
      [
        '# Prime numbers',
        '',
        '> **System prompt:** Be brief',
        '',
        '### You',
        '',
        'Is 7 prime?',
        '',
        '### model groq:llama',
        '',
        'Yes.',
        '',
      ].join('\n'),
    )
  })

  it('makes safe filenames', () => {
    expect(safeFilename('What is 2 + 2? / test')).toBe('What-is-2-2-test')
    expect(safeFilename('???')).toBe('chat')
  })
})
