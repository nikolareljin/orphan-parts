import { describe, expect, it } from 'vitest'
import { candidateRequest, seenText, sourceLabel, stateLabel, stateTone, statusLabel } from './find'

describe('labels', () => {
  it('names every state, tone, status and source', () => {
    expect(stateLabel('documented')).toBe('documented candidate')
    expect(stateLabel('needs_evidence')).toBe('needs evidence')
    expect(stateTone('documented')).toBe('fits')
    expect(stateTone('rejected')).toBe('conflict')
    expect(stateTone('withdrawn')).toBe('muted')
    expect(stateTone('conflicting')).toBe('unsure')
    expect(statusLabel('found')).toBe('found')
    expect(sourceLabel('manual')).toBe('Values I know')
  })
})

describe('seenText', () => {
  it('says how long an observation is trusted, or since when it is too old', () => {
    expect(seenText({ observed_on: '2026-10-20', expires_on: '2026-11-03', expired: false })).toBe('seen 2026-10-20, trusted until 2026-11-03')
    expect(seenText({ observed_on: '2026-01-05', expires_on: '2026-01-19', expired: true })).toBe('seen 2026-01-05, too old since 2026-01-19')
  })
})

describe('candidateRequest', () => {
  it('keeps the text only for a text candidate and only the values that were filled in', () => {
    const base = { text: 'a listing', values: { output_voltage: ' 19.5 ', polarity: '  ' }, observedOn: '', askingPrice: '15', currency: 'USD', location: 'Astoria', url: '' }
    expect(candidateRequest({ ...base, source: 'text' })).toMatchObject({ source_kind: 'text', text: 'a listing', values: { output_voltage: '19.5' } })
    expect(candidateRequest({ ...base, source: 'manual' })).toMatchObject({ source_kind: 'manual', text: '', values: { output_voltage: '19.5' } })
  })
})
