import { describe, expect, it } from 'vitest'
import { SAMPLE_LINE, SAMPLE_SIGN_IN, sampleLine } from './sample'

describe('sampleLine', () => {
  it('names a recorded reading only for the demo visitor', () => {
    expect(sampleLine(true, true)).toBe('Recorded answer for a sample photo, not a reading of yours.')
    expect(sampleLine(true, false)).toBe('')
    expect(sampleLine(false, true)).toBe('')
    expect(sampleLine(false, false)).toBe('')
  })
  it('offers signing in only when the server reads live', () => {
    expect(sampleLine(true, true, true)).toBe(SAMPLE_LINE + SAMPLE_SIGN_IN)
    expect(sampleLine(true, true, false)).not.toContain('Sign in')
  })
})
