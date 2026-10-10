import { describe, expect, it } from 'vitest'
import { dateGroup, groupByDate } from './dates'

const now = new Date(2026, 9, 10, 15, 0) // Oct 10, 3pm local

describe('dateGroup', () => {
  it.each([
    [new Date(2026, 9, 10, 0, 5), 'Today'],
    [new Date(2026, 9, 9, 23, 59), 'Yesterday'],
    [new Date(2026, 9, 4), 'Previous 7 days'],
    [new Date(2026, 8, 20), 'Previous 30 days'],
    [new Date(2026, 0, 1), 'Older'],
  ])('%s → %s', (date, group) => {
    expect(dateGroup(date.toISOString(), now)).toBe(group)
  })

  it('treats future timestamps (clock skew) as today', () => {
    expect(dateGroup(new Date(2026, 9, 11).toISOString(), now)).toBe('Today')
  })
})

describe('groupByDate', () => {
  it('keeps order within groups and orders groups newest first', () => {
    const items = [
      { id: 'a', at: new Date(2026, 9, 10, 14).toISOString() },
      { id: 'b', at: new Date(2026, 9, 10, 9).toISOString() },
      { id: 'c', at: new Date(2026, 9, 9).toISOString() },
      { id: 'd', at: new Date(2025, 0, 1).toISOString() },
    ]
    const groups = groupByDate(items, (i) => i.at, now)
    expect(groups.map((g) => [g.group, g.items.map((i) => i.id)])).toEqual([
      ['Today', ['a', 'b']],
      ['Yesterday', ['c']],
      ['Older', ['d']],
    ])
  })
})
