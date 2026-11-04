import type { Pairing, PairingState } from './api'

// How a pairing reads at a glance: a pass in green, a fail in red, an unknown in yellow, the
// same tones a project's status uses.
export function pairingTone(state: PairingState): 'fits' | 'conflict' | 'unsure' {
  if (state === 'pass') return 'fits'
  if (state === 'fail') return 'conflict'
  return 'unsure'
}

export function pairingLabel(state: PairingState): string {
  if (state === 'pass') return 'fits'
  if (state === 'fail') return 'does not fit'
  return 'unknown: check'
}

// Which with which: a missing part names only the item it is for.
export function pairingWho(p: Pick<Pairing, 'part' | 'part_id' | 'host'>): string {
  return p.part_id === null ? p.host : `${p.part} with ${p.host}`
}

// The counts in one line, for a card or a project: "1 does not fit, 2 fit".
export function pairingSummary(pairings: Pick<Pairing, 'state'>[]): string {
  const count = (s: PairingState) => pairings.filter((p) => p.state === s).length
  const parts: string[] = []
  const fail = count('fail')
  const unknown = count('unknown')
  const pass = count('pass')
  if (fail) parts.push(`${fail} does not fit`)
  if (unknown) parts.push(`${unknown} to check`)
  if (pass) parts.push(`${pass} ${pass === 1 ? 'fits' : 'fit'}`)
  return parts.join(', ')
}

// A Marketplace search for the part a failure needs.
export function marketplaceFor(words: string): string {
  return `https://www.facebook.com/marketplace/search/?query=${encodeURIComponent(words.trim())}`
}
