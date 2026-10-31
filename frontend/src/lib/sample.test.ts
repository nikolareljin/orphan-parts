import { describe, expect, it } from 'vitest'
import { SAMPLE_LINE, sampleLine } from './sample'

describe('sampleLine', () => {
  it('names a recorded result only for the demo visitor', () => {
    expect(sampleLine(true, true)).toBe(SAMPLE_LINE)
    expect(SAMPLE_LINE).toContain('Recorded answer for this sample photo')
    expect(sampleLine(true, false)).toBe('')
    expect(sampleLine(false, true)).toBe('')
    expect(sampleLine(false, false)).toBe('')
  })
})
