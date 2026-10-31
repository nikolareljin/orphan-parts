import { describe, expect, it } from 'vitest'
import { askingPrice, candidateRequest, highlightSegments, maxPriceLine, seenText, sourceLabel, splitListings, stateLabel, stateTone, statusLabel, verdictLabel, verdictTone } from './find'

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
    expect(seenText({ observed_on: '2026-10-20', expires_on: '2026-11-03', expired: false })).toBe('seen 2026-10-20, valid until 2026-11-03')
    expect(seenText({ observed_on: '2026-01-05', expires_on: '2026-01-19', expired: true })).toBe('seen 2026-01-05, out of date since 2026-01-19')
  })
})

describe('candidateRequest', () => {
  it('keeps the text only for a text candidate and only the values that were filled in', () => {
    const base = { text: 'a listing', values: { output_voltage: ' 19.5 ', polarity: '  ' }, observedOn: '', askingPrice: '15', currency: 'USD', location: 'Astoria', url: '' }
    expect(candidateRequest({ ...base, source: 'text' })).toMatchObject({ source_kind: 'text', text: 'a listing', values: { output_voltage: '19.5' } })
    expect(candidateRequest({ ...base, source: 'manual' })).toMatchObject({ source_kind: 'manual', text: '', values: { output_voltage: '19.5' } })
  })
})

describe('splitListings', () => {
  it('splits on lines of dashes, keeping blank lines inside a listing', () => {
    const pasted = 'DVI-D cable 6 ft\n\nDual link, $5\n---\nVGA cable $3\n -----  \n\n'
    expect(splitListings(pasted)).toEqual(['DVI-D cable 6 ft\n\nDual link, $5', 'VGA cable $3'])
  })

  it('splits on blank lines when there are no dashes, and drops empty pieces', () => {
    expect(splitListings('one\nline two\n\n\n  \ntwo\r\n\r\nthree')).toEqual(['one\nline two', 'two', 'three'])
    expect(splitListings('   \n\n')).toEqual([])
    expect(splitListings('just one')).toEqual(['just one'])
  })
})

describe('highlightSegments', () => {
  it('cuts the text into plain and highlighted runs', () => {
    const text = 'Orbital 19.5V 3.34A, for parts'
    expect(
      highlightSegments(text, [
        { kind: 'excluded', start: 21, end: 30 },
        { kind: 'match', start: 8, end: 19 },
      ]),
    ).toEqual([
      { text: 'Orbital ', kind: null },
      { text: '19.5V 3.34A', kind: 'match' },
      { text: ', ', kind: null },
      { text: 'for parts', kind: 'excluded' },
    ])
    expect(highlightSegments('plain', [])).toEqual([{ text: 'plain', kind: null }])
  })

  it('counts code points as the backend does, and lets the earlier of two overlaps keep it', () => {
    // the emoji is one code point and two UTF-16 units
    expect(highlightSegments('🔌 DVI-D', [{ kind: 'match', start: 2, end: 7 }])).toEqual([
      { text: '🔌 ', kind: null },
      { text: 'DVI-D', kind: 'match' },
    ])
    expect(
      highlightSegments('abcdef', [
        { kind: 'match', start: 0, end: 4 },
        { kind: 'excluded', start: 2, end: 6 },
        { kind: 'match', start: 9, end: 12 },
      ]),
    ).toEqual([
      { text: 'abcd', kind: 'match' },
      { text: 'ef', kind: 'excluded' },
    ])
  })
})

describe('verdicts', () => {
  it('names each verdict and its tone', () => {
    expect(verdictLabel('no')).toBe('does not fit')
    expect(verdictLabel('fits')).toBe('fits')
    expect(verdictTone('fits')).toBe('fits')
    expect(verdictTone('maybe')).toBe('unsure')
    expect(verdictTone('no')).toBe('conflict')
  })
})

describe('prices', () => {
  it('writes asking prices with separators, cents only when there are some, and free for 0', () => {
    expect(askingPrice(1200)).toBe('$1,200')
    expect(askingPrice(45.5)).toBe('$45.50')
    expect(askingPrice(1_200_000)).toBe('$1,200,000')
    expect(askingPrice(0)).toBe('free')
  })

  it('says no max price when there is none or it is 0', () => {
    expect(maxPriceLine(20)).toBe('Each link includes your max price, $20.')
    expect(maxPriceLine(0)).toBe('No max price set.')
    expect(maxPriceLine(null)).toBe('No max price set.')
  })
})
