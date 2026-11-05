import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { VoteContext } from '../lib/feedback'
import Feedback from './Feedback'

function render(canVote: boolean): string {
  const buttons = createElement(Feedback, { target: { kind: 'card_picture', id: 3, ref: '4/0/1' }, what: 'drawing' })
  return renderToStaticMarkup(createElement(VoteContext.Provider, { value: canVote }, buttons))
}

describe('Feedback', () => {
  it('is two named toggle buttons for the owner or a judge, neither pressed at first', () => {
    const html = render(true)
    expect(html).toContain('role="group" aria-label="Your vote on this drawing"')
    expect(html).toMatch(/<button type="button" class="link feedback-vote" aria-pressed="false" aria-label="Like this drawing"/)
    expect(html).toMatch(/aria-pressed="false" aria-label="Dislike this drawing"/)
    // the help tip beside them, and no reason asked before a dislike
    expect(html).toContain('aria-label="Help: like and dislike"')
    expect(html).not.toContain('What&#x27;s wrong?')
  })

  it('shows nothing to the demo visitor', () => {
    expect(render(false)).toBe('')
  })
})
