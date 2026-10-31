import { describe, expect, it } from 'vitest'
import type { Picture } from './api'
import { DRAW_DEMO_LINE, DRAW_HINT, PICTURE_LABEL, PROJECT_PICTURE_LABEL, drawState, pictureCaption } from './picture'

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

describe('Draw it for a finished project', () => {
  it('labels the picture as drawn, not as a real build', () => {
    const line = pictureCaption({ ...drawn, use: 'Kitchen recipe display' }, PROJECT_PICTURE_LABEL)
    expect(line).toContain('Drawn as: Kitchen recipe display')
    expect(line).toContain('not a photo of a real build')
    expect(line).not.toContain('not a photo of the item')
  })
  it('keeps the demo visitor to the sign-in line, whatever the server says', () => {
    expect(drawState(true, null)).toBe('demo')
    expect(drawState(true, true)).toBe('demo')
    expect(DRAW_DEMO_LINE).toContain('access code')
  })
  it('shows the button only once the server says it draws', () => {
    expect(drawState(false, null)).toBe('loading')
    expect(drawState(false, false)).toBe('off')
    expect(drawState(false, true)).toBe('ready')
  })
  it('says the click is one image call', () => {
    expect(DRAW_HINT).toBe('Draw how the finished project could look. One image call.')
  })
})
