import type { DecisionChoice, Effort, OpenSearch, TemplateFit, Worth } from './api'
import { money } from './value'

export const CHOICES: { value: DecisionChoice; label: string }[] = [
  { value: 'keep_build', label: 'Keep and build' },
  { value: 'sell', label: 'Sell' },
  { value: 'give', label: 'Give away' },
  { value: 'not_worth', label: 'Not worth it' },
]

export function choiceLabel(choice: DecisionChoice): string {
  return CHOICES.find((c) => c.value === choice)?.label ?? choice
}

export function effortLabel(effort: Effort): string {
  return `${effort} effort`
}

// The worth row in one line: the typical figure and the strategy to start from, or what is
// missing. Weak evidence is said before the figure is read.
export function worthLine(worth: Worth | null): string {
  if (worth === null) return 'Not asked yet.'
  const figure = worth.typical === null ? 'no figure' : `about ${money(worth.typical, worth.currency)}`
  const parts = [figure]
  if (worth.strategy) parts.push(`${worth.strategy.label.toLowerCase()}: ${money(worth.strategy.price, worth.currency)}`)
  if (worth.weak) parts.push('weak evidence')
  if (worth.stale) parts.push('item changed since')
  return parts.join(' · ')
}

// What the rules say the item fills: each template with the requirement keys, as words.
export function fillsLine(templates: TemplateFit[]): string {
  if (templates.length === 0) return 'No project in the catalog asks for this kind of item.'
  return templates.map((t) => `${t.label} (${t.fills.map((k) => k.replace(/_/g, ' ')).join(', ')})`).join('; ')
}

export function candidatesText(search: OpenSearch): string {
  return search.candidates === 1 ? '1 candidate' : `${search.candidates} candidates`
}
