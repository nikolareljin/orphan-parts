import type { Guidance, PriceKind, Quantity } from './api'

export function kindLabel(kind: PriceKind): string {
  switch (kind) {
    case 'asking':
      return 'asking'
    case 'sold':
      return 'sold'
    case 'reported':
      return 'you reported'
    case 'estimate':
      return 'estimate'
  }
}

// A figure with its currency, or a dash when there is none. Whole amounts stay whole.
export function money(value: number | null, currency: string): string {
  if (value === null || Number.isNaN(value)) return '—'
  const text = Number.isInteger(value) ? String(value) : value.toFixed(2)
  return `${text} ${currency}`
}

// What a quantity spans: nothing, one figure, or a range.
export function rangeText(q: Quantity): string {
  if (q.count === 0 || q.low === null || q.high === null) return 'none'
  if (q.low === q.high) return money(q.low, q.currency)
  return `${money(q.low, q.currency)} to ${money(q.high, q.currency)}`
}

export function searchesText(n: number): string {
  return n === 1 ? '1 search' : `${n} searches`
}

// The line above the figures: weak evidence is said before any number is read.
export function evidenceText(guide: Guidance): string {
  const backed = guide.comparables.length
  const reported = guide.quantities.find((q) => q.kind === 'reported')?.count ?? 0
  const parts = [`${backed} similar listing${backed === 1 ? '' : 's'} with a source`]
  if (reported) parts.push(`${reported} sale${reported === 1 ? '' : 's'} you reported`)
  if (guide.dropped) parts.push(`${guide.dropped} without a source left out`)
  return parts.join(', ')
}
