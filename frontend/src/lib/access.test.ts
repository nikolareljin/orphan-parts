import { describe, expect, it } from 'vitest'
import type { Readiness } from './api'
import { accessLost, demoText } from './access'

type Demo = Omit<Readiness['demo'], 'live_models'> & { live_models?: boolean }

const ready = (demo: Demo): Readiness => ({
  status: 'ok',
  model_api: 'fixture',
  data_dir_writable: true,
  spend_usd: 0,
  spend_cap_usd: 25,
  paused: false,
  demo: { live_models: false, ...demo },
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
  it('names the demo door for a visitor without a session', () => {
    const gated = { gated: true, paused: false, daily_used: 12, daily_cap: 300, visitor_cap_per_hour: 20 }
    expect(demoText(ready(gated), false)).toBe('demo: recorded answers; the code unlocks saving')
    expect(demoText(ready({ ...gated, live_models: true }), false)).toBe('demo: recorded answers; the code unlocks saving and the live models')
    expect(demoText(ready({ ...gated, paused: true }), false)).toBe('demo: recorded answers; the code unlocks saving; paused by the operator')
    expect(demoText(ready({ gated: false, paused: false, daily_used: 0, daily_cap: 300, visitor_cap_per_hour: 20 }), false)).toBe('')
  })
})

describe('accessLost', () => {
  it('is a 401, or a write refused as the demo visitor', () => {
    expect(accessLost(401)).toBe(true)
    expect(accessLost(429)).toBe(false)
    expect(accessLost(403)).toBe(false)
    expect(accessLost(403, 'demo: the code unlocks saving, drafts, prices, projects and captures')).toBe(true)
    expect(accessLost(403, 'forbidden')).toBe(false)
  })
})
