import { describe, expect, it } from 'vitest'
import type { Worth } from './api'
import { candidatesText, choiceLabel, effortLabel, fillsLine, worthLine } from './decide'

const worth = (over: Partial<Worth>): Worth => ({
  id: 1,
  version: 1,
  currency: 'USD',
  typical: 18,
  strategy: { name: 'typical', label: 'Typical', price: 18, note: '' },
  weak: false,
  stale: false,
  at: '2026-10-31T10:00:00+00:00',
  ...over,
})

describe('worthLine', () => {
  it('reads the figure, the strategy, and what weakens them', () => {
    expect(worthLine(null)).toBe('Not asked yet.')
    expect(worthLine(worth({}))).toBe('about 18 USD · typical: 18 USD')
    expect(worthLine(worth({ typical: null, strategy: null, weak: true }))).toBe('no figure · weak evidence')
    expect(worthLine(worth({ stale: true }))).toContain('item changed since')
  })
})

describe('fillsLine', () => {
  it('names each template with the requirements it fills', () => {
    expect(fillsLine([])).toBe('No project in the catalog asks for this kind of item.')
    expect(
      fillsLine([
        { id: 'homework_workstation', label: 'Homework workstation', fills: ['laptop'] },
        { id: 'home_server', label: 'Home server', fills: ['computer', 'video_cable'] },
      ]),
    ).toBe('Homework workstation (laptop); Home server (computer, video cable)')
  })
})

describe('labels', () => {
  it('names the choices, the effort and the candidates', () => {
    expect(choiceLabel('keep_build')).toBe('Keep and build')
    expect(choiceLabel('not_worth')).toBe('Not worth it')
    expect(effortLabel('low')).toBe('low effort')
    expect(candidatesText({ id: 1, title: 't', status: 'open', candidates: 1, handoff_url: '' })).toBe('1 candidate')
    expect(candidatesText({ id: 1, title: 't', status: 'open', candidates: 0, handoff_url: '' })).toBe('0 candidates')
  })
})
