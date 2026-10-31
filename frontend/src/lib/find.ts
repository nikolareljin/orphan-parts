import type { Candidate, CandidateState, Highlight, ListingVerdict, SearchStatus, SourceKind } from './api'

export const SOURCES: { value: SourceKind; label: string }[] = [
  { value: 'text', label: 'Listing text' },
  { value: 'screenshot', label: 'Screenshot' },
  { value: 'manual', label: 'Values I know' },
]

// Where a candidate stands, in plain words. A documented candidate is not an installed part.
export function stateLabel(state: CandidateState): string {
  switch (state) {
    case 'unassessed':
      return 'not assessed'
    case 'needs_evidence':
      return 'needs evidence'
    case 'conflicting':
      return 'conflicting evidence'
    case 'documented':
      return 'documented candidate'
    case 'rejected':
      return 'rejected'
    case 'withdrawn':
      return 'withdrawn'
  }
}

export function stateTone(state: CandidateState): 'fits' | 'conflict' | 'unsure' | 'muted' {
  if (state === 'documented') return 'fits'
  if (state === 'rejected') return 'conflict'
  if (state === 'withdrawn') return 'muted'
  return 'unsure'
}

export function statusLabel(status: SearchStatus): string {
  switch (status) {
    case 'open':
      return 'open'
    case 'found':
      return 'found'
    case 'closed':
      return 'closed'
  }
}

export function sourceLabel(kind: SourceKind): string {
  return SOURCES.find((s) => s.value === kind)?.label ?? kind
}

// When the observation was made and how long it is trusted.
export function seenText(c: Pick<Candidate, 'observed_on' | 'expires_on' | 'expired'>): string {
  return c.expired ? `seen ${c.observed_on}, too old since ${c.expires_on}` : `seen ${c.observed_on}, trusted until ${c.expires_on}`
}

// The candidate request as the API takes it: only the fields the source kind uses, trimmed.
export function candidateRequest(input: {
  source: SourceKind
  text: string
  values: Record<string, string>
  observedOn: string
  askingPrice: string
  currency: string
  location: string
  url: string
}): Record<string, unknown> {
  const values: Record<string, string> = {}
  for (const [key, value] of Object.entries(input.values)) {
    if (value.trim()) values[key] = value.trim()
  }
  return {
    source_kind: input.source,
    text: input.source === 'text' ? input.text : '',
    values,
    observed_on: input.observedOn,
    asking_price: input.askingPrice,
    currency: input.currency,
    location: input.location,
    url: input.url,
  }
}

// Several listings pasted at once, one each: split on lines of dashes when there are any (so a
// listing may keep blank lines inside), otherwise on blank lines. Empty pieces are dropped.
export function splitListings(text: string): string[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  const dashes = /^\s*[-–—]{3,}\s*$/
  const byDashes = lines.some((l) => dashes.test(l))
  const pieces: string[] = []
  let current: string[] = []
  for (const line of lines) {
    const breaks = byDashes ? dashes.test(line) : line.trim() === ''
    if (breaks) {
      pieces.push(current.join('\n'))
      current = []
    } else {
      current.push(line)
    }
  }
  pieces.push(current.join('\n'))
  return pieces.map((p) => p.trim()).filter((p) => p.length > 0)
}

export interface Segment {
  text: string
  kind: 'match' | 'excluded' | null
}

// The listing text cut into plain and highlighted runs. Offsets are in code points, as the
// backend counts them, so a listing with an emoji in it highlights the right span; where two
// highlights overlap, the earlier one keeps the overlap.
export function highlightSegments(text: string, highlights: Pick<Highlight, 'kind' | 'start' | 'end'>[]): Segment[] {
  const chars = Array.from(text)
  const sorted = [...highlights].filter((h) => h.end > h.start).sort((a, b) => a.start - b.start || a.end - b.end)
  const out: Segment[] = []
  let at = 0
  for (const h of sorted) {
    const start = Math.max(h.start, at)
    const end = Math.min(h.end, chars.length)
    if (end <= start) continue
    if (start > at) out.push({ text: chars.slice(at, start).join(''), kind: null })
    out.push({ text: chars.slice(start, end).join(''), kind: h.kind })
    at = end
  }
  if (at < chars.length) out.push({ text: chars.slice(at).join(''), kind: null })
  return out
}

export function verdictLabel(verdict: ListingVerdict): string {
  switch (verdict) {
    case 'fits':
      return 'fits'
    case 'maybe':
      return 'maybe'
    case 'no':
      return 'does not fit'
  }
}

export function verdictTone(verdict: ListingVerdict): 'fits' | 'unsure' | 'conflict' {
  return verdict === 'fits' ? 'fits' : verdict === 'no' ? 'conflict' : 'unsure'
}
