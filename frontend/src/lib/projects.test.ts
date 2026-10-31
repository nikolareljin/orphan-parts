import { describe, expect, it } from 'vitest'
import {
  numberProblem,
  budgetText,
  canStart,
  conflictText,
  conflictsOf,
  effortLabel,
  missing,
  money,
  numberOrNull,
  packLabel,
  progressText,
  stepDone,
  todayIso,
  statusLabel,
  statusTone,
} from './projects'

describe('labels', () => {
  it('names every status, tone and effort', () => {
    expect(statusLabel('selected')).toBe('selected: items committed')
    expect(statusLabel('building')).toBe('being built')
    expect(statusTone('done')).toBe('fits')
    expect(statusTone('abandoned')).toBe('muted')
    expect(statusTone('proposed')).toBe('unsure')
    expect(effortLabel('low')).toBe('an hour or so')
  })
})

describe('numbers', () => {
  it('treats a blank or negative number as not set', () => {
    expect(numberOrNull('')).toBeNull()
    expect(numberOrNull(' 40 ')).toBe(40)
    expect(numberOrNull('-1')).toBeNull()
    expect(numberOrNull('abc')).toBeNull()
  })
  it('writes money without needless decimals', () => {
    expect(money(12, 'USD')).toBe('12 USD')
    expect(money(12.5, 'EUR')).toBe('12.50 EUR')
  })
})

describe('budgetText', () => {
  it('says what is left, or by how much the set is over, or that no budget is set', () => {
    expect(budgetText({ budget: 50, currency: 'USD', committed_spend: 12, remaining: 38, selected: 1 })).toBe(
      '1 selected, expected spend 12 USD of 50 USD; 38 USD left',
    )
    expect(budgetText({ budget: 10, currency: 'USD', committed_spend: 22, remaining: -12, selected: 2 })).toBe(
      '2 selected, expected spend 22 USD of 10 USD: over by 12 USD',
    )
    expect(budgetText({ budget: null, currency: 'USD', committed_spend: 0, remaining: null, selected: 0 })).toBe(
      '0 selected, expected spend 0 USD; no budget set',
    )
  })
})

describe('requirements', () => {
  const req = (key: string, state: 'pass' | 'unknown', blocking: boolean) => ({
    key,
    label: key,
    kind: 'item' as const,
    blocking,
    state,
    item_id: null,
    search_id: null,
    profile: '',
  })
  it('lists what is missing with blocking ones first and says whether a build can start', () => {
    const project = { requirements: [req('mouse', 'unknown', false), req('cable', 'unknown', true), req('laptop', 'pass', true)] }
    expect(missing(project).map((r) => r.key)).toEqual(['cable', 'mouse'])
    expect(canStart(project)).toBe(false)
    expect(canStart({ requirements: [req('laptop', 'pass', true), req('mouse', 'unknown', false)] })).toBe(true)
  })
})

describe('conflicts', () => {
  it('reads the conflicts off a 409 body and says them in a line', () => {
    const body = { detail: 'x', conflicts: [{ item_id: 1, item_name: 'Old laptop', project_id: 3, project_title: 'Homework desk' }, { nope: 1 }] }
    const list = conflictsOf(body)
    expect(list).toHaveLength(1)
    expect(conflictText(list)).toBe('Old laptop is committed to "Homework desk"')
    expect(conflictsOf(undefined)).toEqual([])
    expect(conflictsOf({ conflicts: 'no' })).toEqual([])
  })
})

describe('numberProblem', () => {
  it('says what is wrong instead of saving nothing', () => {
    expect(numberProblem('', 'The budget')).toBeNull()
    expect(numberProblem(' 50 ', 'The budget')).toBeNull()
    expect(numberProblem('abc', 'The budget')).toBe('The budget must be a number')
    expect(numberProblem('-5', 'The radius')).toBe('The radius cannot be below 0')
    expect(numberProblem('1e999', 'The budget')).toBe('The budget must be a number')
  })
})

describe('packs and progress', () => {
  it('labels a pack by version and day and says when it is stale', () => {
    expect(packLabel({ version: 2, created_at: '2026-10-29T18:00:00+00:00', stale: false })).toBe('version 2, 2026-10-29')
    expect(packLabel({ version: 1, created_at: '2026-10-28T09:00:00+00:00', stale: true })).toBe('version 1, 2026-10-28, stale: an input changed since')
  })
  it('counts the steps done, treating missing flags as not done', () => {
    const project = { steps: ['a', 'b', 'c'], progress: [true] }
    expect(stepDone(project, 0)).toBe(true)
    expect(stepDone(project, 2)).toBe(false)
    expect(progressText(project)).toBe('1 of 3 steps done')
  })
  it('writes today as a date the API takes', () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
