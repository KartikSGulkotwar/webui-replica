/**
 * Models usually write LaTeX as \( … \) (inline) and \[ … \] (display), but
 * remark-math only understands dollar delimiters. Convert those, leaving code
 * alone. Single "$" is deliberately *not* math (see Markdown.tsx), so prices
 * like "$5 and $10" stay text; inline math becomes "$$…$$" on one line.
 */
export function normalizeMath(markdown: string): string {
  // Split out fenced code blocks and inline code so their contents are untouched.
  const parts = markdown.split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part // code
      return part
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr: string) => `\n$$\n${expr.trim()}\n$$\n`)
        .replace(/\\\(([\s\S]+?)\\\)/g, (_, expr: string) => `$$${expr.trim()}$$`)
    })
    .join('')
}

/** Cheap check for any math delimiter, to decide whether to load KaTeX. */
export function hasMath(markdown: string): boolean {
  return /\$\$|\\\(|\\\[/.test(markdown)
}
