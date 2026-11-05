import type { Picture } from './api'
import { usd } from './format'

export const PICTURE_LABEL = 'Illustrative picture drawn by Muse Image; not a photo of the item'
export const PROJECT_PICTURE_LABEL = 'Illustrative picture drawn by Muse Image; not a photo of a real build'
export const DRAW_HINT = 'Draw how the finished project could look. One image call.'
export const DRAW_AGAIN_HINT = 'Drawing again adds a picture; the ones drawn stay. One image call.'
export const DRAW_DEMO_LINE = 'Sign in with the access code to draw.'
export const DRAW_OFF_LINE = 'Pictures are off on this server.'

// The line under a picture: what it was drawn as, the label, and what the call cost.
export function pictureCaption(p: Picture, label: string = PICTURE_LABEL): string {
  const cost = p.from_fixture ? 'recorded answer, nothing spent' : usd(p.cost_usd)
  return `Drawn as: ${p.use}. ${label}. ${cost}${checkLine(p)}${steerLine(p)}`
}

// What people's votes changed in it: the reasons of earlier dislikes it was drawn avoiding,
// and a liked drawing's correction it kept.
export function steerLine(p: Picture): string {
  const avoided = (p.avoided ?? []).filter(Boolean)
  const parts = []
  if (avoided.length) parts.push(`Drawn again avoiding: ${avoided.join('; ')}`)
  if (p.kept) parts.push(`Keeping: ${p.kept}`)
  return parts.length ? `. ${parts.join('. ')}` : ''
}

// The review gate's line: the verdict, and that it was drawn again when it was.
export function checkLine(p: Picture): string {
  const c = p.check
  if (!c || !['matches', 'partly', 'wrong'].includes(c.verdict)) return ''
  const again = c.redraw_of ? `, drawn again for picture ${c.redraw_of}` : ''
  return `. Checked against its facts by Muse Spark: ${c.verdict}${again} (${usd(c.cost_usd)})`
}

// The pictures to show: one the review gate judged worse than its redraw stays kept, unshown.
export function shownPictures<T extends Picture>(pictures: T[]): T[] {
  return pictures.filter((p) => !p.hidden)
}

// What a "Draw it" for a finished project shows: the demo visitor no button, the line to
// sign in (nothing is read or drawn for them); the owner nothing until the server says
// whether it draws, then the button, or the line saying pictures are off.
export type DrawState = 'demo' | 'loading' | 'off' | 'ready'

export function drawState(demo: boolean, enabled: boolean | null): DrawState {
  if (demo) return 'demo'
  if (enabled === null) return 'loading'
  return enabled ? 'ready' : 'off'
}
