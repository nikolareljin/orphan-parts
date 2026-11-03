import { usd } from './format'
import { whenText } from './inventory'

// The steps that ask a model, and what each says before it was ever asked: what it does, what
// it gives back, and what one asking costs. Opening a section never asks: a saved answer is
// shown as it was kept, and asking again is the owner's button, which adds a new answer beside
// the earlier ones.
export type Step = 'scenarios' | 'uses' | 'price' | 'draft' | 'picture' | 'plan' | 'web' | 'propose'

export const STEPS: Record<Step, { what: string; gives: string; cost: string }> = {
  scenarios: {
    what: 'Muse Spark reads what is known about the item and your profile (skills, tools, effort, budget) and the kinds of item you own besides.',
    gives: 'Three cards: keep and fix (the likely problem, the steps at your level, parts, cost and time), two or three ways to reuse it with what you have, and what selling or giving it away takes, with the one it recommends and why.',
    cost: 'One Muse Spark call, about $0.01.',
  },
  uses: {
    what: 'The rules name the project templates the item fills; Muse Spark proposes what else it could be from its accepted values, condition and faults.',
    gives: 'Up to three ideas, each with what else it needs and the effort.',
    cost: 'One Muse Spark call, under $0.01.',
  },
  price: {
    what: 'Muse Spark searches the web for listings and sales of the same model and condition; only comparables a search result backs are kept.',
    gives: 'Asking, sold, reported and estimated prices kept apart with their pages and dates, three ways to price it, and a warning when the evidence is weak.',
    cost: 'One Muse Spark call with up to four web searches, about $0.04.',
  },
  draft: {
    what: 'Muse Spark writes a Facebook Marketplace (US) listing from what is confirmed about the item, your listing details and its photos; the rules check the category and condition, set the price and add the disclosures.',
    gives: 'Title, price, category, condition, description and tags to paste, the photo order, and the checklist before posting (a give-away: the free listing and how to hand it over).',
    cost: 'One Muse Spark call, about $0.01. Nothing is posted.',
  },
  picture: {
    what: 'Muse Image draws what the item could become, or the item itself.',
    gives: 'One illustrative picture, kept beside the photos and never counted as one.',
    cost: 'One image call, $0.01.',
  },
  plan: {
    what: 'Muse Spark writes how a seller might have listed the part.',
    gives: 'Three to six search phrasings, each a Marketplace search link to open, a match pattern a fitting listing matches and the words that rule one out.',
    cost: 'One Muse Spark call, under $0.01.',
  },
  web: {
    what: 'Muse Spark searches the web for pages that offer the part, the device it came from first.',
    gives: 'Each page found becomes a listing with its link, ranked by the plan.',
    cost: 'One Muse Spark call with up to four web searches, about $0.03.',
  },
  propose: {
    what: 'Muse Spark plans builds from what you have and your profile; the rules check every requirement.',
    gives: 'Projects with what each needs, what you have for it and what is missing.',
    cost: 'One Muse Spark call, about $0.02.',
  },
}

// One saved answer in the list of earlier ones: its number, when, and the model that wrote it.
export function earlierLabel(r: { version: number; at: string; model: string; from_fixture?: boolean }): string {
  const recorded = r.from_fixture ? ' · recorded answer' : ''
  return `Version ${r.version} · ${whenText(r.at)} · ${r.model}${recorded}`
}

// The cost line of a saved answer: what it cost when it was asked.
export function costText(r: { cost_usd: number; from_fixture: boolean }): string {
  return r.from_fixture ? 'recorded answer, nothing spent' : usd(r.cost_usd)
}
