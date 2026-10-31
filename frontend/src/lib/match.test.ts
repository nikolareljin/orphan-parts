import { describe, expect, it } from 'vitest'
import type { ProfileRule } from './api'
import { inputLabel, needSide, ruleHint, rulesNote, statusLabel, verdictLabel, verdictTone } from './match'

const rule = (over: Partial<ProfileRule>): ProfileRule => ({
  key: 'output_voltage',
  label: 'Output voltage',
  kind: 'within',
  unit: 'V',
  hard: true,
  identity: false,
  tolerance: null,
  tolerance_pct: null,
  question: '',
  ...over,
})

describe('verdicts', () => {
  it('names every rung of the ladder and its tone', () => {
    expect(verdictLabel('CONFLICT')).toBe('Conflict: does not fit')
    expect(verdictLabel('EXACT_MATCH')).toBe('Exact match')
    expect(verdictTone('CONFLICT')).toBe('conflict')
    expect(verdictTone('COMPATIBLE_LIKELY')).toBe('fits')
    expect(verdictTone('VISUALLY_SIMILAR')).toBe('unsure')
    expect(verdictTone('INSUFFICIENT_INFO')).toBe('unsure')
    expect(statusLabel('unknown')).toBe('unknown')
  })
})

describe('rule hints', () => {
  it('spells out what each kind allows', () => {
    expect(ruleHint(rule({ tolerance_pct: 5 }))).toBe('±5%')
    expect(ruleHint(rule({ tolerance: 0.1, unit: 'mm' }))).toBe('±0.1 mm')
    expect(ruleHint(rule({ tolerance: 0.1, tolerance_pct: 5, unit: 'mm' }))).toBe('±0.1 mm or ±5%')
    expect(ruleHint(rule({ kind: 'equal', identity: true, unit: '' }))).toBe('must match; confirms an exact match')
    expect(ruleHint(rule({ kind: 'at_least', unit: 'A' }))).toBe('at least')
    expect(ruleHint(rule({ kind: 'at_most', tolerance: 2, unit: 'mm' }))).toBe('at most (2 mm over is OK)')
    expect(ruleHint(rule({ kind: 'at_least', tolerance_pct: 5, unit: 'A' }))).toBe('at least (5% below is OK)')
    expect(ruleHint(rule({ kind: 'at_most', tolerance: 2, tolerance_pct: 5, unit: 'mm' }))).toBe('at most (2 mm or 5% over is OK)')
    expect(inputLabel(rule({}))).toBe('Output voltage (V)')
    expect(inputLabel(rule({ unit: '' }))).toBe('Output voltage')
  })
})

describe('needSide', () => {
  it('sends the item, or only the values that were filled in', () => {
    expect(needSide(7, 'power_adapter', { output_voltage: '19.5' })).toEqual({ item_id: 7 })
    expect(needSide(null, 'power_adapter', { output_voltage: ' 19.5 ', polarity: '  ' })).toEqual({
      profile: 'power_adapter',
      values: { output_voltage: '19.5' },
    })
  })
})

describe('rulesNote', () => {
  it('says so only when the needed item carries a different profile', () => {
    expect(rulesNote('power_adapter', 'power_adapter')).toBe('')
    expect(rulesNote('power_adapter', '')).toBe('')
    expect(rulesNote('power_adapter', undefined)).toBe('')
    expect(rulesNote('power_adapter', 'vacuum_attachment')).toContain('vacuum_attachment')
  })
})
