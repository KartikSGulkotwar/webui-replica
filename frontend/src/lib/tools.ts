/** A short, readable form of a tool call's arguments for the step chip. */
export function describeArgs(args: unknown): string {
  if (args && typeof args === 'object' && !Array.isArray(args)) {
    const values = Object.values(args as Record<string, unknown>)
    if (values.length === 0) return ''
    if (values.length === 1 && typeof values[0] === 'string') return values[0]
  }
  return JSON.stringify(args) ?? ''
}
