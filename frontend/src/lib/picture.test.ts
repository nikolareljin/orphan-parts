import { describe, expect, it } from 'vitest'
import type { Picture } from './api'
import { PICTURE_LABEL, pictureCaption } from './picture'

const drawn: Picture = { n: 1, use: 'a bedside lamp', model: 'muse-image-1.0', cost_usd: 0.01, from_fixture: false, created_at: '2026-10-31T10:00:00+00:00' }

describe('the line under a picture', () => {
  it('says what it was drawn as, that it is drawn, and the cost', () => {
    const line = pictureCaption(drawn)
    expect(line).toContain('Drawn as: a bedside lamp')
    expect(line).toContain(PICTURE_LABEL)
    expect(line).toContain('$0.0100')
  })
  it('says nothing was spent on a recorded answer', () => {
    expect(pictureCaption({ ...drawn, cost_usd: 0, from_fixture: true })).toContain('nothing spent')
  })
})
