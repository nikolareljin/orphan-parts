import type { Picture } from './api'
import { usd } from './format'

export const PICTURE_LABEL = 'Illustrative picture drawn by Muse Image; not a photo of the item'
export const PROJECT_PICTURE_LABEL = 'Illustrative picture drawn by Muse Image; not a photo of a real build'
export const DRAW_HINT = 'Draw how the finished project could look. One image call.'
export const DRAW_DEMO_LINE = 'Sign in with the access code to draw.'
export const DRAW_OFF_LINE = 'Pictures are off on this server.'

// The line under a picture: what it was drawn as, the label, and what the call cost.
export function pictureCaption(p: Picture, label: string = PICTURE_LABEL): string {
  const cost = p.from_fixture ? 'recorded answer, nothing spent' : usd(p.cost_usd)
  return `Drawn as: ${p.use}. ${label}. ${cost}`
}

// What a "Draw it" for a finished project shows: the demo visitor a disabled button and the
// line to sign in (nothing is read or drawn for them); the owner nothing until the server says
// whether it draws, then the button, or the line saying pictures are off.
export type DrawState = 'demo' | 'loading' | 'off' | 'ready'

export function drawState(demo: boolean, enabled: boolean | null): DrawState {
  if (demo) return 'demo'
  if (enabled === null) return 'loading'
  return enabled ? 'ready' : 'off'
}
