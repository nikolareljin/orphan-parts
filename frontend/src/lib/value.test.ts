import { describe, expect, it } from 'vitest'
import type { Guidance, Quantity } from './api'
import { evidenceText, kindLabel, money, rangeText, searchesText } from './value'

const quantity = (over: Partial<Quantity>): Quantity => ({
  kind: 'asking',
  label: 'asking prices seen',
  count: 3,
  low: 12.5,
  high: 22,
  typical: 18,
  currency: 'USD',
  basis: 'seen',
  ...over,
})

describe('money and ranges', () => {
  it('keeps whole amounts whole and says none for nothing', () => {
    expect(money(18, 'USD')).toBe('18 USD')
    expect(money(12.5, 'USD')).toBe('12.50 USD')
    expect(money(null, 'USD')).toBe('—')
    expect(rangeText(quantity({}))).toBe('12.50 USD to 22 USD')
    expect(rangeText(quantity({ count: 1, low: 15, high: 15 }))).toBe('15 USD')
    expect(rangeText(quantity({ count: 0, low: null, high: null, typical: null }))).toBe('none')
  })
})

describe('labels', () => {
  it('names each kind and counts searches', () => {
    expect(kindLabel('reported')).toBe('you reported')
    expect(kindLabel('estimate')).toBe('estimate')
    expect(searchesText(1)).toBe('1 search')
    expect(searchesText(2)).toBe('2 searches')
  })
})

describe('evidenceText', () => {
  it('counts what backs the figures and what was left out', () => {
    const guide = {
      comparables: [{}, {}, {}, {}],
      dropped: 1,
      quantities: [quantity({ kind: 'reported', count: 1 })],
    } as unknown as Guidance
    expect(evidenceText(guide)).toBe('4 similar listings with a source, 1 sale you reported, 1 without a source left out')
    const bare = { comparables: [{}], dropped: 0, quantities: [] } as unknown as Guidance
    expect(evidenceText(bare)).toBe('1 similar listing with a source')
  })
})
