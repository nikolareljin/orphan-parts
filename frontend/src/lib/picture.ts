import type { Picture } from './api'
import { usd } from './format'

export const PICTURE_LABEL = 'Illustrative picture drawn by Muse Image; not a photo of the item'

// The line under a picture: what it was drawn as, the label, and what the call cost.
export function pictureCaption(p: Picture): string {
  const cost = p.from_fixture ? 'recorded answer, nothing spent' : usd(p.cost_usd)
  return `Drawn as: ${p.use}. ${PICTURE_LABEL}. ${cost}`
}
