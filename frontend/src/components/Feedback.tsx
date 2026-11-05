import { useContext, useEffect, useId, useState, type FormEvent } from 'react'
import { api, type FeedbackTally, type FeedbackTarget, type FeedbackVote } from '../lib/api'
import { HELP } from '../lib/help'
import { REASON_MAX, VoteContext, oneLine, optimistic, voteAction, voteLabel, type FeedbackWhat } from '../lib/feedback'
import HelpTip from './HelpTip'

const EMPTY = { likes: 0, dislikes: 0, mine: null, reason: '' }

// A like or a dislike of something the app generated, under it: two small buttons with their
// counts, pressed for the person's own vote; a click on the pressed one takes it back. A
// dislike asks, in one optional line, what is wrong. The votes go to the review tools, never
// to a model. The owner and a judge's code vote; the demo visitor sees nothing.
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

  useEffect(() => {
    let cancelled = false
    api.feedback
      .get({ kind, id, ref })
      .then((found) => {
        if (!cancelled) setTally(found)
      })
      .catch(() => {
        // a target the server does not know (or will not count for this session): no buttons
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [kind, id, ref])

  async function cast(clicked: FeedbackVote) {
    if (busy) return
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
      setTally(before)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function sayWhy(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      setTally(await api.feedback.vote({ kind, id, ref }, 'dislike', oneLine(reason)))
      setAsking(false)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (failed) return null
  return (
    <div className="feedback" role="group" aria-label={`Your vote on this ${what}`}>
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
