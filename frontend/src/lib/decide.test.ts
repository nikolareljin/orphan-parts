import { describe, expect, it } from 'vitest'
import type { Worth } from './api'
import {
  CARDS,
  candidatesText,
  cardFor,
  choiceLabel,
  chosenCard,
  difficultyLabel,
  effortLabel,
  fillsLine,
  recommendationLabel,
  reservedLine,
  worthLine,
} from './decide'

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

describe('reservedLine', () => {
  it('names the builds a sale would break, and says nothing when there is none', () => {
    expect(reservedLine([])).toBe('')
    expect(reservedLine(['Homework workstation'])).toBe(
      'Reserved by Homework workstation: selling or giving it away breaks that build.',
    )
    expect(reservedLine(['Homework workstation', 'Home server'])).toBe(
      'Reserved by Homework workstation, Home server: selling or giving it away breaks those builds.',
    )
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

describe('scenario cards', () => {
  it('records each card as a choice and leads to its section', () => {
    expect(CARDS.map((c) => [c.id, c.choice, c.section])).toEqual([
      ['keep_fix', 'keep_fix', 'facts'],
      ['reuse', 'keep_build', 'decide'],
      ['sell', 'sell', 'sell'],
    ])
    expect(choiceLabel('keep_fix')).toBe('Keep and fix')
  })
  it('lights the sell card for giving it away', () => {
    expect(cardFor('give')).toBe('sell')
    expect(cardFor('reuse')).toBe('reuse')
    expect(recommendationLabel('give')).toBe('Give it away')
    expect(difficultyLabel('moderate')).toBe('moderate for you')
  })
  it('marks the card the last decision took', () => {
    expect(chosenCard('sell', 'give')).toBe(true)
    expect(chosenCard('reuse', 'keep_build')).toBe(true)
    expect(chosenCard('keep_fix', 'keep_build')).toBe(false)
    expect(chosenCard('keep_fix', undefined)).toBe(false)
  })
})
