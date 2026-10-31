import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Draft, Step } from './api'
import {
  HARD_LIMIT,
  categoryText,
  copyFields,
  copyText,
  draftText,
  emptyDetails,
  groupLabel,
  handoffSteps,
  modeLabel,
  parsePrice,
  priceInput,
  priceLabel,
  remaining,
  stepsByGroup,
  today,
} from './listing'

const step = (key: string, group: Step['group'], done = false, required = true): Step => ({
  key,
  label: key,
  group,
  required,
  done,
})

describe('labels', () => {
  it('names the modes and the step groups', () => {
    expect(modeLabel('give')).toBe('Give away')
    expect(groupLabel('data')).toBe('Your data')
  })
})

describe('steps', () => {
  it('groups in the order they are done and counts what is left', () => {
    const steps = [step('photo_front', 'photos'), step('clean', 'prepare', true), step('reset', 'data', false, false)]
    expect(stepsByGroup(steps).map(([g, list]) => [g, list.map((s) => s.key)])).toEqual([
      ['prepare', ['clean']],
      ['photos', ['photo_front']],
      ['data', ['reset']],
    ])
    expect(stepsByGroup([step('a', 'photos')]).map(([g]) => g)).toEqual(['photos'])
    expect(remaining(steps)).toBe(1)
  })
})

describe('draftText', () => {
  it('is the title, a blank line and the text', () => {
    const draft = { title: 'Charger', description: 'Works.\n\nPrice: $5' } as Draft
    expect(draftText(draft)).toBe('Charger\n\nWorks.\n\nPrice: $5')
  })
})

const marketDraft = (over: Partial<Draft> = {}): Draft =>
  ({
    mode: 'sell',
    title: 'DELL 1800FP 18" LCD monitor, 1280 x 1024',
    price: '35',
    price_basis: 'your asking price',
    category: 'Electronics > Computers',
    condition: 'Used - Good',
    description: 'Clean screen.\n\nKnown faults: one stuck pixel',
    tags: ['dell monitor', '18 inch', 'vga'],
    photos: [
      { photo: 2, reason: 'front' },
      { photo: 1, reason: 'label' },
    ],
    ...over,
  }) as Draft

describe('copyFields', () => {
  it('gives the six Marketplace fields in the order of the create form', () => {
    const fields = copyFields(marketDraft())
    expect(fields.map((f) => f.key)).toEqual(['title', 'price', 'category', 'condition', 'description', 'tags'])
    expect(fields.find((f) => f.key === 'price')?.text).toBe('35')
    expect(fields.find((f) => f.key === 'category')?.text).toBe('Electronics › Computers')
    expect(fields.find((f) => f.key === 'tags')?.text).toBe('dell monitor, 18 inch, vga')
    expect(fields.find((f) => f.key === 'description')?.text).toContain('one stuck pixel')
  })

  it('copies the category and condition the owner chose instead', () => {
    const fields = copyFields(marketDraft(), { category: 'Electronics > Monitors', condition: 'Used - Fair' })
    expect(fields.find((f) => f.key === 'category')?.text).toBe('Electronics › Monitors')
    expect(fields.find((f) => f.key === 'condition')?.text).toBe('Used - Fair')
  })

  it('names a free price and an unset one', () => {
    expect(priceLabel(marketDraft({ price: '0' }))).toBe('Free (0)')
    expect(priceLabel(marketDraft({ price: '' }))).toBe('not set')
    expect(priceLabel(marketDraft())).toBe('$35')
    expect(categoryText('Free Stuff')).toBe('Free Stuff')
  })
})

describe('handoffSteps', () => {
  it('counts the photos and words pickup for a give-away', () => {
    expect(handoffSteps(marketDraft())[2]).toBe('Add the 2 photo(s) in the order shown.')
    const free = handoffSteps(marketDraft({ mode: 'give', photos: [] }))
    expect(free[2]).toMatch(/^Add photos/)
    expect(free[3]).toBe('Set local pickup and your area.')
    expect(free.at(-1)).toBe('Check the preview, then publish.')
  })

  it('says the hard limit plainly', () => {
    expect(HARD_LIMIT).toMatch(/No public API posts a personal Marketplace listing/)
    expect(HARD_LIMIT).toMatch(/against its terms/)
  })
})

describe('prices and details', () => {
  it('reads a typed price', () => {
    expect(parsePrice('$35')).toBe(35)
    expect(parsePrice(' 1,200.50 ')).toBe(1200.5)
    expect(parsePrice('')).toBeNull()
    expect(parsePrice('thirty')).toBeNull()
    expect(parsePrice('-5')).toBeNull()
    expect(priceInput(null)).toBe('')
    expect(priceInput(35)).toBe('35')
  })

  it('starts empty, pickup first, holding no data', () => {
    const d = emptyDetails()
    expect(d.handover).toBe('pickup')
    expect(d.data).toBe('none')
    expect(d.lowest_price).toBeNull()
  })

  it('writes the local day', () => {
    expect(today(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05')
  })
})

describe('copyText', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the clipboard when there is one', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    await copyText('DELL 1800FP')
    expect(writeText).toHaveBeenCalledWith('DELL 1800FP')
  })
})
