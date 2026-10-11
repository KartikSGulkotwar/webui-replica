import type { ConversationDetail } from '../types/api'

export function downloadFile(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function safeFilename(title: string) {
  return (
    title
      .replace(/[^\w\s-]/g, '')
      .trim()
      .replace(/\s+/g, '-')
      .slice(0, 60) || 'chat'
  )
}

export function conversationToMarkdown(
  conv: ConversationDetail,
  modelLabel: (id: string) => string,
): string {
  const lines = [`# ${conv.title}`, '']
  if (conv.system_prompt) lines.push(`> **System prompt:** ${conv.system_prompt}`, '')
  for (const m of conv.messages) {
    const who = m.role === 'user' ? 'You' : m.model_id ? modelLabel(m.model_id) : 'Assistant'
    lines.push(`### ${who}`, '', m.content, '')
  }
  return lines.join('\n')
}
