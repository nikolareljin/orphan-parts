import { ApiError, type Availability, type Intent, type Item, type Provenance, type Review } from './api'

export const INTENTS: { value: Intent; label: string }[] = [
  { value: 'keep', label: 'Keep' },
  { value: 'build', label: 'Use in a build' },
  { value: 'sell', label: 'Sell' },
  { value: 'give', label: 'Give away' },
]

export const AVAILABILITIES: { value: Availability; label: string }[] = [
  { value: 'available', label: 'Available' },
  { value: 'reserved', label: 'Reserved' },
  { value: 'gone', label: 'Gone' },
]

export const PROVENANCES: { value: Provenance; label: string }[] = [
  { value: 'observed', label: 'observed on a photo' },
  { value: 'owner_reported', label: 'stated by the owner' },
  { value: 'documented', label: 'from documentation' },
  { value: 'tested', label: 'tested' },
  { value: 'estimated', label: 'estimated' },
]

export function provenanceLabel(p: Provenance): string {
  return PROVENANCES.find((x) => x.value === p)?.label ?? p
}

export function availabilityLabel(a: Availability): string {
  return AVAILABILITIES.find((x) => x.value === a)?.label ?? a
}

export function intentLabel(i: Intent): string {
  return INTENTS.find((x) => x.value === i)?.label ?? i
}

export function reviewLabel(r: Review): string {
  return r === 'proposed' ? 'to confirm' : r
}

// Observed values the owner has not looked at yet.
export function proposedCount(item: Item): number {
  return item.assertions.filter((a) => a.review === 'proposed').length
}

// The details form: the free-text fields the owner edits on the item.
export const DETAIL_KEYS = ['condition', 'faults', 'tests_done', 'accessories', 'location', 'notes'] as const
export type Details = Record<(typeof DETAIL_KEYS)[number], string>

export function detailsOf(item: Item): Details {
  return Object.fromEntries(DETAIL_KEYS.map((k) => [k, item[k]])) as Details
}

// The form after the item came back from the server: a field the owner has typed in and not
// saved keeps what they typed; every other field takes the server's value. Without this a
// decision, an accepted value or any other change elsewhere on the dialog would wipe the typing.
export function mergeDetails(typed: Details, before: Item | null, next: Item): Details {
  const fresh = detailsOf(next)
  if (before === null) return fresh
  return Object.fromEntries(DETAIL_KEYS.map((k) => [k, typed[k] !== before[k] ? typed[k] : fresh[k]])) as Details
}

// What a save of the details sends: only the fields the owner changed from the item as it was
// loaded, so a value never typed in (a blank the demo visitor was served, say) is never written.
// Nothing at all from an item served redacted.
export function changedDetails(typed: Details, item: Item): Partial<Details> {
  if (item.redacted) return {}
  return Object.fromEntries(DETAIL_KEYS.filter((k) => typed[k] !== item[k]).map((k) => [k, typed[k]]))
}

// "2026-10-28T21:05:11+00:00" shown as a local date and time, without the seconds.
export function whenText(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// A write the API refused because the item changed since the page last saw it.
export function isConflict(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409
}

// The question the app asks about a part it cannot tie to its device.
export const PARENT_PROMPT = "We couldn't tell which device this part came from. Tell us more about it, or add a photo of that device (the label under its base is best)."

export function asksForParent(item: Item | null | undefined): boolean {
  return item?.needs_parent === true
}

// What a photo of the device gave, in a line.
export function parentPhotoLine(model: string): string {
  return model ? `Read from the photo: ${model}. Confirm it in the fields.` : 'No model could be read from the photo. Tell us about the device instead.'
}

// Once answered, the device a part came from in a line: the model as read or typed, and the
// owner's words (never sent to the demo visitor). Empty when neither is recorded.
export function cameFrom(item: Item): string {
  const said = [item.fields.parent_device_model?.value, item.fields.parent_device?.value].map((v) => v?.trim() ?? '').filter(Boolean)
  return said.length ? `Came from: ${said.join(', ')}` : ''
}

// While the model read off a photo of the device is still to confirm, the line that says so.
export function photoReadLine(item: Item): string {
  const read = item.fields.parent_device_model
  return read && read.source === 'photo' && read.review === 'proposed' ? parentPhotoLine(read.value) : ''
}
