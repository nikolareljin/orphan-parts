import { describe, expect, it } from 'vitest'
import { buildRequest, defaultFeatureKey, fitScale, formatMm, markLabel, marksNeeded, methodLabel, nextInstruction, toPhoto } from './measure'

const spec = { kind: 'two_point' as const, length_mm: 100, width_mm: 0, height_mm: 0, tolerance_mm: 0.5 }
const image = { width: 640, height: 480 }

describe('marks', () => {
  it('counts and labels the marks per reference kind', () => {
    expect(marksNeeded('two_point')).toBe(4)
    expect(marksNeeded('rectangle')).toBe(6)
    expect([0, 1, 2, 3].map((i) => markLabel(i, 'two_point'))).toEqual(['R1', 'R2', 'F1', 'F2'])
    expect([0, 3, 4, 5].map((i) => markLabel(i, 'rectangle'))).toEqual(['C1', 'C4', 'F1', 'F2'])
  })

  it('tells the user what to mark next', () => {
    expect(nextInstruction(0, 'two_point')).toMatch(/end 1 of the known length/)
    expect(nextInstruction(2, 'two_point')).toMatch(/end 1 of the feature/)
    expect(nextInstruction(4, 'two_point')).toBe('All marks placed')
    expect(nextInstruction(1, 'rectangle')).toMatch(/corner 2/)
  })
})

describe('scaling', () => {
  it('fits wide photos and leaves small ones alone', () => {
    expect(fitScale(1280, 640)).toBe(0.5)
    expect(fitScale(600, 640)).toBe(1)
    expect(toPhoto({ x: 100, y: 50 }, 0.5)).toEqual({ x: 200, y: 100 })
  })
})

describe('buildRequest', () => {
  it('is null until every mark is placed', () => {
    expect(buildRequest([{ x: 1, y: 1 }], spec, 'width', null, image, true)).toBeNull()
  })

  it('splits the marks into the reference and the feature', () => {
    const marks = [
      { x: 100, y: 400 },
      { x: 500, y: 400 },
      { x: 200, y: 200 },
      { x: 340, y: 200 },
    ]
    const req = buildRequest(marks, spec, 'opening_inner_diameter', 'vacuum_attachment', image, true)
    expect(req?.reference).toEqual({ kind: 'two_point', points: marks.slice(0, 2), length_mm: 100, tolerance_mm: 0.5 })
    expect(req?.points).toEqual(marks.slice(2))
    expect(req?.straight_on).toBe(true)
    expect(req?.profile).toBe('vacuum_attachment')
  })

  it('takes four corners for a rectangle', () => {
    const marks = [0, 1, 2, 3, 4, 5].map((i) => ({ x: i, y: i }))
    const req = buildRequest(marks, { ...spec, kind: 'rectangle', width_mm: 85.6, height_mm: 53.98 }, 'width', null, image, false)
    expect(req?.reference.kind).toBe('rectangle')
    expect(req?.reference.kind === 'rectangle' && req.reference.corners.length).toBe(4)
    expect(req?.points).toEqual(marks.slice(4))
  })
})

describe('formatting', () => {
  it('shows the value with its uncertainty, or says there is no number', () => {
    expect(formatMm({ value_mm: 35.04, uncertainty_mm: 1.1875 })).toBe('35.0 ± 1.19 mm')
    expect(formatMm({ value_mm: null, uncertainty_mm: null })).toBe('no number')
    expect(methodLabel('two_point_scale')).toBe('two-point scale')
  })
})

describe('defaultFeatureKey', () => {
  it('starts from the first feature of the profile, else a key of your own', () => {
    expect(defaultFeatureKey([{ key: 'opening_inner_diameter' }, { key: 'insertion_depth' }])).toBe('opening_inner_diameter')
    expect(defaultFeatureKey([])).toBe('__other')
  })
})
