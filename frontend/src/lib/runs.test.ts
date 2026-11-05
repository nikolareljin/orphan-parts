import { describe, expect, it } from 'vitest'
import { costText, earlierLabel } from './runs'

describe('runs', () => {
  it('labels a saved answer with its number, date and product name', () => {
    const label = earlierLabel({ version: 2, at: '2026-11-04T10:00:00+00:00', model: 'muse-spark-1.3' })
    expect(label).toMatch(/^Version 2 · \d{4}-\d{2}-\d{2} \d{2}:\d{2} · Muse Spark$/)
    const recorded = earlierLabel({ version: 1, at: '2026-11-04T10:00:00+00:00', model: 'sam-3.1', from_fixture: true })
    expect(recorded).toMatch(/^Version 1 · \d{4}-\d{2}-\d{2} \d{2}:\d{2} · SAM 3.1 · recorded answer$/)
  })

  it('says what an answer cost, or that a recording spent nothing', () => {
    expect(costText({ cost_usd: 0.00412, from_fixture: false })).toBe('$0.0041')
    expect(costText({ cost_usd: 0, from_fixture: true })).toBe('recorded answer, nothing spent')
  })
})
