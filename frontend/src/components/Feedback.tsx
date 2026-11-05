import { useContext, useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { api, type FeedbackTally, type FeedbackTarget, type FeedbackVote } from '../lib/api'
import { HELP } from '../lib/help'
import { REASON_MAX, VoteContext, oneLine, optimistic, voteAction, voteLabel, type FeedbackWhat } from '../lib/feedback'
import HelpTip from './HelpTip'

const EMPTY = { likes: 0, dislikes: 0, mine: null, reason: '' }

// A like or a dislike of something the app generated, under it: two small buttons with their
// counts, pressed for the person's own vote; a click on the pressed one takes it back. A
// dislike asks, in one optional line, what is wrong. The votes go to the review tools, never
// to a model as such: a dislike's reason steers the next drawing of the same thing, and the
// review tools read them. The owner and a judge's code vote; the demo visitor sees nothing.
// While a vote is on its way the button shows it pressed at once (aria-busy, both buttons
// disabled, so it is never sent twice); the server's answer then stands, and when the request
// fails the tally is read again from the server (or put back as it was) with the error shown.
export default function Feedback({ target, what }: { target: FeedbackTarget; what: FeedbackWhat }) {
  const canVote = useContext(VoteContext)
  if (!canVote) return null
  return <Votes target={target} what={what} />
}

function Votes({ target, what }: { target: FeedbackTarget; what: FeedbackWhat }) {
  const { kind, id, ref = '' } = target
  const [tally, setTally] = useState<FeedbackTally>({ target_kind: kind, target_id: id, target_ref: ref, ...EMPTY })
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const inputId = useId()
  // a request is on its way (a ref: two clicks in one frame both read it before a render)
  const sending = useRef(false)
  // bumped by every vote: the first read's answer arriving after a vote is stale and dropped
  const votes = useRef(0)

  useEffect(() => {
    let cancelled = false
    const at = votes.current
    api.feedback
      .get({ kind, id, ref })
      .then((found) => {
        if (!cancelled && votes.current === at) setTally(found)
      })
      .catch(() => {
        // a target the server does not know (or will not count for this session): no buttons
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [kind, id, ref])

  // after a failed request: what the server has, or what was shown before when it cannot say
  async function reconcile(before: FeedbackTally) {
    try {
      setTally(await api.feedback.get({ kind, id, ref }))
    } catch {
      setTally(before)
    }
  }

  async function cast(clicked: FeedbackVote) {
    if (sending.current) return
    sending.current = true
    votes.current += 1
    const before = tally
    const action = voteAction(tally.mine, clicked)
    setBusy(true)
    setError('')
    setTally(optimistic(tally, clicked))
    try {
      const answer = action === 'withdraw' ? await api.feedback.withdraw({ kind, id, ref }) : await api.feedback.vote({ kind, id, ref }, clicked)
      setTally(answer)
      const ask = action === 'vote' && clicked === 'dislike'
      setAsking(ask)
      if (ask) setReason(answer.reason)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
      await reconcile(before)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }

  async function sayWhy(event: FormEvent) {
    event.preventDefault()
    if (sending.current) return
    sending.current = true
    votes.current += 1
    const before = tally
    setBusy(true)
    setError('')
    try {
      setTally(await api.feedback.vote({ kind, id, ref }, 'dislike', oneLine(reason)))
      setAsking(false)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
      await reconcile(before)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }

  if (failed) return null
  return (
    <div className="feedback" role="group" aria-label={`Your vote on this ${what}`} aria-busy={busy}>
      <div className="feedback-row">
        {(['like', 'dislike'] as const).map((vote) => (
          <button
            key={vote}
            type="button"
            className={`link feedback-vote${tally.mine === vote ? ' pressed' : ''}`}
            aria-pressed={tally.mine === vote}
            aria-label={voteLabel(vote, what)}
            title={voteLabel(vote, what)}
            disabled={busy}
            onClick={() => void cast(vote)}
          >
            <span aria-hidden="true">{vote === 'like' ? '👍' : '👎'}</span>
            <span className="feedback-count">{vote === 'like' ? tally.likes : tally.dislikes}</span>
          </button>
        ))}
        {tally.mine === 'dislike' && tally.reason && !asking && <span className="feedback-reason">{tally.reason}</span>}
        <HelpTip entry={HELP.feedback} />
      </div>
      {asking && (
        <form className="feedback-why" onSubmit={(e) => void sayWhy(e)}>
          <label htmlFor={inputId}>What's wrong?</label>
          {what === 'drawing' && <span className="feedback-reason">the next drawing of it avoids it</span>}
          <input
            id={inputId}
            value={reason}
            maxLength={REASON_MAX}
            placeholder="optional, one line"
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation()
                setAsking(false)
              }
            }}
          />
          <button type="submit" disabled={busy}>
            Save
          </button>
          <button type="button" className="link" onClick={() => setAsking(false)}>
            Skip
          </button>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
