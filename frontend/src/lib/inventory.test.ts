import { describe, expect, it } from 'vitest'
import type { Assertion, Item } from './api'
import { ApiError } from './api'
import {
  PARENT_PROMPT,
  asksForParent,
  availabilityLabel,
  cameFrom,
  changedDetails,
  detailsOf,
  intentLabel,
  isConflict,
  mergeDetails,
  parentPhotoLine,
  photoReadLine,
  proposedCount,
  provenanceLabel,
  reviewLabel,
  whenText,
} from './inventory'

const assertion = (id: number, review: Assertion['review']): Assertion => ({
  id,
  field: `f${id}`,
  value: 'x',
  unit: '',
  provenance: 'observed',
  confidence: 0.9,
  source: 'photo',
  raw: 'x',
  review,
  at: '2026-10-28T21:05:11+00:00',
})

const item = (assertions: Assertion[]): Item => ({
  id: 1,
  name: 'adapter',
  item_type: 'adapter',
  profile: '',
  condition: '',
  intent: 'keep',
  availability: 'available',
  parent_id: null,
  field_count: assertions.length,
  version: 1,
  updated_at: '2026-10-28T21:05:11+00:00',
  public: false,
  faults: '',
  tests_done: '',
  accessories: '',
  location: '',
  notes: '',
  created_at: '2026-10-28T21:05:11+00:00',
  fields: {},
  assertions,
  components: [],
})

describe('labels', () => {
  it('names every provenance and intent in plain words', () => {
    expect(provenanceLabel('owner_reported')).toBe('stated by the owner')
    expect(provenanceLabel('observed')).toBe('observed on a photo')
    expect(intentLabel('build')).toBe('Use in a build')
    expect(availabilityLabel('reserved')).toBe('Reserved')
    expect(reviewLabel('proposed')).toBe('to confirm')
    expect(reviewLabel('accepted')).toBe('accepted')
  })
})

describe('proposedCount', () => {
  it('counts only the observations still to confirm', () => {
    expect(proposedCount(item([assertion(1, 'proposed'), assertion(2, 'accepted'), assertion(3, 'rejected')]))).toBe(1)
    expect(proposedCount(item([]))).toBe(0)
  })
})

describe('whenText', () => {
  it('shows a local date and time without seconds', () => {
    expect(whenText('2026-10-28T21:05:11+00:00')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })

  it('leaves text it cannot parse alone', () => {
    expect(whenText('soon')).toBe('soon')
  })
})

describe('isConflict', () => {
  it('is true only for a 409 from the API', () => {
    expect(isConflict(new ApiError(409, 'item 1 is at version 3, not 2'))).toBe(true)
    expect(isConflict(new ApiError(404, 'no item 9'))).toBe(false)
    expect(isConflict(new Error('offline'))).toBe(false)
  })
})

describe('mergeDetails', () => {
  const before = { ...item([]), notes: 'from the attic', condition: 'scuffed' }
  const next = { ...item([]), version: 2, notes: 'from the attic\n\nRepair plan', condition: 'dented', intent: 'keep' as const }
  it("keeps what the owner typed and has not saved, and takes the server's value elsewhere", () => {
    const typed = { ...detailsOf(before), notes: 'from the attic, check the fan' }
    expect(mergeDetails(typed, before, next)).toEqual({ ...detailsOf(next), notes: 'from the attic, check the fan' })
  })
  it('takes every server value when nothing was typed', () => {
    expect(mergeDetails(detailsOf(before), before, next)).toEqual(detailsOf(next))
  })
  it('takes every server value after the details were saved', () => {
    const typed = { ...detailsOf(before), notes: 'typed ' }
    expect(mergeDetails(typed, null, { ...next, notes: 'typed' })).toEqual({ ...detailsOf(next), notes: 'typed' })
  })
})

describe('changedDetails', () => {
  const loaded = { ...item([]), location: 'garage shelf B', notes: 'paid 40', faults: '' }
  it('sends only the fields that were changed, never an untouched location or notes', () => {
    const body = changedDetails({ ...detailsOf(loaded), faults: 'flickers' }, loaded)
    expect(body).toEqual({ faults: 'flickers' })
    expect(body).not.toHaveProperty('location')
    expect(body).not.toHaveProperty('notes')
  })
  it('sends a location or notes the owner did change, a clearing included', () => {
    expect(changedDetails({ ...detailsOf(loaded), notes: '' }, loaded)).toEqual({ notes: '' })
  })
  it('sends nothing from an item served redacted to the demo visitor', () => {
    const seen = { ...loaded, location: '', notes: '', redacted: true }
    expect(changedDetails({ ...detailsOf(seen), faults: 'flickers', notes: 'typed' }, seen)).toEqual({})
  })
})

describe('the device a part came from', () => {
  it('asks only when the server says the part cannot be tied to its device', () => {
    expect(asksForParent({ ...item([]), needs_parent: true })).toBe(true)
    expect(asksForParent({ ...item([]), needs_parent: false })).toBe(false)
    // an item served before the flag existed, or none at all: nothing is asked
    expect(asksForParent(item([]))).toBe(false)
    expect(asksForParent(null)).toBe(false)
    expect(PARENT_PROMPT).toContain('the label under its base is best')
  })

  it('says where an answered part came from', () => {
    const a = (field: string, value: string): Assertion => ({ ...assertion(9, 'accepted'), field, value })
    expect(cameFrom(item([]))).toBe('')
    expect(cameFrom({ ...item([]), fields: { parent_device_model: a('parent_device_model', 'Hamilton Beach 729') } })).toBe('Came from: Hamilton Beach 729')
    expect(
      cameFrom({ ...item([]), fields: { parent_device_model: a('parent_device_model', 'Hamilton Beach 729'), parent_device: a('parent_device', 'the drink mixer') } }),
    ).toBe('Came from: Hamilton Beach 729, the drink mixer')
  })

  it('says a model read off the photo is still to confirm', () => {
    const read = (review: Assertion['review'], source: Assertion['source']): Item => ({
      ...item([]),
      fields: { parent_device_model: { ...assertion(9, review), field: 'parent_device_model', value: 'Hamilton Beach 729', source } },
    })
    expect(photoReadLine(read('proposed', 'photo'))).toBe('Read from the photo: Hamilton Beach 729. Confirm it in the fields.')
    expect(photoReadLine(read('accepted', 'photo'))).toBe('')
    expect(photoReadLine(read('accepted', 'user_edit'))).toBe('')
    expect(photoReadLine(item([]))).toBe('')
  })

  it('says what a photo of the device gave', () => {
    expect(parentPhotoLine('Hamilton Beach 729')).toBe('Read from the photo: Hamilton Beach 729. Confirm it in the fields.')
    expect(parentPhotoLine('')).toContain('No model could be read')
  })
})
