import { createContext } from 'react'
import type { FeedbackTally, FeedbackVote } from './api'

// Whether this page may vote: the owner and a judge's code, never the demo visitor (the
// server refuses the visitor anyway). Unknown access reads as the visitor: no buttons.
export const VoteContext = createContext(false)

export const REASON_MAX = 200

// What the buttons name, so a screen reader hears "Like this drawing" and not "Like".
export type FeedbackWhat =
  | 'drawing'
  | 'set of cards'
  | 'ideas'
  | 'draft'
  | 'price guidance'
  | 'search plan'
  | 'web find'
  | 'candidate'
  | 'proposal'
  | 'build pack'

export function voteLabel(vote: FeedbackVote, what: FeedbackWhat): string {
  return `${vote === 'like' ? 'Like' : 'Dislike'} this ${what}`
}

// A click on a button already pressed takes the vote back; otherwise it is cast (in place of
// the other one).
export function voteAction(mine: FeedbackVote | null, clicked: FeedbackVote): 'withdraw' | 'vote' {
  return mine === clicked ? 'withdraw' : 'vote'
}

// The reason as the server keeps it: one line, at most REASON_MAX characters.
export function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, REASON_MAX)
}

// The tally as the person sees it at once, before the server answers.
export function optimistic(t: FeedbackTally, clicked: FeedbackVote): FeedbackTally {
  const next = { ...t }
  if (t.mine === 'like') next.likes = Math.max(0, next.likes - 1)
  if (t.mine === 'dislike') next.dislikes = Math.max(0, next.dislikes - 1)
  if (voteAction(t.mine, clicked) === 'withdraw') return { ...next, mine: null, reason: '' }
  if (clicked === 'like') next.likes += 1
  else next.dislikes += 1
  return { ...next, mine: clicked, reason: clicked === 'like' ? '' : t.reason }
}
