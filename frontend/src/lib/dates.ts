export type DateGroup = 'Today' | 'Yesterday' | 'Previous 7 days' | 'Previous 30 days' | 'Older'

const ORDER: DateGroup[] = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older']

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

export function dateGroup(iso: string, now: Date = new Date()): DateGroup {
  const days = Math.round((startOfDay(now) - startOfDay(new Date(iso))) / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days <= 7) return 'Previous 7 days'
  if (days <= 30) return 'Previous 30 days'
  return 'Older'
}

/** Group items (already sorted newest first) under date headings, preserving order. */
export function groupByDate<T>(
  items: T[],
  getDate: (item: T) => string,
  now: Date = new Date(),
): { group: DateGroup; items: T[] }[] {
  const buckets = new Map<DateGroup, T[]>()
  for (const item of items) {
    const g = dateGroup(getDate(item), now)
    if (!buckets.has(g)) buckets.set(g, [])
    buckets.get(g)!.push(item)
  }
  return ORDER.filter((g) => buckets.has(g)).map((group) => ({ group, items: buckets.get(group)! }))
}
