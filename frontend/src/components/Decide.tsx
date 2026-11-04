import { useEffect, useState } from 'react'
import { api, type Decision, type DecisionChoice, type Item, type Scenarios as ScenarioSet, type Uses } from '../lib/api'
import { CHOICES, LEADS_TO, candidatesText, choiceLabel, effortLabel, fillsLine, reservedLine, worthLine } from '../lib/decide'
import { usd } from '../lib/format'
import { whenText } from '../lib/inventory'
import { Earlier, NeverRun } from './Saved'
import Scenarios from './Scenarios'
import SignInLine from './SignInLine'
import HelpTip from './HelpTip'
import { HELP } from '../lib/help'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// One place to decide what the item becomes: three scenarios written for the owner, then what it
// is, what it is worth, what it is good for, what would complete it, and the choice. The rows
// gather what the other panels answered; the uses and the scenarios are the model's and say so;
// the choice is kept on the item as an event. Opening it asks no model: the answers kept are
// shown as they were, the earlier ones a click away; asking again adds a new one. The demo
// visitor (readOnly) reads the same, with no button that asks or decides.
export default function Decide({
  item,
  guided,
  onDecide,
  onGuided,
  demo = false,
  readOnly = demo,
}: {
  item: Item
  // bumped when the Value panel writes a guidance: the worth row reads it again
  guided: number
  onDecide: (choice: DecisionChoice, note: string) => Promise<void>
  // told when the sell card writes a guidance, so the Value panel reads it too
  onGuided: () => void
  // the demo visitor: nothing is drawn for them
  demo?: boolean
  // the demo visitor, or an item served as the visitor sees it: read, never ask or decide
  readOnly?: boolean
}) {
  const [view, setView] = useState<Decision | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [refusal, setRefusal] = useState('')
  // where the refused choice was made: said by the cards or by the row of buttons
  const [refusedAt, setRefusedAt] = useState<'cards' | 'row'>('row')
  // bumped after a decision: the same choice again leaves the version as it was, yet the last
  // decision and its date change
  const [decided, setDecided] = useState(0)
  // every set of cards and every answer of ideas kept, oldest first, and the ones shown (the
  // latest unless an earlier one is picked)
  const [cardsKept, setCardsKept] = useState<ScenarioSet[]>([])
  const [usesKept, setUsesKept] = useState<Uses[]>([])
  const [cardsShown, setCardsShown] = useState<number | null>(null)
  const [usesShown, setUsesShown] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    api.decide
      .view(item.id)
      .then((d) => {
        if (cancelled) return
        setView(d)
        setError('')
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    // the earlier answers are a list beside the view; one that cannot be read lists none
    api.decide
      .history(item.id)
      .then((list) => {
        if (!cancelled) setCardsKept(list)
      })
      .catch(() => undefined)
    api.decide
      .usesHistory(item.id)
      .then((list) => {
        if (!cancelled) setUsesKept(list)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
    // the item's version too: a decision, an edit or an accepted value changes the rows
  }, [item.id, item.version, decided, guided])

  const cards = (cardsShown !== null && cardsKept.find((c) => c.id === cardsShown)) || view?.scenarios || null
  const uses = (usesShown !== null && usesKept.find((u) => u.id === usesShown)) || view?.uses || null

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
      setUsesKept((kept) => [...kept, uses])
      setUsesShown(null)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy('')
    }
  }

  async function askScenarios() {
    if (busy) return
    setBusy('scenarios')
    setError('')
    try {
      const scenarios = await api.decide.scenarios(item.id)
      setView((current) => (current ? { ...current, scenarios } : current))
      setCardsKept((kept) => [...kept, scenarios])
      setCardsShown(null)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy('')
    }
  }

  // The sell card's price guidance: the existing price route, in the currency of the owner's
  // profile and with no place, the same as the Value panel's form left blank.
  async function askPrice() {
    if (busy) return
    setBusy('price')
    setError('')
    try {
      const prefs = await api.build.preferences()
      await api.value.guide(item.id, { currency: prefs.currency, country: '', city: '' })
      setDecided((n) => n + 1)
      onGuided()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy('')
    }
  }

  // A refused decision (the demo visitor, a conflict, no connection) is said here, by the
  // buttons; the note stays as typed and nothing scrolls, because nothing was decided.
  async function choose(choice: DecisionChoice, from: 'cards' | 'row' = 'row') {
    if (busy) return
    setBusy(choice)
    setRefusal('')
    setRefusedAt(from)
    try {
      await onDecide(choice, note)
      setNote('')
      setDecided((n) => n + 1)
      // scrolled to and focused there, so a keyboard or screen reader user lands where a
      // pointer user looks
      const lead = LEADS_TO[choice]
      if (lead) {
        document.querySelector(lead.scroll)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        document.querySelector<HTMLElement>(lead.focus)?.focus({ preventScroll: true })
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
      <div className="section-head">
        <h4>Decide</h4>
        <HelpTip entry={readOnly ? HELP.decideVisitor : HELP.decide} />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {view === null && !error && <p className="muted">Loading…</p>}
      {view && (
        <Scenarios
          scenarios={cards}
          worth={view.worth}
          last={view.last}
          busy={busy}
          onAsk={() => void askScenarios()}
          onChoose={(choice) => void choose(choice, 'cards')}
          onPrice={() => void askPrice()}
          demo={demo}
          readOnly={readOnly}
        />
      )}
      {view && <Earlier items={cardsKept} shown={cards?.id ?? null} onPick={(c) => setCardsShown(c.id)} what="cards" />}
      {refusal && refusedAt === 'cards' && (
        <p className="error" role="alert">
          Not decided: {refusal}
        </p>
      )}
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
            {view.worth === null && !readOnly && (
              <>
                {' '}
                <button type="button" className="link" onClick={askWorth}>
                  Ask what it is worth
                </button>
              </>
            )}
          </dd>

          <dt className="good-for" tabIndex={-1}>
            What it is good for
          </dt>
          <dd>
            {item.intent === 'build' && (
              <>
                Kept for a build. <a href="#build">Plan it in Build and reuse</a>.{' '}
              </>
            )}
            <span className="rules">{fillsLine(view.templates)}</span>{' '}
            {!readOnly && (
              <button type="button" className="link" onClick={() => void askUses()} disabled={busy !== ''}>
                {busy === 'uses' ? 'Working…' : uses ? 'Ask for ideas again' : 'Ask for ideas'}
              </button>
            )}
            {uses ? (
              <UsesView uses={uses} />
            ) : readOnly ? (
              <span className="muted">No ideas were asked for.</span>
            ) : (
              <NeverRun step="uses" />
            )}
            <Earlier items={usesKept} shown={uses?.id ?? null} onPick={(u) => setUsesShown(u.id)} what="ideas" />
          </dd>

          <dt>Parts it still needs</dt>
          <dd>
            {view.searches.length === 0 ? (
              <>
                No open search for a part. Start one on <a href="#find">Find a part</a>.
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
          <dd>
            <button type="button" className="link" onClick={() => document.querySelector('section.picture')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
              Go to the picture section
            </button>
          </dd>

          <dt>Decision</dt>
          <dd>
            {view.last && (
              <p className="decided" role="status" aria-label="Decision made">
                Decided: <span className="badge">{choiceLabel(view.last.choice)}</span> {whenText(view.last.at)}
                {view.last.note && <> · {view.last.note}</>}
              </p>
            )}
            {!view.last && readOnly && <p className="muted">No plan chosen yet.</p>}
            {view.committed_to.length > 0 && (
              <p className="reserved" role="note">
                {reservedLine(view.committed_to)}
              </p>
            )}
            {readOnly ? (
              <SignInLine what="Decide" />
            ) : (
              <>
            <div className="row">
              <label>
                <span>Note</span>
                <input value={note} maxLength={200} placeholder="why (optional)" onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
            <div className="row choices">
              {CHOICES.map((c) => (
                <button key={c.value} type="button" onClick={() => void choose(c.value)} disabled={busy !== ''}>
                  {busy === c.value ? 'Working…' : c.label}
                </button>
              ))}
            </div>
            {refusal && refusedAt === 'row' && (
              <p className="error" role="alert">
                Not decided: {refusal}
              </p>
            )}
              </>
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
        Ideas from the model · {uses.model} · {usd(uses.cost_usd)}
        {uses.from_fixture && <span className="badge">recorded answer</span>}
        {uses.stale && <span className="badge">item changed since</span>}
      </p>
      {uses.uses.length === 0 ? (
        <p className="muted">No ideas came back.</p>
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
