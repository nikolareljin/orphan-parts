import { describe, expect, it } from 'vitest'
import type { Worth } from './api'
import {
  CARDS,
  LEADS_TO,
  STALE_FIX_HINT,
  STEPS_ADDED,
  candidatesText,
  cardFor,
  choiceLabel,
  chosenCard,
  difficultyLabel,
  effortLabel,
  fillsLine,
  keepFix,
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
  it('records each card as a choice', () => {
    expect(CARDS.map((c) => [c.id, c.choice])).toEqual([
      ['keep_fix', 'keep_fix'],
      ['reuse', 'keep_build'],
      ['sell', 'sell'],
    ])
    expect(choiceLabel('keep_fix')).toBe('Keep and fix')
  })
  it('leads each choice to its part of the dialog and focuses there', () => {
    expect(LEADS_TO.keep_fix).toEqual({ scroll: 'form.details', focus: 'form.details textarea[name="notes"]' })
    expect(LEADS_TO.keep_build).toEqual({ scroll: '.decide .good-for', focus: '.decide .good-for' })
    expect(LEADS_TO.sell).toEqual({ scroll: 'section.listing', focus: 'section.listing h4' })
    expect(LEADS_TO.give).toEqual(LEADS_TO.sell)
    expect(LEADS_TO.not_worth).toBeUndefined()
  })
  it('says when keep and fix comes without the repair steps, and when they are in', () => {
    expect(keepFix({ stale: false, steps_in_notes: false })).toEqual({ label: 'Choose this', hint: '' })
    expect(keepFix({ stale: true, steps_in_notes: false })).toEqual({
      label: 'Choose this (without the repair steps)',
      hint: STALE_FIX_HINT,
    })
    expect(STALE_FIX_HINT).toMatch(/Ask again/)
    // the steps are in the notes: no stale hint, edited since or not
    expect(keepFix({ stale: false, steps_in_notes: true })).toEqual({ label: 'Choose this', hint: STEPS_ADDED })
    expect(keepFix({ stale: true, steps_in_notes: true })).toEqual({ label: 'Choose this', hint: STEPS_ADDED })
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
