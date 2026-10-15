/** A reply as it should be read aloud: markdown, code, links and citations removed. */
export function toSpeakable(markdown: string): string {
  return (
    markdown
      // Code blocks aren't worth reading out.
      .replace(/```[\s\S]*?(```|$)/g, ' (code omitted) ')
      .replace(/`([^`]*)`/g, '$1')
      // Math stays as written, without delimiters.
      .replace(/\$\$([\s\S]*?)\$\$/g, '$1')
      // Images and links: keep the words, drop the address.
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/https?:\/\/\S+/g, '')
      // Citation markers: [1], [2][3], 【1†L1-L4】
      .replace(/【[^】]*】/g, '')
      .replace(/\[\d+\]/g, '')
      // Headings, emphasis, quotes, list bullets, table rules.
      .replace(/^#{1,6}\s+/gm, '')
      .replace(/(\*\*|__|\*|_|~~)(.+?)\1/g, '$2')
      .replace(/^>\s?/gm, '')
      .replace(/^\s*([-*+]|\d+\.)\s+/gm, '')
      .replace(/^\s*\|?[-:| ]+\|?\s*$/gm, '')
      .replace(/\|/g, ', ')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{2,}/g, '\n')
      .trim()
  )
}

/** Sentences of at most ~`max` characters (some browsers cut long utterances short). */
export function splitForSpeech(text: string, max = 220): string[] {
  const sentences = text.match(/[^.!?\n]+[.!?]*\s*|\n/g) ?? [text]
  const chunks: string[] = []
  let current = ''
  for (const s of sentences) {
    if ((current + s).length > max && current) {
      chunks.push(current.trim())
      current = ''
    }
    current += s
  }
  if (current.trim()) chunks.push(current.trim())
  return chunks
}
