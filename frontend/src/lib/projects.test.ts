import { describe, expect, it } from 'vitest'
import {
  budgetText,
  canStart,
  conflictText,
  conflictsOf,
  effortLabel,
  missing,
  money,
  numberOrNull,
  skillsFromText,
  skillsToText,
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

describe('skills and numbers', () => {
  it('reads a comma list and writes it back', () => {
    expect(skillsFromText(' soldering, basic computer setup ,, ')).toEqual(['soldering', 'basic computer setup'])
    expect(skillsToText(['a', 'b'])).toBe('a, b')
  })
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
