import type { Candidate, CandidateState, SearchStatus, SourceKind } from './api'

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
