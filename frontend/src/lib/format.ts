import type { Evidence } from './api'

// Display order of the first category's fields; anything else follows alphabetically.
export const FIELD_ORDER = [
  'brand',
  'model_number',
  'part_number',
  'input_voltage',
  'output_voltage',
  'output_current',
  'output_power',
  'connector',
  'polarity',
  'certifications',
  'condition_notes',
]

export function orderedFields(fields: Record<string, Evidence>): [string, Evidence][] {
  const rank = (name: string) => {
    const i = FIELD_ORDER.indexOf(name)
    return i === -1 ? FIELD_ORDER.length : i
  }
  return Object.entries(fields).sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
}

export function fieldLabel(name: string): string {
  const words = name.replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function withUnit(e: Evidence): string {
  return e.unit ? `${e.value} ${e.unit}` : e.value
}

export function percent(confidence: number): string {
  return `${Math.round(Math.min(Math.max(confidence, 0), 1) * 100)}%`
}

export function usd(amount: number): string {
  return amount === 0 ? '$0.00' : `$${amount.toFixed(4)}`
}
