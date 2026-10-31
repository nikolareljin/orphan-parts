import type { SampleCatalog, SampleItem } from './api'

// The line above a recorded reading shown to the demo visitor (a gated server, no session).
// The visitor reads the demo set's own photos, so the answer is the one recorded for that very
// sample. Signing in reads live only where the server has a key, so the way to a reading of
// one's own photos is offered only then.
export const SAMPLE_LINE = 'Recorded answer for this sample.'
export const SAMPLE_SIGN_IN = ' Sign in with the access code to read your own.'
// in place of an upload the demo cannot take and has no sample for
export const SIGN_IN_LINE = 'Sign in with the access code to use this.'

export function sampleLine(fromFixture: boolean, demo: boolean, liveModels = false): string {
  if (!fromFixture || !demo) return ''
  return liveModels ? SAMPLE_LINE + SAMPLE_SIGN_IN : SAMPLE_LINE
}

// One photo in or out of the selection.
export function toggleSample(selected: string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]
}

export function allOfItem(selected: string[], item: SampleItem): boolean {
  return item.photos.length > 0 && item.photos.every((p) => selected.includes(p.id))
}

// Every photo of the item in, or, when all are in already, every photo of it out.
export function toggleItem(selected: string[], item: SampleItem): string[] {
  const ids = item.photos.map((p) => p.id)
  if (allOfItem(selected, item)) return selected.filter((s) => !ids.includes(s))
  return [...selected, ...ids.filter((id) => !selected.includes(id))]
}

// Every sample photo of the catalog, in its order.
export function allPhotoIds(catalog: SampleCatalog): string[] {
  return catalog.items.flatMap((i) => i.photos.map((p) => p.id))
}

// The selection in the catalog's order, which is the order the readings come back in.
export function inCatalogOrder(catalog: SampleCatalog, selected: string[]): string[] {
  return allPhotoIds(catalog).filter((id) => selected.includes(id))
}

// What a reading is called: the item, and which photo when it is not the whole item.
export function readingTitle(catalog: SampleCatalog, itemKey: string, sampleIds: string[], wholeItem: boolean): string {
  const item = catalog.items.find((i) => i.key === itemKey)
  if (!item) return sampleIds.join(', ')
  if (wholeItem) return item.photos.length > 1 ? `${item.name}, all ${item.photos.length} photos` : item.name
  const n = item.photos.findIndex((p) => p.id === sampleIds[0])
  return `${item.name}, photo ${n + 1} of ${item.photos.length}`
}
