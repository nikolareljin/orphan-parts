import { describe, expect, it } from 'vitest'
import type { FeedbackTally } from './api'
import { REASON_MAX, oneLine, optimistic, voteAction, voteLabel } from './feedback'

const none: FeedbackTally = { target_kind: 'item_picture', target_id: 1, target_ref: '1', likes: 2, dislikes: 1, mine: null, reason: '' }

describe('feedback', () => {
  it('names each button with what it is about', () => {
    expect(voteLabel('like', 'drawing')).toBe('Like this drawing')
    expect(voteLabel('dislike', 'set of cards')).toBe('Dislike this set of cards')
  })

  it('casts a vote, and takes it back on a second click of the same button', () => {
    expect(voteAction(null, 'like')).toBe('vote')
    expect(voteAction('dislike', 'like')).toBe('vote')
    expect(voteAction('like', 'like')).toBe('withdraw')
  })

  it('moves the counts at once, one vote per person', () => {
    const liked = optimistic(none, 'like')
    expect([liked.likes, liked.dislikes, liked.mine]).toEqual([3, 1, 'like'])
    const switched = optimistic(liked, 'dislike')
    expect([switched.likes, switched.dislikes, switched.mine]).toEqual([2, 2, 'dislike'])
    const back = optimistic({ ...switched, reason: 'a TV' }, 'dislike')
    expect([back.likes, back.dislikes, back.mine, back.reason]).toEqual([2, 1, null, ''])
  })

  it('keeps a reason to one short line', () => {
    expect(oneLine('  drawn as\na TV\t ')).toBe('drawn as a TV')
    expect(oneLine('x'.repeat(REASON_MAX + 20))).toHaveLength(REASON_MAX)
  })
})
