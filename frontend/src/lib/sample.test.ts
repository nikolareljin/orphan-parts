import { describe, expect, it } from 'vitest'
import type { SampleCatalog } from './api'
import {
  SAMPLE_LINE,
  SAMPLE_SIGN_IN,
  allOfItem,
  allPhotoIds,
  inCatalogOrder,
  readingTitle,
  sampleLine,
  toggleItem,
  toggleSample,
} from './sample'

const catalog: SampleCatalog = {
  title: 'a drawer',
  items: [
    { key: 'mon', name: 'Monitor', item_type: 'monitor', photos: [{ id: 'mon-label', file: 'mon-label.jpg', item_key: 'mon', item_name: 'Monitor' }] },
    {
      key: 'gpu',
      name: 'Graphics card',
      item_type: 'graphics card',
      photos: [
        { id: 'gpu-front', file: 'gpu-front.jpg', item_key: 'gpu', item_name: 'Graphics card' },
        { id: 'gpu-back', file: 'gpu-back.jpg', item_key: 'gpu', item_name: 'Graphics card' },
      ],
    },
  ],
  listings: [],
  notes: [],
}

describe('sampleLine', () => {
  it('names a recorded reading only for the demo visitor', () => {
    expect(sampleLine(true, true)).toBe('Recorded answer for this sample.')
    expect(sampleLine(true, false)).toBe('')
    expect(sampleLine(false, true)).toBe('')
    expect(sampleLine(false, false)).toBe('')
  })
  it('offers signing in only when the server reads live', () => {
    expect(sampleLine(true, true, true)).toBe(SAMPLE_LINE + SAMPLE_SIGN_IN)
    expect(sampleLine(true, true, false)).not.toContain('Sign in')
  })
})

describe('picking samples', () => {
  it('puts one photo in and takes it out again', () => {
    expect(toggleSample([], 'gpu-back')).toEqual(['gpu-back'])
    expect(toggleSample(['gpu-back', 'mon-label'], 'gpu-back')).toEqual(['mon-label'])
  })
  it('selects every photo of an item, and clears them when all are in', () => {
    const gpu = catalog.items[1]
    expect(toggleItem(['gpu-back'], gpu)).toEqual(['gpu-back', 'gpu-front'])
    expect(allOfItem(['gpu-back', 'gpu-front'], gpu)).toBe(true)
    expect(toggleItem(['mon-label', 'gpu-back', 'gpu-front'], gpu)).toEqual(['mon-label'])
    expect(allOfItem(['gpu-back'], gpu)).toBe(false)
  })
  it('sends the selection in the catalog order', () => {
    expect(allPhotoIds(catalog)).toEqual(['mon-label', 'gpu-front', 'gpu-back'])
    expect(inCatalogOrder(catalog, ['gpu-back', 'mon-label'])).toEqual(['mon-label', 'gpu-back'])
  })
  it('names a reading by its item and photo', () => {
    expect(readingTitle(catalog, 'gpu', ['gpu-front', 'gpu-back'], true)).toBe('Graphics card, all 2 photos')
    expect(readingTitle(catalog, 'gpu', ['gpu-back'], false)).toBe('Graphics card, photo 2 of 2')
    expect(readingTitle(catalog, 'mon', ['mon-label'], true)).toBe('Monitor')
    expect(readingTitle(catalog, 'gone', ['x'], false)).toBe('x')
  })
})
