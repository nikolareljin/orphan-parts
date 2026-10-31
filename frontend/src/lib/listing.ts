import type { DataState, Draft, DraftMode, Handover, Included, SellDetails, Step, StepGroup } from './api'

export const MODES: { value: DraftMode; label: string }[] = [
  { value: 'sell', label: 'Sell' },
  { value: 'give', label: 'Give away' },
]

export function modeLabel(mode: DraftMode): string {
  return MODES.find((m) => m.value === mode)?.label ?? mode
}

export function groupLabel(group: StepGroup): string {
  switch (group) {
    case 'prepare':
      return 'Before handing it over'
    case 'photos':
      return 'Photos'
    case 'data':
      return 'Wipe your data'
  }
}

// Steps in their groups, in the order the groups are meant to be done.
export function stepsByGroup(steps: Step[]): [StepGroup, Step[]][] {
  const order: StepGroup[] = ['prepare', 'photos', 'data']
  return order.map((g): [StepGroup, Step[]] => [g, steps.filter((s) => s.group === g)]).filter(([, list]) => list.length > 0)
}

// What goes to the clipboard: the title, a blank line, the text as it would be posted.
export function draftText(draft: Draft): string {
  return `${draft.title}\n\n${draft.description}`
}

export function remaining(steps: Step[]): number {
  return steps.filter((s) => s.required && !s.done).length
}

// --- Facebook Marketplace (US) -----------------------------------------------------------

export const HARD_LIMIT =
  'No public API posts a personal Marketplace listing, and automating the site is against its terms. ' +
  'Everything is prepared here and Marketplace’s create page opens; you paste the fields and post.'

export const INCLUDED: { value: Included; label: string }[] = [
  { value: 'stand', label: 'Stand' },
  { value: 'cables', label: 'Cables' },
  { value: 'power_cord', label: 'Power cord' },
  { value: 'box', label: 'Original box' },
  { value: 'manual', label: 'Manual' },
  { value: 'remote', label: 'Remote' },
]

export const HANDOVERS: { value: Handover; label: string }[] = [
  { value: 'pickup', label: 'Local pickup' },
  { value: 'shipping', label: 'Shipping' },
  { value: 'either', label: 'Either' },
]

export const DATA_STATES: { value: DataState; label: string }[] = [
  { value: 'none', label: 'None stored' },
  { value: 'wiped', label: 'Signed out and wiped' },
  { value: 'not_wiped', label: 'Not wiped yet' },
]

export function emptyDetails(): SellDetails {
  return {
    condition_words: '',
    included: [],
    included_other: '',
    faults: '',
    untested: '',
    data: 'none',
    reason: '',
    handover: 'pickup',
    area: '',
    asking_price: null,
    lowest_price: null,
    availability: '',
  }
}

// A price as typed: "$35", "35.00" or "" (none); anything else is null too.
export function parsePrice(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, '')
  if (cleaned === '') return null
  const value = Number(cleaned)
  return Number.isFinite(value) && value >= 0 ? value : null
}

// The details to save with the prices as typed. A give-away hides the price fields, so a
// saved asking price, lowest price and handover are kept as they were (the draft prices a
// give-away at 0 and hands it over at pickup whatever they say); a sale checks what was typed.
export function detailsToSave(
  details: SellDetails,
  mode: DraftMode,
  asking: string,
  lowest: string,
): { details: SellDetails } | { error: string } {
  if (mode === 'give') return { details }
  const a = parsePrice(asking)
  const l = parsePrice(lowest)
  if ((asking.trim() && (a === null || a === 0)) || (lowest.trim() && l === null)) {
    return { error: 'a price is a number of dollars above 0, like 35' }
  }
  return { details: { ...details, asking_price: a, lowest_price: l } }
}

// Whether two sets of details say the same, field by field; what is included in any order.
export function sameDetails(a: SellDetails, b: SellDetails): boolean {
  return (Object.keys(emptyDetails()) as (keyof SellDetails)[]).every((k) =>
    k === 'included' ? [...a.included].sort().join() === [...b.included].sort().join() : a[k] === b[k],
  )
}

// The listed button: the first listing, then a new price on the same listing.
export function listedLabel(state: string, mode: DraftMode, amount: number | null): string {
  if (state !== 'listed') return 'Mark as listed'
  return mode === 'sell' && amount !== null && amount > 0 ? `Listed again at ${dollars(amount)}` : 'Listed again'
}

// A US price as people read it: $35, $35.50.
export function dollars(value: number): string {
  return Number.isInteger(value) ? `$${value.toLocaleString('en-US')}` : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function priceInput(value: number | null): string {
  return value === null ? '' : String(value)
}

export type CopyKey = 'title' | 'price' | 'category' | 'condition' | 'description' | 'tags'

export interface CopyField {
  key: CopyKey
  label: string
  text: string
}

// The fields as they go into Marketplace's create form, one Copy button each. The price is the
// number Marketplace takes; 0 lists it as free. The tags are copied as one comma-separated line.
// The category and the condition are the owner's choice when changed from the draft's.
export function copyFields(draft: Draft, chosen: { category?: string; condition?: string } = {}): CopyField[] {
  return [
    { key: 'title', label: 'Title', text: draft.title },
    { key: 'price', label: 'Price', text: draft.price },
    { key: 'category', label: 'Category', text: categoryText(chosen.category ?? draft.category) },
    { key: 'condition', label: 'Condition', text: chosen.condition ?? draft.condition },
    { key: 'description', label: 'Description', text: draft.description },
    { key: 'tags', label: 'Tags', text: draft.tags.join(', ') },
  ]
}

// "Electronics > Computers" as the picker steps through it: "Electronics › Computers".
export function categoryText(path: string): string {
  return path.split(' > ').join(' › ')
}

export function priceLabel(draft: Draft): string {
  if (draft.price === '0') return 'Free (0)'
  return draft.price ? `$${draft.price}` : 'not set'
}

export function handoffSteps(draft: Draft): string[] {
  return [
    'Open Marketplace and choose Item for sale.',
    'Paste the title, price, category, condition, description and tags.',
    draft.photos.length > 0 ? `Add the ${draft.photos.length} photo(s) in the order shown.` : 'Add photos: the front, the label, every fault.',
    draft.mode === 'give' ? 'Set local pickup and your area.' : 'Set local pickup or shipping, and your area.',
    'Check the preview, then publish.',
  ]
}

// Copy to the clipboard; where the API is missing (an http page), a hidden text area does it.
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const done = document.execCommand('copy')
  area.remove()
  if (!done) throw new Error('copy is not available here; select the text and copy it')
}

// The owner's calendar day, YYYY-MM-DD.
export function today(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
