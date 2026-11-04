import { describe, expect, it } from 'vitest'
import type { Readiness } from './api'
import { accessLost, demoText, judgeMayChange, judgeText } from './access'

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
      'Live calls: 12 of 300 used today (20 per visitor per hour)',
    )
    expect(demoText(ready({ gated: true, paused: true, daily_used: 12, daily_cap: 300, visitor_cap_per_hour: 20 }))).toContain('paused by the operator')
    expect(demoText(ready({ gated: false, paused: true, daily_used: 0, daily_cap: 300, visitor_cap_per_hour: 20 }))).toBe('paused by the operator')
  })
  it('names the demo door for a visitor without a session', () => {
    const gated = { gated: true, paused: false, daily_used: 12, daily_cap: 300, visitor_cap_per_hour: 20 }
    expect(demoText(ready(gated), false)).toBe('Demo: recorded answers only. Sign in to save')
    expect(demoText(ready({ ...gated, live_models: true }), false)).toBe('Demo: recorded answers only. Sign in to save and use the live models')
    expect(demoText(ready({ ...gated, paused: true }), false)).toBe('Demo: recorded answers only. Sign in to save; paused by the operator')
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

describe('judge access', () => {
  const judge = { code_id: 4, recorded: false, calls_per_day: 20, calls_left: 7, max_usd: 5, usd_left: 3.5 }

  it('says what a judge code may still spend, or that it is on the recordings', () => {
    expect(judgeText(null)).toBe('')
    expect(judgeText(judge)).toBe('Judge access: 7 live calls left today, $3.50 left')
    expect(judgeText({ ...judge, calls_left: 1 })).toBe('Judge access: 1 live call left today, $3.50 left')
    expect(judgeText({ ...judge, recorded: true })).toBe('Judge access: recorded answers only')
  })

  it('lets a judge change only the items it added, and the owner every item', () => {
    expect(judgeMayChange(judge, { owner_code: 4 })).toBe(true)
    expect(judgeMayChange(judge, { owner_code: null })).toBe(false)
    expect(judgeMayChange(judge, { owner_code: 9 })).toBe(false)
    expect(judgeMayChange(null, { owner_code: null })).toBe(true)
  })
})
