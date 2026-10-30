import { describe, expect, it } from 'vitest'
import type { Assertion, Item } from './api'
import { ApiError } from './api'
import { availabilityLabel, intentLabel, isConflict, proposedCount, provenanceLabel, reviewLabel, whenText } from './inventory'

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
