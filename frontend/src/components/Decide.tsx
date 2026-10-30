import { useEffect, useState } from 'react'
import { api, type Decision, type DecisionChoice, type Item, type Uses } from '../lib/api'
import { CHOICES, candidatesText, choiceLabel, effortLabel, fillsLine, reservedLine, worthLine } from '../lib/decide'
import { usd } from '../lib/format'
import { whenText } from '../lib/inventory'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// One place to decide what the item becomes: what it is, what it is worth, what it is good for,
// what would complete it, then the choice. The rows gather what the other panels answered; the
// uses are the model's proposals and say so; the choice is kept on the item as an event.
export default function Decide({
  item,
  onDecide,
}: {
  item: Item
  onDecide: (choice: DecisionChoice, note: string) => Promise<void>
}) {
  const [view, setView] = useState<Decision | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [refusal, setRefusal] = useState('')

  useEffect(() => {
    let cancelled = false
    api.decide
      .view(item.id)
      .then((d) => {
        if (!cancelled) setView(d)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
    // the item's version too: a decision, an edit or an accepted value changes the rows
  }, [item.id, item.version])

  // The price call takes the currency and the place from the owner, on the Value panel's own
  // form; this row sends them there rather than ask with a currency it made up.
  function askWorth() {
    const form = document.querySelector<HTMLFormElement>('section.value form')
    form?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    form?.querySelector<HTMLElement>('input, select')?.focus({ preventScroll: true })
  }

  async function askUses() {
    if (busy) return
    setBusy('uses')
    setError('')
    try {
      const uses = await api.decide.uses(item.id)
      setView((current) => (current ? { ...current, uses } : current))
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy('')
    }
  }

  // A refused decision (the demo visitor, a conflict, no connection) is said here, by the
  // buttons; the note stays as typed and nothing scrolls, because nothing was decided.
  async function choose(choice: DecisionChoice) {
    if (busy) return
    setBusy(choice)
    setRefusal('')
    try {
      await onDecide(choice, note)
      setNote('')
      if (choice === 'sell' || choice === 'give') {
        document.querySelector('section.listing')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    } catch (err: unknown) {
      setRefusal(message(err))
    } finally {
      setBusy('')
    }
  }

  function showFields() {
    document.querySelector('table[aria-label="Fields"]')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <section className="decide" aria-label="Decide">
      <h4>Decide</h4>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {view === null && !error && <p className="muted">Loading…</p>}
      {view && (
        <dl className="rows">
          <dt>What it is</dt>
          <dd>
            {item.item_type} · {view.accepted_fields} of {item.field_count} value{item.field_count === 1 ? '' : 's'} accepted
            {' · '}
            <button type="button" className="link" onClick={showFields}>
              see the values
            </button>
          </dd>

          <dt>What it is worth</dt>
          <dd>
            {worthLine(view.worth)}
            {view.worth === null && (
              <>
                {' '}
                <button type="button" className="link" onClick={askWorth}>
                  Ask what it is worth
                </button>
              </>
            )}
          </dd>

          <dt>What it is good for</dt>
          <dd>
            <span className="rules">{fillsLine(view.templates)}</span>{' '}
            <button type="button" className="link" onClick={() => void askUses()} disabled={busy !== ''}>
              {busy === 'uses' ? 'Working…' : view.uses ? 'Ask for ideas again' : 'Ask for ideas'}
            </button>
            {view.uses && <UsesView uses={view.uses} />}
          </dd>

          <dt>What would complete it</dt>
          <dd>
            {view.searches.length === 0 ? (
              <>
                No open search from this item. <a href="#find">Find a part</a> opens one.
              </>
            ) : (
              <ul className="searches" aria-label="Open searches">
                {view.searches.map((s) => (
                  <li key={s.id}>
                    {s.title} · {candidatesText(s)} ·{' '}
                    <a href={s.handoff_url} target="_blank" rel="noopener noreferrer">
                      Marketplace search
                    </a>{' '}
                    · <a href="#find">Find a part</a>
                  </li>
                ))}
              </ul>
            )}
          </dd>

          <dt>What it could look like</dt>
          <dd className="muted">Picture: coming.</dd>

          <dt>Decision</dt>
          <dd>
            {view.last && (
              <p className="decided" role="status" aria-label="Decision made">
                Decided: <span className="badge">{choiceLabel(view.last.choice)}</span> {whenText(view.last.at)}
                {view.last.note && <> · {view.last.note}</>}
              </p>
            )}
            {view.committed_to.length > 0 && (
              <p className="reserved" role="note">
                {reservedLine(view.committed_to)}
              </p>
            )}
            <div className="row">
              <label>
                <span>Note</span>
                <input value={note} maxLength={200} placeholder="why, in a line" onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
            <div className="row choices">
              {CHOICES.map((c) => (
                <button key={c.value} type="button" onClick={() => void choose(c.value)} disabled={busy !== ''}>
                  {busy === c.value ? 'Working…' : c.label}
                </button>
              ))}
            </div>
            {refusal && (
              <p className="error" role="alert">
                Not decided: {refusal}
              </p>
            )}
          </dd>
        </dl>
      )}
    </section>
  )
}

function UsesView({ uses }: { uses: Uses }) {
  return (
    <div className="uses" role="status" aria-label={`Ideas ${uses.version}`}>
      <p className="meta">
        The model's proposals · {uses.model} · {usd(uses.cost_usd)}
        {uses.from_fixture && <span className="badge">recorded answer</span>}
        {uses.stale && <span className="badge">item changed since</span>}
      </p>
      {uses.uses.length === 0 ? (
        <p className="muted">No use was proposed.</p>
      ) : (
        <ul aria-label="Ideas">
          {uses.uses.map((u, i) => (
            <li key={`${i}:${u.title}`}>
              <strong>{u.title}</strong> <small className="muted">({effortLabel(u.effort)})</small>
              <br />
              {u.what_it_does}
              {u.needs.length > 0 && <span className="raw">Needs: {u.needs.join('; ')}</span>}
              {u.note && <span className="raw">Check first: {u.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
