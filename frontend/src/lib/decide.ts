import type { DecisionChoice, Difficulty, Effort, OpenSearch, Recommendation, TemplateFit, Worth } from './api'
import { money } from './value'

export const CHOICES: { value: DecisionChoice; label: string }[] = [
  { value: 'keep_fix', label: 'Keep and fix' },
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

// What a sale or a gift breaks: the selected projects that count on the item, by title.
export function reservedLine(committedTo: string[]): string {
  if (committedTo.length === 0) return ''
  const one = committedTo.length === 1
  return `Reserved by ${committedTo.join(', ')}: selling or giving it away breaks ${one ? 'that build' : 'those builds'}.`
}

export function candidatesText(search: OpenSearch): string {
  return search.candidates === 1 ? '1 candidate' : `${search.candidates} candidates`
}

// The three scenario cards: the title each is shown under and the choice "Choose this" records.
export type ScenarioCard = 'keep_fix' | 'reuse' | 'sell'

export const CARDS: { id: ScenarioCard; title: string; choice: DecisionChoice }[] = [
  { id: 'keep_fix', title: 'Keep and fix', choice: 'keep_fix' },
  { id: 'reuse', title: 'Reuse it', choice: 'keep_build' },
  { id: 'sell', title: 'Sell or give away', choice: 'sell' },
]

// Where a choice leads once it is kept: the part of the item dialog scrolled to, and what takes
// the focus there. Keep and fix goes to the notes, where the repair steps are added; reuse to
// what the item is good for; a sale or a gift to the listing's heading.
export const LEADS_TO: Partial<Record<DecisionChoice, { scroll: string; focus: string }>> = {
  keep_fix: { scroll: 'form.details', focus: 'form.details textarea[name="notes"]' },
  keep_build: { scroll: '.decide .good-for', focus: '.decide .good-for' },
  sell: { scroll: 'section.listing', focus: 'section.listing h4' },
  give: { scroll: 'section.listing', focus: 'section.listing h4' },
}

// The keep and fix button: on cards written before the item last changed, the repair steps are
// not added to the notes, and the button and its hint say so.
export const STALE_FIX_HINT = 'The item changed since; Ask again to add the repair steps.'

export function keepFixLabel(stale: boolean): string {
  return stale ? 'Choose this (without the repair steps)' : 'Choose this'
}

// The card a recommendation lights up: giving it away is on the sell card.
export function cardFor(recommended: Recommendation): ScenarioCard {
  return recommended === 'give' ? 'sell' : recommended
}

export function recommendationLabel(recommended: Recommendation): string {
  switch (recommended) {
    case 'keep_fix':
      return 'Keep and fix'
    case 'reuse':
      return 'Reuse it'
    case 'sell':
      return 'Sell it'
    case 'give':
      return 'Give it away'
  }
}

export function difficultyLabel(difficulty: Difficulty): string {
  return difficulty === 'easy' ? 'easy for you' : difficulty === 'moderate' ? 'moderate for you' : 'hard for you'
}

// Whether a card is the one the last decision took: the sell card covers selling and giving.
export function chosenCard(card: ScenarioCard, choice: DecisionChoice | undefined): boolean {
  if (choice === undefined) return false
  if (card === 'sell') return choice === 'sell' || choice === 'give'
  return CARDS.find((c) => c.id === card)?.choice === choice
}
