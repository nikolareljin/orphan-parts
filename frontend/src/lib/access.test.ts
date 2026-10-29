import { describe, expect, it } from 'vitest'
import type { Readiness } from './api'
import { accessLost, demoText } from './access'

const ready = (demo: Readiness['demo']): Readiness => ({
  status: 'ok',
  model_api: 'fixture',
  data_dir_writable: true,
  spend_usd: 0,
  spend_cap_usd: 25,
  paused: false,
  demo,
})

describe('demoText', () => {
  it('says nothing without a gate and the counts with one', () => {
    expect(demoText(ready({ gated: false, paused: false, daily_used: 0, daily_cap: 300, visitor_cap_per_hour: 20 }))).toBe('')
    expect(demoText(ready({ gated: true, paused: false, daily_used: 12, daily_cap: 300, visitor_cap_per_hour: 20 }))).toBe(
      'demo: 12 of 300 calls today, 20 per visitor and hour',
    )
    expect(demoText(ready({ gated: true, paused: true, daily_used: 12, daily_cap: 300, visitor_cap_per_hour: 20 }))).toContain('paused by the operator')
    expect(demoText(ready({ gated: false, paused: true, daily_used: 0, daily_cap: 300, visitor_cap_per_hour: 20 }))).toBe('paused by the operator')
  })
})

describe('accessLost', () => {
  it('is only a 401', () => {
    expect(accessLost(401)).toBe(true)
    expect(accessLost(429)).toBe(false)
    expect(accessLost(403)).toBe(false)
  })
})
