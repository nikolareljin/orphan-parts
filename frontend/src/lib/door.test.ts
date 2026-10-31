import { describe, expect, it } from 'vitest'
import { SIGNED_IN, SIGNED_OUT, doorOf, isDemo, retryDelayMs, uploadsAllowed } from './door'

describe('doorOf', () => {
  it('offers the way in while access is unknown', () => {
    expect(doorOf(null)).toBe('sign-in')
  })

  it('offers sign out with a session and sign in without one on a gated server', () => {
    expect(doorOf({ gated: true, granted: true })).toBe('sign-out')
    expect(doorOf({ gated: true, granted: false })).toBe('sign-in')
  })

  it('shows the open note on a server without a code, whatever granted says', () => {
    // the backend answers {gated: false, granted: true} there
    expect(doorOf({ gated: false, granted: true })).toBe('open')
    expect(doorOf({ gated: false, granted: false })).toBe('open')
  })

  it('flips at once after sign in, sign out and a lost session', () => {
    expect(doorOf(SIGNED_IN)).toBe('sign-out')
    expect(doorOf(SIGNED_OUT)).toBe('sign-in')
  })
})

describe('isDemo', () => {
  it('is the demo only when known to be gated without a session', () => {
    expect(isDemo(null)).toBe(false)
    expect(isDemo(SIGNED_OUT)).toBe(true)
    expect(isDemo(SIGNED_IN)).toBe(false)
    expect(isDemo({ gated: false, granted: true })).toBe(false)
  })
})

describe('uploadsAllowed', () => {
  it('keeps every upload input away until the server says signed in or open', () => {
    // no answer yet, or every try failed: the visitor's samples and lines, never a file input
    expect(uploadsAllowed(null)).toBe(false)
    expect(uploadsAllowed(SIGNED_OUT)).toBe(false)
    expect(uploadsAllowed(SIGNED_IN)).toBe(true)
    expect(uploadsAllowed({ gated: false, granted: true })).toBe(true)
    expect(uploadsAllowed({ gated: false, granted: false })).toBe(true)
  })
})

describe('retryDelayMs', () => {
  it('backs off from one second and stays at thirty', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 20].map(retryDelayMs)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000])
  })

  it('treats nonsense as the first failure', () => {
    expect(retryDelayMs(0)).toBe(1000)
    expect(retryDelayMs(-3)).toBe(1000)
  })
})
