import type { Availability, Intent, Item, Provenance, Review } from './api'

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
  { value: 'documented', label: 'documented' },
  { value: 'tested', label: 'tested' },
  { value: 'estimated', label: 'estimated' },
]

export function provenanceLabel(p: Provenance): string {
  return PROVENANCES.find((x) => x.value === p)?.label ?? p
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

// "2026-10-28T21:05:11+00:00" shown as a local date and time, without the seconds.
export function whenText(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
